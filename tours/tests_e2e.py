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
        self.assertContains(mapa_response, 'style="display: none;"')

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