import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import SESION_TOUR, TURISTA


class ChatGuideTouristE2ETests(TestCase):
    def setUp(self):
        self.guia_user = User.objects.create_user(username='guia_e2e', password='1234')
        self.turista_user = User.objects.create_user(username='turista_e2e', password='1234')

        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)

        ruta = Ruta.objects.create(
            titulo='Ruta E2E Chat',
            descripcion='Ruta para validar chat guía/turista',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )

        self.sesion = SESION_TOUR.objects.create(
            codigo_acceso='E2E001',
            estado='en_curso',
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

        self.turista = TURISTA.objects.create(user=self.turista_user, alias='turista-e2e')
        self.sesion.turistas.add(self.turista)

        self.guia_client = Client()
        self.guia_client.force_login(self.guia_user)

        self.turista_client = Client()
        self.turista_client.force_login(self.turista_user)

    def test_e2e_guia_envia_alerta_y_turista_recibe_notificacion_y_mensaje(self):
        mapa_response = self.turista_client.get(reverse('tours:mapa_turista', args=[self.sesion.id]))
        self.assertEqual(mapa_response.status_code, 200)
        self.assertContains(mapa_response, 'id="chat-badge"')

        texto_alerta = 'ALERTA: Nos movemos a la siguiente parada.'
        send_response = self.guia_client.post(
            reverse('tours:enviar_mensaje', args=[self.sesion.id]),
            data=json.dumps({'texto': texto_alerta}),
            content_type='application/json',
        )

        self.assertEqual(send_response.status_code, 201)
        send_payload = send_response.json()
        self.assertEqual(send_payload['texto'], texto_alerta)
        self.assertEqual(send_payload['nombre_remitente'], self.guia_user.username)

        read_response = self.turista_client.get(reverse('tours:obtener_mensajes', args=[self.sesion.id]))
        self.assertEqual(read_response.status_code, 200)

        read_payload = read_response.json()
        self.assertGreaterEqual(read_payload['total'], 1)
        self.assertTrue(
            any(
                mensaje['texto'] == texto_alerta and mensaje['nombre_remitente'] == self.guia_user.username
                for mensaje in read_payload['mensajes']
            )
        )


class TouristLocationE2ETests(TestCase):
    """
    Tests E2E que verifican el flujo completo de visibilidad de ubicaciones:
    el turista comparte su posición y el guía la recibe en tiempo real.
    """

    def setUp(self):
        self.guia_user = User.objects.create_user(username='guia_loc_e2e', password='1234')
        self.turista_user = User.objects.create_user(username='turista_loc_e2e', password='1234')

        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)

        ruta = Ruta.objects.create(
            titulo='Ruta E2E Ubicaciones',
            descripcion='Ruta para validar visibilidad de ubicaciones',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )

        self.sesion = SESION_TOUR.objects.create(
            codigo_acceso='E2ELOC01',
            estado='en_curso',
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

        self.turista = TURISTA.objects.create(user=self.turista_user, alias='turista-loc-e2e')
        self.sesion.turistas.add(self.turista)

        self.guia_client = Client()
        self.guia_client.force_login(self.guia_user)

        self.turista_client = Client()
        self.turista_client.force_login(self.turista_user)

    def test_e2e_turista_comparte_ubicacion_y_guia_la_ve_en_el_mapa(self):
        """
        Flujo completo: el turista envía su ubicación al servidor y el guía
        puede consultarla inmediatamente a través del endpoint de ubicaciones.
        """
        # 1. El turista accede al mapa (verificamos que el mapa carga correctamente)
        mapa_response = self.turista_client.get(
            reverse('tours:mapa_turista', args=[self.sesion.id])
        )
        self.assertEqual(mapa_response.status_code, 200)

        # 2. El turista envía su ubicación GPS al servidor
        ubicacion_response = self.turista_client.post(
            reverse('tours:registrar_ubicacion'),
            data=json.dumps({'sesion_id': self.sesion.id, 'latitud': 37.3891, 'longitud': -5.9845}),
            content_type='application/json',
        )
        self.assertEqual(ubicacion_response.status_code, 201)

        # 3. El guía consulta las ubicaciones de los turistas
        ubicaciones_response = self.guia_client.get(
            reverse('tours:ubicaciones_turistas', args=[self.sesion.id])
        )
        self.assertEqual(ubicaciones_response.status_code, 200)

        payload = ubicaciones_response.json()
        self.assertEqual(len(payload['turistas']), 1)

        turista_data = payload['turistas'][0]
        self.assertEqual(turista_data['alias'], 'turista-loc-e2e')
        self.assertAlmostEqual(turista_data['lat'], 37.3891, places=4)
        self.assertAlmostEqual(turista_data['lng'], -5.9845, places=4)

    def test_e2e_guia_accede_al_mapa_con_variable_esguia_correcta(self):
        """El guía accede al mapa y el HTML contiene la variable JavaScript esGuia=true."""
        mapa_response = self.guia_client.get(
            reverse('tours:mapa_turista', args=[self.sesion.id])
        )
        self.assertEqual(mapa_response.status_code, 200)
        self.assertContains(mapa_response, 'const esGuia = true')

    def test_e2e_turista_accede_al_mapa_con_variable_esguia_correcta(self):
        """El turista accede al mapa y el HTML contiene la variable JavaScript esGuia=false."""
        mapa_response = self.turista_client.get(
            reverse('tours:mapa_turista', args=[self.sesion.id])
        )
        self.assertEqual(mapa_response.status_code, 200)
        self.assertContains(mapa_response, 'const esGuia = false')

    def test_e2e_ubicacion_se_actualiza_con_cada_envio(self):
        """
        Si el turista envía varias ubicaciones, el guía siempre ve la más reciente.
        """
        # Primera ubicación
        self.turista_client.post(
            reverse('tours:registrar_ubicacion'),
            data=json.dumps({'sesion_id': self.sesion.id, 'latitud': 37.3891, 'longitud': -5.9845}),
            content_type='application/json',
        )

        # Segunda ubicación (más reciente)
        self.turista_client.post(
            reverse('tours:registrar_ubicacion'),
            data=json.dumps({'sesion_id': self.sesion.id, 'latitud': 37.3900, 'longitud': -5.9900}),
            content_type='application/json',
        )

        ubicaciones_response = self.guia_client.get(
            reverse('tours:ubicaciones_turistas', args=[self.sesion.id])
        )
        payload = ubicaciones_response.json()

        # Solo debe aparecer una entrada con la posición más reciente
        self.assertEqual(len(payload['turistas']), 1)
        self.assertAlmostEqual(payload['turistas'][0]['lat'], 37.3900, places=4)
        self.assertAlmostEqual(payload['turistas'][0]['lng'], -5.9900, places=4)