import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import Parada, Ruta
from tours.models import TURISTA


class GeneracionRutaIATestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.payload = {
            'ciudad': 'Sevilla',
            'duracion': 3,
            'personas': 6,
            'exigencia': 'media',
            'mood': ['historia', 'gastronomia'],
        }
        self.ruta_ia = {
            'titulo': 'Ruta IA Sevilla',
            'descripcion': 'Ruta de prueba generada por IA',
            'duracion_horas': 3,
            'num_personas': 6,
            'nivel_exigencia': 'medio',
            'mood': ['historia', 'gastronomia'],
            'paradas': [
                {
                    'orden': 1,
                    'nombre': 'Parada 1',
                    'coordenadas': {'lat': 37.38, 'lon': -5.99},
                },
                {
                    'orden': 2,
                    'nombre': 'Parada 2',
                    'coordenadas': {'lat': 37.39, 'lon': -6.00},
                },
            ],
        }

    @patch('creacion.services.consultar_langgraph')
    def test_guia_puede_generar_y_guardar_ruta_ia(self, mock_consultar):
        mock_consultar.return_value = self.ruta_ia

        guia_user = User.objects.create_user(username='guia1', password='1234')
        self.client.login(username='guia1', password='1234')

        response = self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps(self.payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'OK')
        self.assertTrue(payload.get('datos', {}).get('ruta_id'))

        ruta = Ruta.objects.get(id=payload['datos']['ruta_id'])
        self.assertEqual(ruta.guia.user.user, guia_user)
        self.assertEqual(ruta.titulo, f"Sevilla {timezone.localtime().strftime('%Y-%m-%d')}")
        self.assertTrue(ruta.es_generada_ia)
        self.assertEqual(ruta.paradas.count(), 2)
        self.assertEqual(Parada.objects.filter(ruta=ruta).count(), 2)

    @patch('creacion.services.consultar_langgraph')
    def test_turista_no_puede_generar_ruta_ia(self, mock_consultar):
        mock_consultar.return_value = self.ruta_ia

        turista_user = User.objects.create_user(username='turista1', password='1234')
        TURISTA.objects.create(user=turista_user, alias='Turista Uno')
        self.client.login(username='turista1', password='1234')

        response = self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps(self.payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Ruta.objects.count(), 0)


class CatalogoRutasIATestCase(TestCase):
    def test_filtro_solo_ia(self):
        guia_user = User.objects.create_user(username='guia2', password='1234')
        self.client.login(username='guia2', password='1234')

        with patch('creacion.services.consultar_langgraph') as mock_consultar:
            mock_consultar.return_value = {
                'titulo': 'Ruta IA catálogo',
                'descripcion': 'Descripción',
                'duracion_horas': 2,
                'num_personas': 4,
                'nivel_exigencia': 'media',
                'mood': ['historia'],
                'paradas': [
                    {
                        'orden': 1,
                        'nombre': 'Inicio',
                        'coordenadas': {'lat': 37.38, 'lon': -5.99},
                    }
                ],
            }
            self.client.post(
                reverse('creacion:generar_ruta_ia'),
                data=json.dumps({
                    'ciudad': 'Sevilla',
                    'duracion': 2,
                    'personas': 4,
                    'exigencia': 'media',
                    'mood': ['historia'],
                }),
                content_type='application/json',
            )

        response = self.client.get(reverse('rutas-catalogo') + '?solo_ia=1')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertTrue(data[0]['es_generada_ia'])


class CatalogoRutasUsuarioActualTestCase(TestCase):
    def setUp(self):
        self.client = Client()

    @patch('creacion.services.consultar_langgraph')
    def test_catalogo_solo_muestra_rutas_del_usuario_autenticado(self, mock_consultar):
        mock_consultar.return_value = {
            'titulo': 'Ruta IA user',
            'descripcion': 'Descripción',
            'duracion_horas': 2,
            'num_personas': 4,
            'nivel_exigencia': 'media',
            'mood': ['historia'],
            'paradas': [
                {
                    'orden': 1,
                    'nombre': 'Inicio',
                    'coordenadas': {'lat': 37.38, 'lon': -5.99},
                }
            ],
        }

        User.objects.create_user(username='guia_catalogo_1', password='1234')
        user_2 = User.objects.create_user(username='guia_catalogo_2', password='1234')

        self.client.login(username='guia_catalogo_1', password='1234')
        self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps({
                'ciudad': 'Sevilla',
                'duracion': 2,
                'personas': 4,
                'exigencia': 'media',
                'mood': ['historia'],
            }),
            content_type='application/json',
        )
        self.client.logout()

        self.client.login(username='guia_catalogo_2', password='1234')
        self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps({
                'ciudad': 'Granada',
                'duracion': 2,
                'personas': 4,
                'exigencia': 'media',
                'mood': ['historia'],
            }),
            content_type='application/json',
        )

        response = self.client.get(reverse('rutas-catalogo'))
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['guia']['username'], user_2.username)
        self.assertEqual(data[0]['titulo'], f"Granada {timezone.localtime().strftime('%Y-%m-%d')}")
