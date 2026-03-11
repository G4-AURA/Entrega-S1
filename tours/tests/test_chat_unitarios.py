"""
tests/test_chat_unitarios.py

Tests unitarios del sistema de chat (S2.1-54).
Valida:
- Almacenamiento correcto de mensajes
- Autorización de usuarios
- Manejo de excepciones
- Lógica de negocio del chat
"""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import MensajeChat, SesionTour, Turista, TuristaSesion
from tours import services


class MensajeChatModelTest(TestCase):
    """Tests unitarios del modelo MensajeChat."""

    def setUp(self):
        """Configuración inicial."""
        self.user_guia = User.objects.create_user(
            username='guia_model_test', password='test123'
        )
        auth_user = AuthUser.objects.create(user=self.user_guia)
        self.guia = Guia.objects.create(user=auth_user)

        self.ruta = Ruta.objects.create(
            titulo='Ruta Model Test',
            descripcion='Test',
            duracion_horas=2,
            num_personas=5,
            nivel_exigencia='Media',
            mood=['Aventura'],
            guia=self.guia
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso='MDL123',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

    def test_mensaje_se_crea_correctamente(self):
        """Test: Verificar que un mensaje se almacena con todos sus campos."""
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            remitente=self.user_guia,
            nombre_remitente='Guía Test',
            texto='Hola a todos',
        )

        # Verificar que se guardó
        self.assertIsNotNone(mensaje.id)
        self.assertEqual(mensaje.sesion_tour, self.sesion)
        self.assertEqual(mensaje.remitente, self.user_guia)
        self.assertEqual(mensaje.nombre_remitente, 'Guía Test')
        self.assertEqual(mensaje.texto, 'Hola a todos')
        self.assertIsNotNone(mensaje.momento)

        # Verificar que se puede recuperar
        mensaje_db = MensajeChat.objects.get(id=mensaje.id)
        self.assertEqual(mensaje_db.texto, 'Hola a todos')

    def test_mensaje_turista_anonimo(self):
        """Test: Mensaje de turista anónimo (sin remitente User)."""
        turista = Turista.objects.create(alias='TuristaAnon')
        
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=turista,
            nombre_remitente=turista.alias,
            texto='Mensaje anónimo',
        )

        self.assertIsNone(mensaje.remitente)
        self.assertEqual(mensaje.turista, turista)
        self.assertEqual(mensaje.nombre_remitente, 'TuristaAnon')

    def test_mensaje_con_texto_largo(self):
        """Test: Almacenar mensaje con texto extenso."""
        texto_largo = 'A' * 4000
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            nombre_remitente='Usuario',
            texto=texto_largo,
        )

        self.assertEqual(len(mensaje.texto), 4000)
        mensaje_db = MensajeChat.objects.get(id=mensaje.id)
        self.assertEqual(len(mensaje_db.texto), 4000)

    def test_mensaje_momento_auto_now_add(self):
        """Test: El campo momento se establece automáticamente."""
        antes = timezone.now()
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            nombre_remitente='Test',
            texto='Mensaje temporal',
        )
        despues = timezone.now()

        self.assertGreaterEqual(mensaje.momento, antes)
        self.assertLessEqual(mensaje.momento, despues)

    def test_multiples_mensajes_misma_sesion(self):
        """Test: Una sesión puede tener múltiples mensajes."""
        MensajeChat.objects.create(
            sesion_tour=self.sesion,
            nombre_remitente='Usuario1',
            texto='Mensaje 1'
        )
        MensajeChat.objects.create(
            sesion_tour=self.sesion,
            nombre_remitente='Usuario2',
            texto='Mensaje 2'
        )
        MensajeChat.objects.create(
            sesion_tour=self.sesion,
            nombre_remitente='Usuario3',
            texto='Mensaje 3'
        )

        mensajes = MensajeChat.objects.filter(sesion_tour=self.sesion)
        self.assertEqual(mensajes.count(), 3)

    def test_relacionado_inverso_sesion_mensajes(self):
        """Test: Acceso a mensajes desde la sesión (related_name)."""
        MensajeChat.objects.create(
            sesion_tour=self.sesion,
            nombre_remitente='Test',
            texto='Mensaje 1'
        )
        MensajeChat.objects.create(
            sesion_tour=self.sesion,
            nombre_remitente='Test',
            texto='Mensaje 2'
        )

        # Usar related_name='mensajes'
        mensajes = self.sesion.mensajes.all()
        self.assertEqual(mensajes.count(), 2)

    def test_mensaje_str_representation(self):
        """Test: Representación en string del mensaje."""
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            nombre_remitente='TestUser',
            texto='Hola mundo'
        )

        str_repr = str(mensaje)
        # Verificar que contiene información útil
        self.assertIsNotNone(str_repr)


class ChatServicesTest(TestCase):
    """Tests de los servicios relacionados con el chat."""

    def setUp(self):
        """Configuración inicial."""
        self.user_guia = User.objects.create_user(
            username='guia_services', password='test123'
        )
        auth_user = AuthUser.objects.create(user=self.user_guia)
        self.guia = Guia.objects.create(user=auth_user)

        self.ruta = Ruta.objects.create(
            titulo='Ruta Services',
            descripcion='Test',
            duracion_horas=2,
            num_personas=5,
            nivel_exigencia='Baja',
            mood=['Relax'],
            guia=self.guia
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso='SRV123',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

        self.turista = Turista.objects.create(alias='TuristaServices')
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
            activo=True
        )

    def test_es_guia_de_sesion_verdadero(self):
        """Test: Verificar que identifica correctamente al guía."""
        result = services.es_guia_de_sesion(self.user_guia, self.sesion)
        self.assertTrue(result)

    def test_es_guia_de_sesion_falso(self):
        """Test: Usuario que no es guía de la sesión."""
        otro_user = User.objects.create_user(username='otro', password='123')
        result = services.es_guia_de_sesion(otro_user, self.sesion)
        self.assertFalse(result)

    def test_obtener_turista_anonimo_con_cookie(self):
        """Test: Resolver turista desde request con cookie."""
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.session = {'turista_id': self.turista.id}

        turista = services.obtener_turista_anonimo(request)
        self.assertEqual(turista, self.turista)

    def test_obtener_turista_anonimo_sin_cookie(self):
        """Test: Sin cookie debe retornar None."""
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.session = {}

        turista = services.obtener_turista_anonimo(request)
        self.assertIsNone(turista)

    def test_obtener_turista_anonimo_id_invalido(self):
        """Test: Cookie con ID inexistente retorna None."""
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.session = {'turista_id': 99999}

        turista = services.obtener_turista_anonimo(request)
        self.assertIsNone(turista)

    def test_tiene_acceso_guia(self):
        """Test: El guía tiene acceso a su sesión."""
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user_guia
        request.session = {}

        tiene_acceso = services.tiene_acceso_a_sesion(request, self.sesion)
        self.assertTrue(tiene_acceso)

    def test_tiene_acceso_turista_activo(self):
        """Test: Turista activo tiene acceso."""
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        request.session = {'turista_id': self.turista.id}

        tiene_acceso = services.tiene_acceso_a_sesion(request, self.sesion)
        self.assertTrue(tiene_acceso)

    def test_no_tiene_acceso_turista_inactivo(self):
        """Test: Turista desactivado no tiene acceso."""
        # Desactivar turista
        ts = TuristaSesion.objects.get(turista=self.turista, sesion_tour=self.sesion)
        ts.activo = False
        ts.save()

        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        request.session = {'turista_id': self.turista.id}

        tiene_acceso = services.tiene_acceso_a_sesion(request, self.sesion)
        self.assertFalse(tiene_acceso)

    def test_determinar_remitente_guia(self):
        """Test: Determinar remitente del guía autenticado."""
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user_guia
        request.session = {}

        remitente_user, remitente_turista, nombre, error = services.determinar_remitente(request, self.sesion)
        # Debería retornar el user del guía
        self.assertEqual(remitente_user, self.user_guia)
        self.assertIsNone(remitente_turista)
        self.assertIsNotNone(nombre)
        self.assertIsNone(error)

    def test_determinar_remitente_turista(self):
        """Test: Determinar remitente del turista anónimo."""
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        request.session = {'turista_id': self.turista.id}

        remitente_user, remitente_turista, nombre, error = services.determinar_remitente(request, self.sesion)
        # Debería retornar el turista
        self.assertIsNone(remitente_user)
        self.assertEqual(remitente_turista, self.turista)
        self.assertEqual(nombre, 'TuristaServices')
        self.assertIsNone(error)


class ChatIntegrationTest(TestCase):
    """Tests de integración del flujo completo del chat."""

    def setUp(self):
        """Configuración inicial."""
        self.user_guia = User.objects.create_user(
            username='guia_integration', password='test123'
        )
        auth_user = AuthUser.objects.create(user=self.user_guia)
        self.guia = Guia.objects.create(user=auth_user)

        self.ruta = Ruta.objects.create(
            titulo='Ruta Integration',
            descripcion='Test',
            duracion_horas=2,
            num_personas=5,
            nivel_exigencia='Media',
            mood=['Historia'],
            guia=self.guia
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso='INT123',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

        self.turista = Turista.objects.create(alias='TuristaInt')
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
            activo=True
        )

        self.client = Client()

    def test_flujo_completo_enviar_y_obtener(self):
        """Test: Enviar mensaje y luego recuperarlo."""
        # 1. Simular turista y enviar mensaje
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response_enviar = self.client.post(
            f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
            data=json.dumps({'texto': 'Mensaje de prueba'}),
            content_type='application/json'
        )

        self.assertEqual(response_enviar.status_code, 201)
        data_enviar = response_enviar.json()
        mensaje_id = data_enviar['mensaje_id']

        # 2. Obtener mensajes
        response_obtener = self.client.get(
            f'/tours/sesiones/{self.sesion.id}/mensajes/'
        )

        self.assertEqual(response_obtener.status_code, 200)
        data_obtener = response_obtener.json()
        self.assertIn('mensajes', data_obtener)
        self.assertEqual(len(data_obtener['mensajes']), 1)
        self.assertEqual(data_obtener['mensajes'][0]['id'], mensaje_id)
        self.assertEqual(data_obtener['mensajes'][0]['texto'], 'Mensaje de prueba')

    def test_orden_cronologico_mensajes(self):
        """Test: Los mensajes se devuelven en orden cronológico."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        # Crear 3 mensajes con pequeñas diferencias de tiempo
        textos = ['Primero', 'Segundo', 'Tercero']
        for texto in textos:
            self.client.post(
                f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
                data=json.dumps({'texto': texto}),
                content_type='application/json'
            )

        # Obtener mensajes
        response = self.client.get(
            f'/tours/sesiones/{self.sesion.id}/mensajes/'
        )

        mensajes = response.json()['mensajes']
        self.assertEqual(len(mensajes), 3)
        self.assertEqual(mensajes[0]['texto'], 'Primero')
        self.assertEqual(mensajes[1]['texto'], 'Segundo')
        self.assertEqual(mensajes[2]['texto'], 'Tercero')

    def test_filtro_desde_fecha(self):
        """Test: Filtrar mensajes por parámetro 'desde'."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        # Crear primer mensaje directamente en la base de datos con momento específico
        from datetime import datetime, timezone as tz
        momento1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=tz.utc)
        mensaje1 = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            nombre_remitente=self.turista.alias,
            texto='Mensaje antiguo',
        )
        # Actualizar el momento manualmente
        MensajeChat.objects.filter(id=mensaje1.id).update(momento=momento1)

        # Crear segundo mensaje con momento posterior
        momento2 = datetime(2024, 1, 1, 13, 0, 0, tzinfo=tz.utc)
        mensaje2 = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            nombre_remitente=self.turista.alias,
            texto='Mensaje nuevo',
        )
        MensajeChat.objects.filter(id=mensaje2.id).update(momento=momento2)

        # Obtener todos los mensajes (debería retornar ambos)
        response_todos = self.client.get(
            f'/tours/sesiones/{self.sesion.id}/mensajes/'
        )
        self.assertEqual(response_todos.status_code, 200)
        todos_mensajes = response_todos.json()['mensajes']
        self.assertEqual(len(todos_mensajes), 2)

        # Filtrar por fecha en medio (después del primero, antes del segundo)
        momento_corte = '2024-01-01T12:30:00'
        response_filtrado = self.client.get(
            f'/tours/sesiones/{self.sesion.id}/mensajes/?desde={momento_corte}'
        )

        self.assertEqual(response_filtrado.status_code, 200)
        data = response_filtrado.json()
        mensajes_filtrados = data['mensajes']
        
        # Debería retornar solo el segundo mensaje
        self.assertEqual(len(mensajes_filtrados), 1)
        self.assertEqual(mensajes_filtrados[0]['texto'], 'Mensaje nuevo')

    def test_conversacion_guia_turista(self):
        """Test: Intercambio de mensajes entre guía y turista."""
        # Turista envía mensaje
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        self.client.post(
            f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
            data=json.dumps({'texto': 'Pregunta del turista'}),
            content_type='application/json'
        )

        # Guía responde
        self.client.login(username='guia_integration', password='test123')
        self.client.post(
            f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
            data=json.dumps({'texto': 'Respuesta del guía'}),
            content_type='application/json'
        )

        # Obtener conversación
        response = self.client.get(
            f'/tours/sesiones/{self.sesion.id}/mensajes/'
        )

        mensajes = response.json()['mensajes']
        self.assertEqual(len(mensajes), 2)
        self.assertEqual(mensajes[0]['texto'], 'Pregunta del turista')
        self.assertEqual(mensajes[1]['texto'], 'Respuesta del guía')

    def test_varios_turistas_en_chat(self):
        """Test: Varios turistas pueden participar en el mismo chat."""
        # Crear segundo turista
        turista2 = Turista.objects.create(alias='Turista2')
        TuristaSesion.objects.create(
            turista=turista2,
            sesion_tour=self.sesion,
            activo=True
        )

        # Primer turista envía
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        self.client.post(
            f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
            data=json.dumps({'texto': 'Mensaje de turista 1'}),
            content_type='application/json'
        )

        # Segundo turista envía
        session['turista_id'] = turista2.id
        session.save()

        self.client.post(
            f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
            data=json.dumps({'texto': 'Mensaje de turista 2'}),
            content_type='application/json'
        )

        # Ambos pueden ver todos los mensajes
        response = self.client.get(
            f'/tours/sesiones/{self.sesion.id}/mensajes/'
        )

        mensajes = response.json()['mensajes']
        self.assertEqual(len(mensajes), 2)


class ChatEdgeCasesTest(TestCase):
    """Tests de casos límite y situaciones especiales."""

    def setUp(self):
        """Configuración inicial."""
        self.user_guia = User.objects.create_user(
            username='guia_edge', password='test123'
        )
        auth_user = AuthUser.objects.create(user=self.user_guia)
        self.guia = Guia.objects.create(user=auth_user)

        self.ruta = Ruta.objects.create(
            titulo='Ruta Edge',
            descripcion='Test',
            duracion_horas=2,
            num_personas=5,
            nivel_exigencia='Alta',
            mood=['Aventura'],
            guia=self.guia
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso='EDG123',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

        self.turista = Turista.objects.create(alias='TuristaEdge')
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
            activo=True
        )

        self.client = Client()

    def test_mensaje_con_caracteres_especiales(self):
        """Test: Mensajes con emojis y caracteres especiales."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        texto_especial = "¡Hola! 😊 ¿Cómo están? #TourÉpico @guía"
        
        response = self.client.post(
            f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
            data=json.dumps({'texto': texto_especial}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)

        # Verificar que se guardó correctamente
        mensaje = MensajeChat.objects.latest('momento')
        self.assertEqual(mensaje.texto, texto_especial)

    def test_sesion_sin_mensajes(self):
        """Test: Obtener mensajes de sesión vacía."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response = self.client.get(
            f'/tours/sesiones/{self.sesion.id}/mensajes/'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['mensajes']), 0)
        self.assertEqual(data['total'], 0)

    def test_mensaje_con_saltos_de_linea(self):
        """Test: Mensaje con múltiples líneas."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        texto_multilinea = "Línea 1\nLínea 2\nLínea 3"
        
        response = self.client.post(
            f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
            data=json.dumps({'texto': texto_multilinea}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)

        # Verificar preservación de saltos
        mensaje = MensajeChat.objects.latest('momento')
        self.assertIn('\n', mensaje.texto)

    def test_mensaje_exactamente_5000_caracteres(self):
        """Test: Mensaje con longitud límite exacta."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        texto_limite = 'A' * 5000
        
        response = self.client.post(
            f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
            data=json.dumps({'texto': texto_limite}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)

    def test_campo_texto_faltante(self):
        """Test: Request sin campo 'texto'."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response = self.client.post(
            f'/tours/sesiones/{self.sesion.id}/mensajes/enviar/',
            data=json.dumps({}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
