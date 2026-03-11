"""
tests/test_chat_api_integration.py

Tests de integración de los endpoints REST del chat (S2.1-54, S2.1-55).

Valida los endpoints:
- POST /tours/sesiones/<id>/mensajes/enviar/
- GET  /tours/sesiones/<id>/mensajes/

Verifica:
- Envío y recuperación correcta de mensajes
- Filtros de consulta (desde, limite)
- Manejo de errores (sesión inexistente, no autorizado, sesión finalizada)
- Validaciones de entrada (JSON inválido, texto vacío, límites)
"""
import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import MensajeChat, SesionTour, Turista, TuristaSesion


class EnviarMensajeAPITest(TestCase):
    """Tests del endpoint POST /tours/sesiones/<id>/mensajes/enviar/"""

    def setUp(self):
        """Configuración inicial."""
        # Crear guía autenticado
        self.user_guia = User.objects.create_user(
            username='guia_api_test',
            password='test123'
        )
        auth_user = AuthUser.objects.create(user=self.user_guia)
        self.guia = Guia.objects.create(user=auth_user)

        # Crear ruta
        self.ruta = Ruta.objects.create(
            titulo='Ruta API Integration Test',
            descripcion='Test de endpoints REST',
            duracion_horas=2,
            num_personas=20,
            nivel_exigencia='Media',
            mood=['Aventura'],
            guia=self.guia
        )

        # Crear sesión activa
        self.sesion_activa = SesionTour.objects.create(
            codigo_acceso='API001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

        # Crear sesión finalizada
        self.sesion_finalizada = SesionTour.objects.create(
            codigo_acceso='API002',
            estado=SesionTour.FINALIZADO,
            fecha_inicio=timezone.now() - timedelta(hours=5),
            ruta=self.ruta
        )

        # Crear turista anónimo
        self.turista = Turista.objects.create(alias='TurAnonimo')
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion_activa,
            activo=True
        )

        # Clientes HTTP
        self.client_guia = Client()
        self.client_guia.force_login(self.user_guia)

        self.client_turista = Client()
        session = self.client_turista.session
        session['turista_id'] = self.turista.id
        session['turista_alias'] = self.turista.alias
        session.save()

        self.client_anonimo = Client()

    # ======================================================================
    # Tests de envío exitoso
    # ======================================================================

    def test_guia_envia_mensaje_exitosamente(self):
        """Test: Guía autenticado envía un mensaje correctamente."""
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': 'Hola turistas'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['texto'], 'Hola turistas')
        self.assertEqual(data['nombre_remitente'], 'guia_api_test')
        self.assertIn('mensaje_id', data)
        self.assertIn('id', data)
        self.assertIn('momento', data)

        # Verificar que se guardó en BD
        mensaje = MensajeChat.objects.get(id=data['mensaje_id'])
        self.assertEqual(mensaje.texto, 'Hola turistas')
        self.assertEqual(mensaje.remitente, self.user_guia)
        self.assertIsNone(mensaje.turista)

    def test_turista_anonimo_envia_mensaje_exitosamente(self):
        """Test: Turista anónimo envía un mensaje correctamente."""
        response = self.client_turista.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': 'Pregunta del turista'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['texto'], 'Pregunta del turista')
        self.assertEqual(data['nombre_remitente'], 'TurAnonimo')

        # Verificar que se guardó con turista, no con user
        mensaje = MensajeChat.objects.get(id=data['mensaje_id'])
        self.assertIsNone(mensaje.remitente)
        self.assertEqual(mensaje.turista, self.turista)

    def test_mensaje_con_espacios_se_trimea(self):
        """Test: El texto con espacios iniciales/finales se trimea."""
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': '  Mensaje con espacios  '}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        # El servicio trimea antes de validar
        data = response.json()
        self.assertEqual(data['texto'], 'Mensaje con espacios')

    def test_mensaje_largo_pero_valido(self):
        """Test: Mensaje próximo al límite (5000 caracteres)."""
        texto_largo = 'A' * 4999
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': texto_largo}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data['texto']), 4999)

    def test_multiples_mensajes_en_orden(self):
        """Test: Enviar múltiples mensajes conserva el orden."""
        textos = [f'Mensaje {i}' for i in range(1, 4)]

        ids_mensaje = []
        for i, texto in enumerate(textos):
            response = self.client_guia.post(
                reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
                data=json.dumps({'texto': texto}),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 201)
            ids_mensaje.append(response.json()['mensaje_id'])

        # Verificar que existen en BD
        mensajes = MensajeChat.objects.filter(id__in=ids_mensaje).order_by('momento')
        self.assertEqual(len(mensajes), 3)

        # Verificar orden
        for i, mensaje in enumerate(mensajes):
            self.assertEqual(mensaje.texto, textos[i])

    # ======================================================================
    # Tests de validación de entrada
    # ======================================================================

    def test_texto_vacio_rechazado(self):
        """Test: Texto vacío es rechazado."""
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': ''}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('vacío', data['error'].lower())

    def test_texto_solo_espacios_rechazado(self):
        """Test: Texto con solo espacios es rechazado."""
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': '   '}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)

    def test_texto_faltante_rechazado(self):
        """Test: Omitir el campo texto es rechazado."""
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)

    def test_texto_excede_limite_rechazado(self):
        """Test: Texto > 5000 caracteres es rechazado."""
        texto_largo = 'A' * 5001
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': texto_largo}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('demasiado largo', data['error'].lower())

    def test_json_invalido_rechazado(self):
        """Test: JSON inválido retorna 400."""
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data='{"texto": "sin cerrar',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)

    # ======================================================================
    # Tests de sesión inexistente
    # ======================================================================

    def test_sesion_inexistente_retorna_404(self):
        """Test: Sesión que no existe retorna 404."""
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[99999]),
            data=json.dumps({'texto': 'Test'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('no existe', data['error'].lower())

    # ======================================================================
    # Tests de sesión finalizada
    # ======================================================================

    def test_guia_no_puede_enviar_a_sesion_finalizada(self):
        """Test: Guía no puede enviar a sesión finalizada."""
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_finalizada.id]),
            data=json.dumps({'texto': 'Mensaje a finalizada'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('finalizada', data['error'].lower())
        self.assertEqual(data['estado_sesion'], SesionTour.FINALIZADO)

    def test_turista_no_puede_enviar_a_sesion_finalizada(self):
        """Test: Turista no puede enviar a sesión finalizada."""
        # Unir turista a sesión finalizada
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion_finalizada,
            activo=True
        )

        response = self.client_turista.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_finalizada.id]),
            data=json.dumps({'texto': 'Mensaje'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)

    # ======================================================================
    # Tests de autorización
    # ======================================================================

    def test_usuario_anonimo_no_puede_enviar(self):
        """Test: Usuario no autenticado y sin sesión turista no puede enviar."""
        response = self.client_anonimo.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': 'Test'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('error', data)

    def test_turista_no_puede_enviar_a_otra_sesion(self):
        """Test: Turista no puede enviar a sesión a la que no pertenece."""
        otra_sesion = SesionTour.objects.create(
            codigo_acceso='API003',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

        response = self.client_turista.post(
            reverse('tours:enviar_mensaje', args=[otra_sesion.id]),
            data=json.dumps({'texto': 'Acceso no permitido'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('error', data)

    def test_turista_inactivo_no_puede_enviar(self):
        """Test: Turista marcado como inactivo no puede enviar."""
        # Marcar turista como inactivo
        ts = TuristaSesion.objects.get(
            turista=self.turista,
            sesion_tour=self.sesion_activa
        )
        ts.activo = False
        ts.save()

        response = self.client_turista.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': 'Test'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)

    def test_guia_diferente_no_puede_enviar(self):
        """Test: Un guía que no es de la sesión no puede enviar."""
        # Crear otro guía
        otro_user = User.objects.create_user(
            username='otro_guia',
            password='pass123'
        )
        client_otro_guia = Client()
        client_otro_guia.force_login(otro_user)

        response = client_otro_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': 'No tengo acceso'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)

    # ======================================================================
    # Tests de respuesta correcta
    # ======================================================================

    def test_respuesta_incluye_todos_campos_requeridos(self):
        """Test: La respuesta 201 incluye todos los campos esperados."""
        response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion_activa.id]),
            data=json.dumps({'texto': 'Mensaje completo'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()

        campos_requeridos = [
            'status', 'mensaje_id', 'id', 'nombre_remitente',
            'texto', 'momento'
        ]
        for campo in campos_requeridos:
            self.assertIn(campo, data)

        self.assertEqual(data['status'], 'ok')
        self.assertIsInstance(data['mensaje_id'], int)
        self.assertEqual(data['mensaje_id'], data['id'])
        self.assertIsInstance(data['momento'], str)


class ObtenerMensajesAPITest(TestCase):
    """Tests del endpoint GET /tours/sesiones/<id>/mensajes/"""

    def setUp(self):
        """Configuración inicial."""
        # Crear guía
        self.user_guia = User.objects.create_user(
            username='guia_get_test',
            password='test123'
        )
        auth_user = AuthUser.objects.create(user=self.user_guia)
        self.guia = Guia.objects.create(user=auth_user)

        # Crear ruta y sesión
        self.ruta = Ruta.objects.create(
            titulo='Ruta para GET mensajes',
            descripcion='Test',
            duracion_horas=2,
            num_personas=15,
            nivel_exigencia='Baja',
            mood=['Historia'],
            guia=self.guia
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso='GET001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

        # Crear turista
        self.turista = Turista.objects.create(alias='GetTurista')
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
            activo=True
        )

        # Crear mensajes de prueba (con timestamps diferentes)
        self.messages_data = []
        for i in range(5):
            msg = MensajeChat.objects.create(
                sesion_tour=self.sesion,
                remitente=self.user_guia if i % 2 == 0 else None,
                turista=None if i % 2 == 0 else self.turista,
                nombre_remitente='Guía' if i % 2 == 0 else 'Turista',
                texto=f'Mensaje {i}'
            )
            self.messages_data.append(msg)

        # Clientes
        self.client_guia = Client()
        self.client_guia.force_login(self.user_guia)

        self.client_turista = Client()
        session = self.client_turista.session
        session['turista_id'] = self.turista.id
        session.save()

        self.client_anonimo = Client()

    # ======================================================================
    # Tests de recuperación exitosa
    # ======================================================================

    def test_guia_puede_obtener_mensajes(self):
        """Test: Guía puede recuperar todos los mensajes de la sesión."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn('mensajes', data)
        self.assertIn('total', data)
        self.assertIn('estado_sesion', data)
        self.assertEqual(data['total'], 5)
        self.assertEqual(len(data['mensajes']), 5)
        self.assertEqual(data['estado_sesion'], SesionTour.EN_CURSO)

    def test_turista_puede_obtener_mensajes(self):
        """Test: Turista puede recuperar mensajes de su sesión."""
        response = self.client_turista.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['total'], 5)

    def test_estructura_mensaje_en_respuesta(self):
        """Test: Cada mensaje tiene la estructura correcta."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertGreater(len(data['mensajes']), 0)
        mensaje = data['mensajes'][0]

        campos_requeridos = ['id', 'nombre_remitente', 'texto', 'momento']
        for campo in campos_requeridos:
            self.assertIn(campo, mensaje)

    def test_mensajes_ordenados_cronologicamente(self):
        """Test: Los mensajes se devuelven en orden cronológico."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        mensajes = data['mensajes']

        # Verificar orden ascendente de timestamps
        for i in range(len(mensajes) - 1):
            ts_actual = mensajes[i]['momento']
            ts_siguiente = mensajes[i + 1]['momento']
            self.assertLess(ts_actual, ts_siguiente)

    def test_respuesta_vacia_para_sesion_sin_mensajes(self):
        """Test: Sesión sin mensajes devuelve lista vacía."""
        otra_sesion = SesionTour.objects.create(
            codigo_acceso='VACIA001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[otra_sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['total'], 0)
        self.assertEqual(len(data['mensajes']), 0)

    # ======================================================================
    # Tests del filtro "limite"
    # ======================================================================

    def test_limite_default_es_50(self):
        """Test: Sin especificar límite, se devuelven hasta 50 mensajes."""
        # Crear 60 mensajes
        for i in range(55):
            MensajeChat.objects.create(
                sesion_tour=self.sesion,
                remitente=self.user_guia,
                nombre_remitente='Guía',
                texto=f'Mensaje extra {i}'
            )

        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data['mensajes']), 50)

    def test_limite_personalizado(self):
        """Test: Se respeta el parámetro limite."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'limite': '3'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data['mensajes']), 3)

    def test_limite_minimo_aceptado(self):
        """Test: Límite mínimo de 1 es aceptado."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'limite': '1'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data['mensajes']), 1)

    def test_limite_maximo_aceptado(self):
        """Test: Límite máximo de 200 es aceptado."""
        # Crear más de 200 mensajes
        for i in range(210):
            MensajeChat.objects.create(
                sesion_tour=self.sesion,
                remitente=self.user_guia,
                nombre_remitente='Guía',
                texto=f'Msg {i}'
            )

        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'limite': '200'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data['mensajes']), 200)

    def test_limite_fuera_de_rango_rechazado(self):
        """Test: Límite < 1 retorna error."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'limite': '0'}
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)

    def test_limite_superior_a_200_rechazado(self):
        """Test: Límite > 200 retorna error."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'limite': '201'}
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('200', data['error'])

    def test_limite_no_numerico_rechazado(self):
        """Test: Límite no numérico es rechazado."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'limite': 'abc'}
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('entero', data['error'].lower())

    # ======================================================================
    # Tests del filtro "desde"
    # ======================================================================

    def test_filtro_desde_valido(self):
        """Test: Parámetro desde filtra mensajes posteriores a fecha dada."""
        # Obtener timestamp del tercer mensaje
        ts_filtro = self.messages_data[2].momento.isoformat()

        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'desde': ts_filtro}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Solo últimos 2 mensajes (índices 3 y 4)
        self.assertEqual(data['total'], 2)

        # Verificar que son posteriores al timestamp
        for msg in data['mensajes']:
            msg_ts = msg['momento']
            self.assertGreater(msg_ts, ts_filtro)

    def test_filtro_desde_sin_resultados(self):
        """Test: Filtro desde sin coincidencias devuelve lista vacía."""
        futuro = (timezone.now() + timedelta(hours=1)).isoformat()

        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'desde': futuro}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['total'], 0)

    def test_filtro_desde_invalido_rechazado(self):
        """Test: Fecha ISO-8601 inválida es rechazada."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'desde': 'fecha-invalida'}
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('ISO-8601', data['error'])

    def test_filtro_desde_y_limite_combinados(self):
        """Test: Filtros desde y limite se aplican juntos."""
        ts_filtro = self.messages_data[1].momento.isoformat()

        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'desde': ts_filtro, 'limite': '2'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Debería ser máximo 2 mensajes posteriores al timestamp
        self.assertLessEqual(len(data['mensajes']), 2)

    # ======================================================================
    # Tests de autorización
    # ======================================================================

    def test_usuario_anonimo_no_puede_obtener_mensajes(self):
        """Test: Usuario sin autentificar y sin sesión no tiene acceso."""
        response = self.client_anonimo.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('error', data)

    def test_turista_inactivo_no_puede_obtener(self):
        """Test: Turista marcado como inactivo no puede obtener mensajes."""
        # Desactivar turista
        ts = TuristaSesion.objects.get(
            turista=self.turista,
            sesion_tour=self.sesion
        )
        ts.activo = False
        ts.save()

        response = self.client_turista.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 403)

    def test_turista_no_puede_obtener_de_otra_sesion(self):
        """Test: Turista no puede obtener mensajes de otra sesión."""
        otra_sesion = SesionTour.objects.create(
            codigo_acceso='OTRA001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

        response = self.client_turista.get(
            reverse('tours:obtener_mensajes', args=[otra_sesion.id])
        )

        self.assertEqual(response.status_code, 403)

    # ======================================================================
    # Tests de sesión inexistente
    # ======================================================================

    def test_sesion_inexistente_retorna_404(self):
        """Test: Sesión que no existe retorna 404."""
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[99999])
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('no existe', data['error'].lower())

    # ======================================================================
    # Tests integradores guía-turista
    # ======================================================================

    def test_guia_envia_turista_obtiene(self):
        """Test: Turista obtiene messages enviados por guía."""
        # Guía envía mensaje
        send_response = self.client_guia.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Mensaje guía a turista'}),
            content_type='application/json'
        )

        self.assertEqual(send_response.status_code, 201)

        # Turista obtiene mensajes
        get_response = self.client_turista.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(get_response.status_code, 200)
        data = get_response.json()

        # Verificar que está en la lista
        self.assertTrue(
            any(
                msg['texto'] == 'Mensaje guía a turista'
                for msg in data['mensajes']
            )
        )

    def test_turista_envia_guia_obtiene(self):
        """Test: Guía obtiene mensajes enviados por turista."""
        # Turista envía mensaje
        send_response = self.client_turista.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': 'Pregunta del turista'}),
            content_type='application/json'
        )

        self.assertEqual(send_response.status_code, 201)

        # Guía obtiene mensajes
        get_response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(get_response.status_code, 200)
        data = get_response.json()

        # Verificar presencia
        self.assertTrue(
            any(
                msg['texto'] == 'Pregunta del turista'
                for msg in data['mensajes']
            )
        )

    def test_conversacion_completa(self):
        """Test: Conversación guía ↔ turista funciona correctamente."""
        mensajes_esperados = [
            ('Hola turistas', 'Guía', self.client_guia),
            ('¿Dónde estamos?', 'GetTurista', self.client_turista),
            ('Aquí está la parada', 'Guía', self.client_guia),
        ]

        for texto, remitente_esperado, cliente in mensajes_esperados:
            response = cliente.post(
                reverse('tours:enviar_mensaje', args=[self.sesion.id]),
                data=json.dumps({'texto': texto}),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 201)

        # Obtener todos los mensajes
        response = self.client_guia.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Debe contener al menos los 3 nuevos mensajes
        textos_obtenidos = [msg['texto'] for msg in data['mensajes']]

        for texto, _, _ in mensajes_esperados:
            self.assertIn(texto, textos_obtenidos)
