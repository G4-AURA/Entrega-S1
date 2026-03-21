"""
tests/test_chat_excepciones.py

Tests del sistema de control de excepciones del chat (S2.1-52).
Verifica que se controlen adecuadamente:
- Sesiones inexistentes
- Sesiones finalizadas
- Usuarios sin acceso a la sesión
- Mensajes inválidos
"""
import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import MensajeChat, SesionTour, Turista, TuristaSesion


class ChatExcepcionesTestCase(TestCase):
    """Tests de validaciones y excepciones del chat de sesión."""

    def setUp(self):
        """Configuración inicial para todos los tests."""
        # Crear usuario guía
        self.user_guia = User.objects.create_user(
            username='guia_test', password='test123'
        )
        auth_user = AuthUser.objects.create(user=self.user_guia)
        self.guia = Guia.objects.create(user=auth_user)

        # Crear ruta
        self.ruta = Ruta.objects.create(
            titulo='Ruta Test',
            descripcion='Descripción test',
            duracion_horas=2.5,
            num_personas=10,
            nivel_exigencia='Baja',
            mood=['Historia'],
            guia=self.guia
        )

        # Crear sesión activa
        self.sesion_activa = SesionTour.objects.create(
            codigo_acceso='ABC123',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta
        )

        # Crear sesión finalizada
        self.sesion_finalizada = SesionTour.objects.create(
            codigo_acceso='XYZ789',
            estado=SesionTour.FINALIZADO,
            fecha_inicio=timezone.now() - timedelta(hours=3),
            ruta=self.ruta
        )

        # Crear turista con acceso a la sesión activa
        self.turista = Turista.objects.create(alias='TuristaTest')
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion_activa,
            activo=True
        )

        # Cliente para requests
        self.client = Client()

    def test_enviar_mensaje_sesion_inexistente(self):
        """Test: Enviar mensaje a sesión inexistente debe devolver 404."""
        # Simular turista en sesión
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response = self.client.post(
            f'/tours/sesiones/99999/mensajes/enviar/',
            data=json.dumps({'texto': 'Hola'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('no existe', data['error'])

    def test_enviar_mensaje_sesion_finalizada(self):
        """Test: No se pueden enviar mensajes a sesiones finalizadas."""
        # Login como guía
        self.client.login(username='guia_test', password='test123')

        response = self.client.post(
            f'/tours/sesiones/{self.sesion_finalizada.id}/mensajes/enviar/',
            data=json.dumps({'texto': 'Mensaje a sesión finalizada'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('finalizada', data['error'])
        self.assertEqual(data['estado_sesion'], SesionTour.FINALIZADO)

        # Verificar que no se guardó el mensaje
        mensajes = MensajeChat.objects.filter(sesion_tour=self.sesion_finalizada)
        self.assertEqual(mensajes.count(), 0)

    def test_enviar_mensaje_sin_acceso(self):
        """Test: Usuario sin acceso no puede enviar mensajes."""
        # Crear otro turista sin acceso a la sesión
        turista_sin_acceso = Turista.objects.create(alias='SinAcceso')
        session = self.client.session
        session['turista_id'] = turista_sin_acceso.id
        session.save()

        response = self.client.post(
            f'/tours/sesiones/{self.sesion_activa.id}/mensajes/enviar/',
            data=json.dumps({'texto': 'Intento sin acceso'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('error', data)
        self.assertTrue('permiso' in data['error'] or 'perteneces' in data['error'])

        # Verificar que no se guardó el mensaje
        mensajes = MensajeChat.objects.filter(
            sesion_tour=self.sesion_activa,
            texto='Intento sin acceso'
        )
        self.assertEqual(mensajes.count(), 0)

    def test_enviar_mensaje_texto_vacio(self):
        """Test: No se pueden enviar mensajes vacíos."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response = self.client.post(
            f'/tours/sesiones/{self.sesion_activa.id}/mensajes/enviar/',
            data=json.dumps({'texto': '   '}),  # Solo espacios
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('vacío', data['error'])

    def test_enviar_mensaje_json_invalido(self):
        """Test: JSON malformado debe devolver 400."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response = self.client.post(
            f'/tours/sesiones/{self.sesion_activa.id}/mensajes/enviar/',
            data='{"texto": "hola"',  # JSON inválido
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('JSON', data['error'])

    def test_enviar_mensaje_muy_largo(self):
        """Test: Mensajes demasiado largos deben ser rechazados."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        texto_largo = 'A' * 5001  # Más de 5000 caracteres

        response = self.client.post(
            f'/tours/sesiones/{self.sesion_activa.id}/mensajes/enviar/',
            data=json.dumps({'texto': texto_largo}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('largo', data['error'])

    def test_enviar_mensaje_exitoso(self):
        """Test: Mensaje válido se guarda correctamente."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        texto = 'Hola, este es un mensaje válido'
        response = self.client.post(
            f'/tours/sesiones/{self.sesion_activa.id}/mensajes/enviar/',
            data=json.dumps({'texto': texto}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('mensaje_id', data)
        self.assertIn('momento', data)

        # Verificar que el mensaje se guardó
        mensaje = MensajeChat.objects.get(id=data['mensaje_id'])
        self.assertEqual(mensaje.texto, texto)
        self.assertEqual(mensaje.sesion_tour, self.sesion_activa)

    def test_obtener_mensajes_sesion_inexistente(self):
        """Test: Obtener mensajes de sesión inexistente devuelve 404."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response = self.client.get('/tours/sesiones/99999/mensajes/')

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('no existe', data['error'])

    def test_obtener_mensajes_sin_acceso(self):
        """Test: Usuario sin acceso no puede obtener mensajes."""
        turista_sin_acceso = Turista.objects.create(alias='SinAcceso2')
        session = self.client.session
        session['turista_id'] = turista_sin_acceso.id
        session.save()

        response = self.client.get(
            f'/tours/sesiones/{self.sesion_activa.id}/mensajes/'
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('acceso', data['error'].lower())

    def test_obtener_mensajes_fecha_invalida(self):
        """Test: Parámetro 'desde' con formato inválido devuelve 400."""
        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response = self.client.get(
            f'/tours/sesiones/{self.sesion_activa.id}/mensajes/?desde=fecha-invalida'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('iso', data['error'].lower())

    def test_obtener_mensajes_exitoso(self):
        """Test: Obtener mensajes con acceso válido funciona correctamente."""
        # Crear algunos mensajes
        MensajeChat.objects.create(
            sesion_tour=self.sesion_activa,
            nombre_remitente='TuristaTest',
            texto='Mensaje 1'
        )
        MensajeChat.objects.create(
            sesion_tour=self.sesion_activa,
            nombre_remitente='GuiaTest',
            texto='Mensaje 2'
        )

        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response = self.client.get(
            f'/tours/sesiones/{self.sesion_activa.id}/mensajes/'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('mensajes', data)
        self.assertIn('total', data)
        self.assertIn('estado_sesion', data)
        self.assertEqual(len(data['mensajes']), 2)
        self.assertEqual(data['total'], 2)

    def test_obtener_mensajes_sesion_finalizada_permitido(self):
        """
        Test: Se permite consultar el historial de mensajes de sesiones
        finalizadas para usuarios que tuvieron acceso.
        """
        # Agregar turista a sesión finalizada
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion_finalizada,
            activo=True
        )

        # Crear mensaje en sesión finalizada
        MensajeChat.objects.create(
            sesion_tour=self.sesion_finalizada,
            nombre_remitente='TuristaTest',
            texto='Mensaje histórico'
        )

        session = self.client.session
        session['turista_id'] = self.turista.id
        session.save()

        response = self.client.get(
            f'/tours/sesiones/{self.sesion_finalizada.id}/mensajes/'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['estado_sesion'], SesionTour.FINALIZADO)
        self.assertEqual(len(data['mensajes']), 1)

    def test_guia_puede_enviar_mensaje(self):
        """Test: El guía puede enviar mensajes a su sesión."""
        self.client.login(username='guia_test', password='test123')

        response = self.client.post(
            f'/tours/sesiones/{self.sesion_activa.id}/mensajes/enviar/',
            data=json.dumps({'texto': 'Mensaje del guía'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['status'], 'ok')

    def test_guia_no_puede_enviar_a_sesion_ajena(self):
        """Test: El guía no puede enviar mensajes a sesiones de otros guías."""
        # Crear otro guía y su sesión
        otro_user = User.objects.create_user(username='otro_guia', password='test123')
        otro_auth = AuthUser.objects.create(user=otro_user)
        otro_guia = Guia.objects.create(user=otro_auth)
        
        otra_ruta = Ruta.objects.create(
            titulo='Otra Ruta',
            descripcion='Test',
            duracion_horas=2,
            num_personas=5,
            nivel_exigencia='Media',
            mood=['Naturaleza'],
            guia=otro_guia
        )
        
        otra_sesion = SesionTour.objects.create(
            codigo_acceso='OTR999',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=otra_ruta
        )

        # Intentar enviar como el primer guía a la sesión del segundo
        self.client.login(username='guia_test', password='test123')

        response = self.client.post(
            f'/tours/sesiones/{otra_sesion.id}/mensajes/enviar/',
            data=json.dumps({'texto': 'Intento no autorizado'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('permiso', data['error'])
