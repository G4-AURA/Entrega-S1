import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class CrearRutaContractJsonTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.guia = User.objects.create_user(username='guia_contract', password='1234')
        self.client.force_login(self.guia)

    @patch('creacion.views._guardar_ruta_ia_en_bd')
    @patch('creacion.views._obtener_guia_para_usuario', return_value=object())
    @patch('creacion.views.consultar_langgraph')
    def test_generar_ruta_ia_respuesta_ok_contiene_campos_minimos(
        self, mock_consultar, _mock_get_guia, mock_guardar
    ):
        payload = {
            'ciudad': 'Sevilla',
            'duracion': 2,
            'personas': 4,
            'exigencia': 'media',
            'mood': ['historia'],
        }
        mock_consultar.return_value = {'paradas': [{'nombre': 'A', 'coordenadas': [37.38, -5.99]}]}
        mock_guardar.return_value = type('RutaStub', (), {'id': 11})()

        response = self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('status', data)
        self.assertIn('mensaje', data)
        self.assertIn('ruta_id', data)
        self.assertIn('datos_ruta', data)

    def test_generar_ruta_ia_error_campos_obligatorios_mensaje_coherente(self):
        response = self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps({'ciudad': 'Sevilla'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['status'], 'ERROR')
        self.assertIn('Faltan parámetros obligatorios', data['mensaje'])

    def test_guardar_manual_error_json_invalido_mensaje_coherente(self):
        response = self.client.post(
            reverse('creacion:guardar_ruta_manual'),
            data='{bad json}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['status'], 'ERROR')
        self.assertTrue(data['mensaje'])
