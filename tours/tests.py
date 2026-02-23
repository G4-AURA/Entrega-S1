from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import RUTA, SESION_TOUR, TURISTA


class SessionLogicEndpointsTests(TestCase):
    def setUp(self):
        self.guia = User.objects.create_user(username='guia_test', password='1234')
        self.turista_user = User.objects.create_user(username='turista_test', password='1234')
        self.turista = TURISTA.objects.create(user=self.turista_user, alias='turista1')
        self.ruta = RUTA.objects.create(nombre='Ruta Test', descripcion='Descripción de prueba')

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
