from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import SESION_TOUR, TURISTA, UBICACION_VIVO, MENSAJE_CHAT
from rutas.models import Ruta, Guia 
from .tasks import barrido_mensajes_efimeros


class SessionLogicEndpointsTests(TestCase):
    def setUp(self):
        self.guia = User.objects.create_user(username='guia_test', password='1234')
        self.turista_user = User.objects.create_user(username='turista_test', password='1234')
        self.turista = TURISTA.objects.create(user=self.turista_user, alias='turista1')
        
        self.guia_perfil = Guia.objects.create()
        self.ruta = Ruta.objects.create(
            titulo='Ruta Test', 
            duracion_horas=1.0, 
            num_personas=10,
            nivel_exigencia='Baja',
            guia=self.guia_perfil
        )

        self.sesion = SESION_TOUR.objects.create(
            codigo_acceso='TMP001',
            estado='pendiente',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

    def test_iniciar_tour_cambia_estado_y_generacodigo(self):
        client = Client()
        client.force_login(self.guia)

        response = client.post(reverse('tours:iniciar_tour', args=[self.sesion.id]))

        self.assertEqual(response.status_code, 200)
        self.sesion.refresh_from_db()
        data = response.json()
        self.assertEqual(self.sesion.estado, 'en_curso')
        self.assertTrue(data['codigo_acceso'])
        self.assertEqual(data['estado'], 'en_curso')

    def test_iniciar_tour_requiere_autenticacion(self):
        client = Client()

        response = client.post(reverse('tours:iniciar_tour', args=[self.sesion.id]))

        self.assertEqual(response.status_code, 401)

    def test_iniciar_tour_finalizado_devuelve_error(self):
        client = Client()
        client.force_login(self.guia)
        self.sesion.estado = 'finalizado'
        self.sesion.save(update_fields=['estado'])

        response = client.post(reverse('tours:iniciar_tour', args=[self.sesion.id]))

        self.assertEqual(response.status_code, 400)

    def test_unirse_tour_ok_agrega_turista(self):
        client = Client()
        client.force_login(self.turista_user)
        self.sesion.estado = 'en_curso'
        self.sesion.codigo_acceso = 'ABC123'
        self.sesion.save(update_fields=['estado', 'codigo_acceso'])

        response = client.post(
            reverse('tours:unirse_tour'),
            data='{"codigo_acceso": "ABC123"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.sesion.turistas.filter(pk=self.turista.pk).exists())

    def test_unirse_tour_codigo_invalido(self):
        client = Client()
        client.force_login(self.turista_user)
        self.sesion.estado = 'en_curso'
        self.sesion.save(update_fields=['estado'])

        response = client.post(
            reverse('tours:unirse_tour'),
            data='{"codigo_acceso": "INVALID"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)

    def test_unirse_tour_requiere_perfil_turista(self):
        user_sin_perfil = User.objects.create_user(username='sinperfil', password='1234')
        client = Client()
        client.force_login(user_sin_perfil)
        self.sesion.estado = 'en_curso'
        self.sesion.codigo_acceso = 'XYZ123'
        self.sesion.save(update_fields=['estado', 'codigo_acceso'])

        response = client.post(
            reverse('tours:unirse_tour'),
            data='{"codigo_acceso": "XYZ123"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)

    def test_unirse_tour_sesion_no_activa(self):
        client = Client()
        client.force_login(self.turista_user)

        response = client.post(
            reverse('tours:unirse_tour'),
            data='{"codigo_acceso": "TMP001"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)


class TrackingEndpointsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='track_user', password='1234')
        
        self.guia_perfil = Guia.objects.create()
        self.ruta = Ruta.objects.create(
            titulo='Ruta Tracking', 
            duracion_horas=1.0, 
            num_personas=10,
            nivel_exigencia='Baja',
            guia=self.guia_perfil
        )
        
        self.sesion = SESION_TOUR.objects.create(
            codigo_acceso='TRK001',
            estado='en_curso',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

    def test_registrar_ubicacion_crea_registro(self):
        client = Client()
        client.force_login(self.user)

        response = client.post(
            '/api/ubicacion/',
            data='{"sesion_id": %d, "latitud": 37.3891, "longitud": -5.9845}' % self.sesion.id,
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(UBICACION_VIVO.objects.count(), 1)
        ubicacion = UBICACION_VIVO.objects.first()
        self.assertEqual(ubicacion.sesion_tour_id, self.sesion.id)
        self.assertEqual(ubicacion.usuario_id, self.user.id)
        self.assertAlmostEqual(ubicacion.coordenadas.y, 37.3891, places=4)
        self.assertAlmostEqual(ubicacion.coordenadas.x, -5.9845, places=4)

    def test_registrar_ubicacion_requiere_autenticacion(self):
        client = Client()

        response = client.post(
            '/api/ubicacion/',
            data='{"sesion_id": %d, "latitud": 37.3891, "longitud": -5.9845}' % self.sesion.id,
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 401)

    def test_registrar_ubicacion_valida_campos_obligatorios(self):
        client = Client()
        client.force_login(self.user)

        response = client.post(
            '/api/ubicacion/',
            data='{"latitud": 37.3891, "longitud": -5.9845}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    def test_registrar_ubicacion_valida_rango(self):
        client = Client()
        client.force_login(self.user)

        response = client.post(
            '/api/ubicacion/',
            data='{"sesion_id": %d, "latitud": 120.0, "longitud": -5.9845}' % self.sesion.id,
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)


class ChatCeleryTestCase(TestCase):
    def setUp(self):
        self.guia_perfil = Guia.objects.create()
        self.user_chat = User.objects.create_user(username='tester_chat', password='123')
        self.ruta = Ruta.objects.create(
            titulo="Ruta Test", 
            duracion_horas=1.0, 
            num_personas=5,
            nivel_exigencia="Baja",
            guia=self.guia_perfil
        )
        
        self.sesion = SESION_TOUR.objects.create(
            codigo_acceso="UNIT-TEST",
            ruta=self.ruta,
            fecha_inicio=timezone.now(),
            estado="en_curso" 
        )

    def test_creacion_mensaje_y_asociacion_tour(self):
        """Prueba Unitaria: Comprueba la correcta creación y asociación a un tour activo."""
        mensaje = MENSAJE_CHAT.objects.create(
            sesion_tour=self.sesion,
            remitente=self.user_chat,
            texto="Hola, este es un mensaje de prueba"
        )
        
        self.assertEqual(MENSAJE_CHAT.objects.count(), 1)
        self.assertEqual(mensaje.sesion_tour.id, self.sesion.id)
        self.assertEqual(mensaje.sesion_tour.estado, 'en_curso') 
        self.assertEqual(mensaje.remitente.username, 'tester_chat')

    def test_tarea_celery_borrado_efectivo(self):
        """Prueba de Integración: Asegura que la tarea asíncrona limpia la base de datos."""
        MENSAJE_CHAT.objects.create(sesion_tour=self.sesion, remitente=self.user_chat, texto="Mensaje 1")
        MENSAJE_CHAT.objects.create(sesion_tour=self.sesion, remitente=self.user_chat, texto="Mensaje 2")
        self.assertEqual(MENSAJE_CHAT.objects.count(), 2)
        
        self.sesion.estado = "finalizado"
        self.sesion.save(update_fields=['estado'])
        
        barrido_mensajes_efimeros(self.sesion.id)
        
        self.assertEqual(MENSAJE_CHAT.objects.count(), 0)