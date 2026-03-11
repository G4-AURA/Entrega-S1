from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from rutas.models import AuthUser, Guia, Ruta
from tours.tasks import barrido_mensajes_efimeros
from tours.models import MENSAJE_CHAT, SESION_TOUR, TURISTA, TURISTASESION, UBICACION_VIVO


class SessionLogicEndpointsTests(TestCase):
    def setUp(self):
        self.guia = User.objects.create_user(username='guia_test', password='1234')
        self.turista_user = User.objects.create_user(username='turista_test', password='1234')
        self.turista = TURISTA.objects.create(user=self.turista_user, alias='turista1')
        auth_guia = AuthUser.objects.create(user=self.guia)
        guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Test',
            descripcion='Descripción de prueba',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
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

        self.assertEqual(response.status_code, 302)

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
        self.turista = TURISTA.objects.create(user=self.user, alias='track_turista')

        guia_user = User.objects.create_user(username='track_guia', password='1234')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Tracking',
            descripcion='Tracking test',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SESION_TOUR.objects.create(
            codigo_acceso='TRK001',
            estado='en_curso',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.sesion.turistas.add(self.turista)

    def test_registrar_ubicacion_crea_registro(self):
        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse('tours:registrar_ubicacion'),
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
            reverse('tours:registrar_ubicacion'),
            data='{"sesion_id": %d, "latitud": 37.3891, "longitud": -5.9845}' % self.sesion.id,
            content_type='application/json',
        )

        expected_login_url = reverse('login')
        expected_next = reverse('tours:registrar_ubicacion')
        self.assertRedirects(response, f"{expected_login_url}?next={expected_next}")

    def test_registrar_ubicacion_valida_campos_obligatorios(self):
        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse('tours:registrar_ubicacion'),
            data='{"latitud": 37.3891, "longitud": -5.9845}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    def test_registrar_ubicacion_valida_rango(self):
        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse('tours:registrar_ubicacion'),
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
    
    def test_tarea_celery_no_borra_si_activa(self):
        """Prueba de Seguridad: La tarea ignora el borrado si el tour sigue en curso."""
        MENSAJE_CHAT.objects.create(
            sesion_tour=self.sesion, 
            remitente=self.user_chat, 
            texto="Este mensaje está a salvo"
        )
        resultado = barrido_mensajes_efimeros(self.sesion.id)
        self.assertEqual(MENSAJE_CHAT.objects.count(), 1)
        self.assertIn("Operación cancelada", resultado)


class ChatApiValidationTests(TestCase):
    def setUp(self):
        self.guia_user = User.objects.create_user(username='chat_guia', password='1234')
        self.no_participante = User.objects.create_user(username='chat_intruso', password='1234')

        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)

        self.ruta = Ruta.objects.create(
            titulo='Ruta Chat API',
            descripcion='Validaciones de chat',
            duracion_horas=1.5,
            num_personas=10,
            mood=['Historia'],
            guia=guia,
        )

        self.sesion = SESION_TOUR.objects.create(
            codigo_acceso='CHAT01',
            estado='en_curso',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.turista = TURISTA.objects.create(alias='anon-chat')
        TURISTASESION.objects.create(turista=self.turista, sesion_tour=self.sesion, activo=True)

        self.guia_client = Client()
        self.guia_client.force_login(self.guia_user)

        self.anon_client = Client()
        session = self.anon_client.session
        session['turista_id'] = self.turista.id
        session['turista_alias'] = self.turista.alias
        session.save()

        self.intruso_client = Client()
        self.intruso_client.force_login(self.no_participante)

    def test_enviar_mensaje_rechaza_texto_vacio(self):
        response = self.guia_client.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data='{"texto": "   "}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_enviar_mensaje_rechaza_usuario_sin_permiso(self):
        response = self.intruso_client.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data='{"texto": "mensaje"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_obtener_mensajes_aplica_limite_y_orden_cronologico(self):
        base = timezone.now() - timedelta(minutes=5)
        textos = ['m1', 'm2', 'm3']
        for idx, texto in enumerate(textos):
            mensaje = MENSAJE_CHAT.objects.create(
                sesion_tour=self.sesion,
                nombre_remitente='chat_guia',
                texto=texto,
            )
            MENSAJE_CHAT.objects.filter(id=mensaje.id).update(momento=base + timedelta(minutes=idx))

        response = self.anon_client.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'limite': '2'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total'], 2)
        self.assertEqual([m['texto'] for m in payload['mensajes']], ['m2', 'm3'])

    def test_obtener_mensajes_rechaza_limite_invalido(self):
        response = self.anon_client.get(
            reverse('tours:obtener_mensajes', args=[self.sesion.id]),
            {'limite': '0'},
        )
        self.assertEqual(response.status_code, 400)