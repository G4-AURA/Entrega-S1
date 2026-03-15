from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.tasks import barrido_mensajes_efimeros
from tours.models import MENSAJE_CHAT, SESION_TOUR, TURISTA, UBICACION_VIVO


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


class TouristLocationVisibilityTests(TestCase):
    """
    Tests que verifican que el guía puede ver la ubicación del resto de turistas
    durante una sesión de tour activa.

    Cubren los siguientes escenarios de usuario:
    - Un turista registrado envía su ubicación al servidor.
    - El guía consulta las ubicaciones de todos los turistas.
    - El guía obtiene una lista vacía cuando ningún turista ha compartido su ubicación.
    - Solo el guía puede acceder al endpoint de ubicaciones de turistas.
    - Un turista no puede ver las ubicaciones de otros turistas.
    - Un usuario no autenticado no puede acceder al endpoint.
    - Varios turistas registrados aparecen correctamente en la respuesta.
    - Solo se devuelve la ubicación más reciente de cada turista.
    - Los turistas anónimos (sin cuenta) no aparecen en la lista.
    """

    def setUp(self):
        # Crear guía
        self.guia_user = User.objects.create_user(username='guia_loc', password='1234')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)

        # Crear turista registrado
        self.turista_user = User.objects.create_user(username='turista_loc', password='1234')
        self.turista = TURISTA.objects.create(user=self.turista_user, alias='Turista Loc')

        # Crear segundo turista registrado
        self.turista2_user = User.objects.create_user(username='turista_loc2', password='1234')
        self.turista2 = TURISTA.objects.create(user=self.turista2_user, alias='Turista Loc 2')

        # Crear turista anónimo (sin cuenta Django)
        self.turista_anonimo = TURISTA.objects.create(user=None, alias='Visitante Anónimo')

        # Crear ruta y sesión
        self.ruta = Ruta.objects.create(
            titulo='Ruta Ubicaciones',
            descripcion='Test de ubicaciones',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SESION_TOUR.objects.create(
            codigo_acceso='LOC001',
            estado='en_curso',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.sesion.turistas.add(self.turista)
        self.sesion.turistas.add(self.turista2)
        self.sesion.turistas.add(self.turista_anonimo)

        self.guia_client = Client()
        self.guia_client.force_login(self.guia_user)

        self.turista_client = Client()
        self.turista_client.force_login(self.turista_user)

    def test_turista_registrado_puede_enviar_su_ubicacion(self):
        """Un turista registrado puede enviar su ubicación al servidor."""
        response = self.turista_client.post(
            reverse('tours:registrar_ubicacion'),
            data='{"sesion_id": %d, "latitud": 37.3891, "longitud": -5.9845}' % self.sesion.id,
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(UBICACION_VIVO.objects.filter(usuario=self.turista_user).count(), 1)

    def test_guia_ve_ubicacion_de_turista_despues_de_que_la_comparte(self):
        """El guía puede ver la ubicación de un turista después de que este la envía."""
        from django.contrib.gis.geos import Point

        UBICACION_VIVO.objects.create(
            coordenadas=Point(-5.9845, 37.3891, srid=4326),
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            usuario=self.turista_user,
        )

        response = self.guia_client.get(
            reverse('tours:ubicaciones_turistas', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('turistas', data)
        self.assertEqual(len(data['turistas']), 1)
        turista_data = data['turistas'][0]
        self.assertEqual(turista_data['alias'], 'Turista Loc')
        self.assertAlmostEqual(turista_data['lat'], 37.3891, places=4)
        self.assertAlmostEqual(turista_data['lng'], -5.9845, places=4)
        self.assertIn('timestamp', turista_data)
        self.assertIn('turista_id', turista_data)

    def test_guia_obtiene_lista_vacia_cuando_ningun_turista_comparte_ubicacion(self):
        """El guía recibe una lista vacía si ningún turista ha enviado su ubicación."""
        response = self.guia_client.get(
            reverse('tours:ubicaciones_turistas', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['turistas'], [])

    def test_guia_ve_ubicaciones_de_multiples_turistas(self):
        """El guía puede ver las ubicaciones de varios turistas al mismo tiempo."""
        from django.contrib.gis.geos import Point

        UBICACION_VIVO.objects.create(
            coordenadas=Point(-5.9845, 37.3891, srid=4326),
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            usuario=self.turista_user,
        )
        UBICACION_VIVO.objects.create(
            coordenadas=Point(-5.9900, 37.3900, srid=4326),
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            usuario=self.turista2_user,
        )

        response = self.guia_client.get(
            reverse('tours:ubicaciones_turistas', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['turistas']), 2)
        alias_list = [t['alias'] for t in data['turistas']]
        self.assertIn('Turista Loc', alias_list)
        self.assertIn('Turista Loc 2', alias_list)

    def test_guia_solo_ve_ultima_ubicacion_por_turista(self):
        """El guía solo recibe la ubicación más reciente de cada turista, no duplicados."""
        from django.contrib.gis.geos import Point

        t1 = timezone.now()
        UBICACION_VIVO.objects.create(
            coordenadas=Point(-5.9845, 37.3891, srid=4326),
            timestamp=t1,
            sesion_tour=self.sesion,
            usuario=self.turista_user,
        )
        # Segunda ubicación más reciente del mismo turista
        t2 = timezone.now()
        UBICACION_VIVO.objects.create(
            coordenadas=Point(-5.9850, 37.3895, srid=4326),
            timestamp=t2,
            sesion_tour=self.sesion,
            usuario=self.turista_user,
        )

        response = self.guia_client.get(
            reverse('tours:ubicaciones_turistas', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Solo debe aparecer una entrada por turista con la última ubicación
        self.assertEqual(len(data['turistas']), 1)
        self.assertAlmostEqual(data['turistas'][0]['lat'], 37.3895, places=4)
        self.assertAlmostEqual(data['turistas'][0]['lng'], -5.9850, places=4)

    def test_turistas_anonimos_no_aparecen_en_ubicaciones(self):
        """Los turistas anónimos (sin cuenta Django) no aparecen en el endpoint de ubicaciones."""
        response = self.guia_client.get(
            reverse('tours:ubicaciones_turistas', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        alias_list = [t['alias'] for t in data['turistas']]
        self.assertNotIn('Visitante Anónimo', alias_list)

    def test_turista_no_puede_acceder_a_ubicaciones_de_otros_turistas(self):
        """Un turista no puede consultar las ubicaciones del resto de turistas (solo el guía puede)."""
        response = self.turista_client.get(
            reverse('tours:ubicaciones_turistas', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 403)

    def test_usuario_no_autenticado_no_puede_acceder_a_ubicaciones_turistas(self):
        """Un usuario sin autenticar no puede acceder al endpoint de ubicaciones de turistas."""
        anon_client = Client()

        response = anon_client.get(
            reverse('tours:ubicaciones_turistas', args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 403)

    def test_sesion_inexistente_devuelve_404(self):
        """Consultar ubicaciones de turistas de una sesión que no existe devuelve 404."""
        response = self.guia_client.get(
            reverse('tours:ubicaciones_turistas', args=[99999])
        )

        self.assertEqual(response.status_code, 404)