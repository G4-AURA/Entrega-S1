import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from rutas.models import AuthUser, Guia, Ruta
from tours.models import TURISTA


class GenerarRutaIAViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('creacion:generar_ruta_ia')
        self.payload = {
            'ciudad': 'Sevilla',
            'duracion': 3,
            'personas': 6,
            'exigencia': 'media',
            'mood': ['historia', 'gastronomia'],
        }

    def test_rechaza_usuario_no_autenticado(self):
        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'ERROR')

    def test_rechaza_usuario_turista(self):
        turista_user = User.objects.create_user(username='turista', password='1234')
        TURISTA.objects.create(user=turista_user, alias='T1')
        self.client.force_login(turista_user)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'ERROR')

    @patch('creacion.views._guardar_ruta_ia_en_bd')
    @patch('creacion.views._obtener_guia_para_usuario')
    @patch('creacion.views.consultar_langgraph')
    def test_delega_en_servicios_y_retorna_200(self, mock_consultar, mock_get_guia, mock_guardar):
        user = User.objects.create_user(username='guia', password='1234')
        self.client.force_login(user)

        mock_consultar.return_value = {'paradas': [{'nombre': 'A', 'coordenadas': [37.38, -5.99]}]}
        mock_get_guia.return_value = object()
        mock_guardar.return_value = type('RutaStub', (), {'id': 99})()

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 200)
        mock_consultar.assert_called_once_with({
            'ciudad': 'Sevilla',
            'duracion': 3.0,
            'personas': 6,
            'exigencia': Ruta.Exigencia.MEDIA,
            'mood': [Ruta.Mood.HISTORIA, Ruta.Mood.GASTRONOMIA],
            'deseos': [],
            'metadata': {}
        })
        mock_get_guia.assert_called_once_with(user)
        mock_guardar.assert_called_once()

    @patch('creacion.views.consultar_langgraph')
    def test_devuelve_400_si_faltan_campos(self, mock_consultar):
        user = User.objects.create_user(username='guia_campos', password='1234')
        self.client.force_login(user)

        incompleto = {'ciudad': 'Sevilla'}
        response = self.client.post(self.url, data=json.dumps(incompleto), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        mock_consultar.assert_not_called()

    @patch('creacion.views._obtener_guia_para_usuario', return_value=object())
    @patch('creacion.views.consultar_langgraph', side_effect=ValueError('datos inválidos'))
    def test_error_validacion_retorna_400(self, _mock_consultar, _mock_get_guia):
        user = User.objects.create_user(username='guia_error', password='1234')
        self.client.force_login(user)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Error en los datos', response.json()['mensaje'])


class GuardarRutaManualViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('creacion:guardar_ruta_manual')
        self.payload = {
            'titulo': 'Ruta Manual Centro',
            'descripcion': 'Ruta creada a mano',
            'duracion_horas': 2.5,
            'num_personas': 12,
            'nivel_exigencia': 'Media',
            'mood': ['Historia'],
            'paradas': [
                {'nombre': 'Parada 1', 'lat': 37.38, 'lon': -5.99},
                {'nombre': 'Parada 2', 'lat': 37.39, 'lon': -6.00},
            ],
        }

    def test_guardar_manual_retorna_401_sin_login(self):
        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 401)

    def test_guardar_manual_retorna_403_para_turista(self):
        turista_user = User.objects.create_user(username='turista_manual', password='1234')
        TURISTA.objects.create(user=turista_user, alias='TM')
        self.client.force_login(turista_user)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 403)

    @patch('creacion.views._obtener_guia_para_usuario')
    def test_guardar_manual_delega_perfil_guia_y_crea_ruta(self, mock_get_guia):
        user = User.objects.create_user(username='guia_manual', password='1234')
        self.client.force_login(user)
        auth_profile = AuthUser.objects.create(user=user)
        mock_get_guia.return_value = Guia.objects.create(user=auth_profile)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ruta.objects.count(), 1)
        mock_get_guia.assert_called_once_with(user)

    def test_guardar_manual_datos_invalidos_retorna_400(self):
        user = User.objects.create_user(username='guia_manual_bad', password='1234')
        self.client.force_login(user)

        invalid_payload = {'titulo': 'Ruta Inválida', 'duracion_horas': 'no-num'}
        response = self.client.post(self.url, data=json.dumps(invalid_payload), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'ERROR')
