"""
tours/tests/tests_e2e.py

Pruebas end-to-end para la interacción de chat entre guías y turistas durante un tour en vivo.
Valida:
  - Flujo básico: envío y recepción de mensajes
  - Múltiples turistas en la misma sesión
  - Integridad del chat ante cierre de sesión
  - Integridad del chat ante desconexión de participantes
  - Validación de permisos y restricciones
"""
import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Parada, Ruta
from tours.models import MensajeChat, SesionTour, Turista, TuristaSesion


class E2EChatGuideTouristTests(TestCase):
    """Pruebas end-to-end para chat entre guía y turistas durante tour en vivo."""

    def setUp(self):
        """Crea un escenario básico: guía, ruta, sesión y turistas."""
        # Crear guía autenticado
        self.guia_user = User.objects.create_user(
            username='guia_e2e_test',
            password='test1234'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(user=auth_guia)

        # Crear ruta
        self.ruta = Ruta.objects.create(
            titulo='Ruta E2E Chat Test',
            descripcion='Ruta para validar chat guía/turista',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia', 'Naturaleza'],
            guia=self.guia,
        )

        # Crear parada inicial si la ruta lo requiere
        self.parada = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada Inicial',
            orden=1,
            coordenadas=Point(-3.7038, 40.4168, srid=4326),  # (lon, lat) para PostGIS
        )

        # Crear sesión en estado EN_CURSO
        self.sesion = SesionTour.objects.create(
            codigo_acceso='E2E001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
            parada_actual=self.parada,
        )

        # Cliente del guía autenticado
        self.guia_client = Client()
        self.guia_client.force_login(self.guia_user)

    def _crear_turista_con_sesion(self, alias: str) -> tuple[Turista, Client]:
        """
        Helper: crea un turista y lo une a la sesión.
        Retorna (Turista, Client) configurado con sesión de turista.
        """
        turista = Turista.objects.create(alias=alias)
        TuristaSesion.objects.create(
            turista=turista,
            sesion_tour=self.sesion,
            activo=True,
        )

        client = Client()
        session = client.session
        session['turista_id'] = turista.id
        session['turista_alias'] = turista.alias
        session.save()

        return turista, client

    # =========================================================================
    # TEST 1: Flujo básico — guía envía, turista recibe
    # =========================================================================

    def test_guia_envia_mensaje_y_turista_lo_recibe(self):
        """
        Verifica que el guía pueda enviar un mensaje y que el turista
        lo reciba correctamente.
        """
        turista1, turista1_client = self._crear_turista_con_sesion('turista_basico_1')

        # Guía envía mensaje
        texto_mensaje = 'Bienvenidos al tour. Nos reunimos en 5 minutos.'
        response = self.guia_client.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': texto_mensaje}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['texto'], texto_mensaje)
        self.assertEqual(data['nombre_remitente'], self.guia_user.username)

        # Turista obtiene mensajes
        response = turista1_client.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['total'], 1)
        self.assertEqual(len(data['mensajes']), 1)
        self.assertEqual(data['mensajes'][0]['texto'], texto_mensaje)
        self.assertEqual(data['mensajes'][0]['nombre_remitente'], self.guia_user.username)

    def test_turista_envia_mensaje_y_guia_lo_recibe(self):
        """
        Verifica que un turista pueda enviar un mensaje y que el guía
        lo reciba correctamente.
        """
        turista1, turista1_client = self._crear_turista_con_sesion('turista_basico_2')

        # Turista envía mensaje
        texto_mensaje = 'Tengo una pregunta sobre la parada anterior.'
        response = turista1_client.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': texto_mensaje}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['texto'], texto_mensaje)
        self.assertEqual(data['nombre_remitente'], turista1.alias)

        # Guía obtiene mensajes
        response = self.guia_client.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['total'], 1)
        self.assertTrue(
            any(
                m['texto'] == texto_mensaje and
                m['nombre_remitente'] == turista1.alias
                for m in data['mensajes']
            )
        )

    # =========================================================================
    # TEST 2: Múltiples turistas — verificar orden y aislamiento
    # =========================================================================

    def test_multiples_turistas_envian_y_reciben_mensajes_en_orden(self):
        """
        Verifica que múltiples turistas pueden participar en el chat
        y que los mensajes se mantienen en orden cronológico.
        """
        turista1, client1 = self._crear_turista_con_sesion('turista_multi_1')
        turista2, client2 = self._crear_turista_con_sesion('turista_multi_2')
        turista3, client3 = self._crear_turista_con_sesion('turista_multi_3')

        # Secuencia de mensajes
        msg1_text = 'Primer mensaje del turista 1'
        msg2_text = 'Respuesta del turista 2'
        msg3_text = 'Es increíble, turista 3 aquí'
        msg4_text = 'Información importante del guía'

        # Turista 1 envía
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': msg1_text}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Turista 2 envía
        response = client2.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': msg2_text}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Turista 3 envía
        response = client3.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': msg3_text}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Guía envía
        response = self.guia_client.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': msg4_text}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Todos obtienen los 4 mensajes en orden
        for client in [client1, client2, client3, self.guia_client]:
            response = client.get(
                reverse('tours:obtener_mensajes', args=[self.sesion.id])
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()

            self.assertEqual(data['total'], 4)
            self.assertEqual(len(data['mensajes']), 4)

            # Verificar orden: los textos deben aparecer en secuencia
            textos = [m['texto'] for m in data['mensajes']]
            self.assertEqual(textos, [msg1_text, msg2_text, msg3_text, msg4_text])

    def test_turista_aislado_no_puede_acceder_a_chat_de_otra_sesion(self):
        """
        Verifica que un turista no pueda enviar/leer mensajes de una sesión
        a la que no pertenece.
        """
        # Turista 1 se une a sesión 1
        turista1, client1 = self._crear_turista_con_sesion('turista_aislado_1')

        # Crear segunda sesión
        sesion2 = SesionTour.objects.create(
            codigo_acceso='E2E002',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
            parada_actual=self.parada,
        )

        # Turista 1 intenta enviar mensaje a sesión 2 sin estar unido
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[sesion2.id]),
            data=json.dumps({'texto': 'No debo poder enviar esto'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('error', response.json())

        # Turista 1 intenta leer mensajes de sesión 2
        response = client1.get(
            reverse('tours:obtener_mensajes', args=[sesion2.id])
        )
        self.assertEqual(response.status_code, 403)

    # =========================================================================
    # TEST 3: Validación de mensajes — límites y restricciones
    # =========================================================================

    def test_mensaje_vacio_es_rechazado(self):
        """Verifica que los mensajes vacíos sean rechazados."""
        turista1, client1 = self._crear_turista_con_sesion('turista_validacion_1')

        # Intento 1: texto vacío
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

        # Intento 2: texto con solo espacios
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': '   '}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_mensaje_muy_largo_es_rechazado(self):
        """Verifica que los mensajes que exceden el límite de 5000 caracteres sean rechazados."""
        turista1, client1 = self._crear_turista_con_sesion('turista_validacion_2')

        # Mensaje con 5001 caracteres
        texto_largo = 'a' * 5001

        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': texto_largo}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('demasiado largo', data['error'].lower())

    def test_mensaje_en_limite_es_aceptado(self):
        """Verifica que un mensaje de exactamente 5000 caracteres sea aceptado."""
        turista1, client1 = self._crear_turista_con_sesion('turista_validacion_3')

        texto_limite = 'x' * 5000

        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': texto_limite}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['texto'], texto_limite)

    # =========================================================================
    # TEST 4: Cierre de sesión — integridad del chat
    # =========================================================================

    def test_no_se_pueden_enviar_mensajes_despues_de_cerrar_sesion(self):
        """
        Verifica que ningún participante pueda enviar mensajes
        después de que la sesión haya sido finalizada.
        """
        turista1, client1 = self._crear_turista_con_sesion('turista_cierre_1')

        # Enviar mensaje antes de cerrar (debe funcionar)
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Mensaje antes del cierre'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Cerrar sesión
        self.sesion.estado = SesionTour.FINALIZADO
        self.sesion.save()

        # Turista intenta enviar mensaje después del cierre
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Mensaje después del cierre'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('finalizada', data['error'].lower())

        # Guía también es bloqueado
        response = self.guia_client.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Intento del guía'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_mensajes_previos_persisten_despues_de_cerrar_sesion(self):
        """
        Verifica que los mensajes anteriores al cierre permanezcan
        accesibles después de finalizar la sesión.
        """
        turista1, client1 = self._crear_turista_con_sesion('turista_cierre_2')

        # Enviar varios mensajes
        msg1 = 'Primer mensaje'
        msg2 = 'Segundo mensaje'
        msg3 = 'Tercer mensaje'

        for texto in [msg1, msg2, msg3]:
            response = client1.post(
                reverse('tours:enviar_mensaje', args=[self.sesion.id]),
                data=json.dumps({'texto': texto}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 201)

        # Cerrar sesión
        self.sesion.estado = SesionTour.FINALIZADO
        self.sesion.save()

        # Verificar que los mensajes siguen siendo accesibles
        response = client1.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['total'], 3)
        textos = [m['texto'] for m in data['mensajes']]
        self.assertEqual(textos, [msg1, msg2, msg3])

    # =========================================================================
    # TEST 5: Desconexión de turistas — integridad del chat
    # =========================================================================

    def test_turista_desconectado_no_puede_enviar_mensajes(self):
        """
        Verifica que un turista que ha sido desconectado
        (TuristaSesion.activo=False) no pueda enviar mensajes.
        """
        turista1, client1 = self._crear_turista_con_sesion('turista_desconexion_1')

        # Turista envía un mensaje (debe funcionar)
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Mensaje antes de desconexión'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Desconectar turista (marcar como inactivo)
        ts = TuristaSesion.objects.get(turista=turista1, sesion_tour=self.sesion)
        ts.activo = False
        ts.save()

        # Turista intenta enviar otro mensaje
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Acaso puedo enviar esto?'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_turista_desconectado_no_puede_leer_nuevos_mensajes(self):
        """
        Verifica que un turista desconectado no pueda recuperar mensajes.
        """
        turista1, client1 = self._crear_turista_con_sesion('turista_desconexion_2')

        # Desconectar turista
        ts = TuristaSesion.objects.get(turista=turista1, sesion_tour=self.sesion)
        ts.activo = False
        ts.save()

        # Turista intenta recuperar mensajes
        response = client1.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )
        self.assertEqual(response.status_code, 403)

    def test_mensajes_de_turista_desconectado_persisten_en_bd(self):
        """
        Verifica que los mensajes enviados por un turista antes de
        desconectarse permanezcan en la base de datos.
        """
        turista1, client1 = self._crear_turista_con_sesion('turista_desconexion_3')

        # Turista envía mensaje
        texto_mensaje = 'Este mensaje debe persistir'
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': texto_mensaje}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        mensaje_id = response.json()['mensaje_id']

        # Desconectar turista
        ts = TuristaSesion.objects.get(turista=turista1, sesion_tour=self.sesion)
        ts.activo = False
        ts.save()

        # Verificar que el mensaje persiste en BD
        mensaje = MensajeChat.objects.get(id=mensaje_id)
        self.assertEqual(mensaje.texto, texto_mensaje)
        self.assertEqual(mensaje.turista, turista1)
        self.assertEqual(mensaje.sesion_tour, self.sesion)

    def test_otros_turistas_siguen_viendo_mensajes_de_desconectado(self):
        """
        Verifica que cuando un turista se desconecta, los otros
        participantes aún pueden ver sus mensajes previos.
        """
        turista1, client1 = self._crear_turista_con_sesion('turista_desconexion_4a')
        turista2, client2 = self._crear_turista_con_sesion('turista_desconexion_4b')

        # Turista 1 envía mensaje
        msg1 = 'Soy el turista 1'
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': msg1}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Turista 2 envía mensaje
        msg2 = 'Soy el turista 2'
        response = client2.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': msg2}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Desconectar turista 1
        ts = TuristaSesion.objects.get(turista=turista1, sesion_tour=self.sesion)
        ts.activo = False
        ts.save()

        # Turista 2 sigue pudiendo ver todos los mensajes incluyendo el de turista 1
        response = client2.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['total'], 2)
        textos = [m['texto'] for m in data['mensajes']]
        self.assertIn(msg1, textos)
        self.assertIn(msg2, textos)

    # =========================================================================
    # TEST 6: Recuperación de mensajes con límites y filtros
    # =========================================================================

    def test_obtener_mensajes_con_limite(self):
        """Verifica que el parámetro `limite` funciona correctamente."""
        turista1, client1 = self._crear_turista_con_sesion('turista_limite_1')

        # Enviar 10 mensajes
        for i in range(10):
            response = client1.post(
                reverse('tours:enviar_mensaje', args=[self.sesion.id]),
                data=json.dumps({'texto': f'Mensaje {i + 1}'}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 201)

        # Obtener solo los últimos 5
        response = client1.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]) + '?limite=5'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['total'], 5)
        self.assertEqual(len(data['mensajes']), 5)
        # Los últimos 5 deben ser del 6 al 10
        textos = [m['texto'] for m in data['mensajes']]
        self.assertIn('Mensaje 6', textos)
        self.assertIn('Mensaje 10', textos)

    def test_obtener_mensajes_limite_invalido(self):
        """Verifica que límites inválidos sean rechazados."""
        turista1, client1 = self._crear_turista_con_sesion('turista_limite_2')

        # Límite menor que 1
        response = client1.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]) + '?limite=0'
        )
        self.assertEqual(response.status_code, 400)

        # Límite mayor que 200
        response = client1.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]) + '?limite=300'
        )
        self.assertEqual(response.status_code, 400)

        # Límite no numérico
        response = client1.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]) + '?limite=abc'
        )
        self.assertEqual(response.status_code, 400)

    def test_obtener_mensajes_con_filtro_desde(self):
        """
        Verifica que el filtro `desde` permite recuperar solo mensajes
        posteriores a una fecha/hora dada.
        """
        from urllib.parse import quote
        
        turista1, client1 = self._crear_turista_con_sesion('turista_desde_1')

        # Enviar mensaje
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Mensaje antiguo'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        momento1 = response.json()['momento']

        # Esperar un poco
        import time
        time.sleep(0.1)

        # Enviar segundo mensaje
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Mensaje nuevo'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Recuperar solo mensajes posteriores al primer momento
        # Usar quote() para codificar caracteres especiales en la URL
        url = reverse('tours:obtener_mensajes', args=[self.sesion.id]) + f'?desde={quote(momento1)}'
        response = client1.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['total'], 1)
        self.assertEqual(data['mensajes'][0]['texto'], 'Mensaje nuevo')

    # =========================================================================
    # TEST 7: Integridad de datos
    # =========================================================================

    def test_cada_mensaje_tiene_los_campos_requeridos(self):
        """
        Verifica que cada mensaje enviado contenga todos los campos
        requeridos en la respuesta.
        """
        turista1, client1 = self._crear_turista_con_sesion('turista_campos_1')

        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Mensaje de prueba'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()

        # Verificar que existen todos los campos esperados
        required_fields = [
            'status', 'mensaje_id', 'id', 'nombre_remitente',
            'texto', 'momento'
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Campo '{field}' no encontrado en respuesta")

    def test_momento_es_iso_format(self):
        """Verifica que el timestamp del mensaje esté en formato ISO-8601."""
        turista1, client1 = self._crear_turista_con_sesion('turista_iso_1')

        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Prueba ISO'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        momento_str = data['momento']

        # Intentar parsear como ISO-8601
        from django.utils.dateparse import parse_datetime
        momento = parse_datetime(momento_str)
        self.assertIsNotNone(momento, f"'{momento_str}' no es ISO-8601 válido")

    def test_nombre_remitente_es_correcto_para_guia_y_turista(self):
        """
        Verifica que el nombre del remitente se asigna correctamente:
        - username para el guía
        - alias para turistas
        """
        turista1, client1 = self._crear_turista_con_sesion('turista_name_1')

        # Turista envía
        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Mensaje turista'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['nombre_remitente'], turista1.alias)

        # Guía envía
        response = self.guia_client.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Mensaje guía'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['nombre_remitente'], self.guia_user.username)

    def test_estado_sesion_es_reflejado_en_obtener_mensajes(self):
        """Verifica que el estado de la sesión se incluya en la respuesta."""
        turista1, client1 = self._crear_turista_con_sesion('turista_estado_1')

        # Sesión en EN_CURSO
        response = client1.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['estado_sesion'], SesionTour.EN_CURSO)

        # Cambiar a FINALIZADO
        self.sesion.estado = SesionTour.FINALIZADO
        self.sesion.save()

        response = client1.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['estado_sesion'], SesionTour.FINALIZADO)

    # =========================================================================
    # TEST 8: Casos extremos
    # =========================================================================

    def test_sesion_inexistente_retorna_404(self):
        """Verifica que acceder a una sesión inexistente retorne 404."""
        turista1, client1 = self._crear_turista_con_sesion('turista_404_1')

        response = client1.post(
            reverse('tours:enviar_mensaje', args=[99999]),
            data=json.dumps({'texto': 'Mensaje a sesión inexistente'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)

    def test_json_invalido_retorna_400(self):
        """Verifica que JSON inválido sea rechazado."""
        turista1, client1 = self._crear_turista_con_sesion('turista_json_1')

        response = client1.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data='{"texto": "mensaje incompleto"',  # JSON inválido
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

