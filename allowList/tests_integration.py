import json
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import Client, TestCase
from django.urls import reverse

from allowList.models import CategoriaOSM, POI


class AllowListApiIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="admin_integration",
            password="admin1234",
            email="admin@example.com",
        )
        self.normal_user = User.objects.create_user(
            username="normal_integration",
            password="normal1234",
        )

        self.poi_existente = POI.objects.create(
            nombre="POI existente",
            categoria=CategoriaOSM.MONUMENTO,
            ciudad="Sevilla",
            coordenadas=Point(-5.992, 37.386, srid=4326),
            fuente=POI.Fuente.MANUAL,
        )

    def test_superuser_puede_crear_listar_y_eliminar_poi_manual(self):
        self.client.force_login(self.superuser)

        crear_response = self.client.post(
            reverse("allowlist:api_crear_manual"),
            data=json.dumps(
                {
                    "nombre": "Archivo de Indias",
                    "lat": 37.3859,
                    "lon": -5.9930,
                    "categoria": CategoriaOSM.MONUMENTO,
                    "ciudad": "Sevilla",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(crear_response.status_code, 201)
        crear_payload = crear_response.json()
        self.assertEqual(crear_payload["status"], "OK")

        poi_id = crear_payload["poi_id"]
        self.assertTrue(POI.objects.filter(id=poi_id, fuente=POI.Fuente.MANUAL).exists())

        listar_response = self.client.get(reverse("allowlist:api_listar"))
        self.assertEqual(listar_response.status_code, 200)
        listar_payload = listar_response.json()
        self.assertEqual(listar_payload["status"], "OK")
        self.assertGreaterEqual(listar_payload["total"], 2)

        eliminar_response = self.client.post(reverse("allowlist:api_eliminar", args=[poi_id]))
        self.assertEqual(eliminar_response.status_code, 200)
        self.assertEqual(eliminar_response.json()["status"], "OK")
        self.assertFalse(POI.objects.filter(id=poi_id).exists())

    def test_usuario_normal_no_puede_acceder_a_api_admin(self):
        self.client.force_login(self.normal_user)

        listar_response = self.client.get(reverse("allowlist:api_listar"))
        self.assertEqual(listar_response.status_code, 403)
        self.assertEqual(listar_response.json()["status"], "ERROR")

        crear_response = self.client.post(
            reverse("allowlist:api_crear_manual"),
            data=json.dumps(
                {
                    "nombre": "POI bloqueado",
                    "lat": 37.38,
                    "lon": -5.99,
                    "categoria": CategoriaOSM.OTRO,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(crear_response.status_code, 403)
        self.assertEqual(crear_response.json()["status"], "ERROR")

    @patch("allowList.services.requests.post")
    def test_buscar_osm_mockeando_solo_boundary_http(self, mock_requests_post):
        self.client.force_login(self.superuser)

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "elements": [
                {
                    "type": "node",
                    "id": 101,
                    "lat": 37.3860,
                    "lon": -5.9920,
                    "tags": {
                        "name": "Giralda",
                        "historic": "monument",
                    },
                }
            ]
        }
        mock_requests_post.return_value = mock_response

        response = self.client.post(
            reverse("allowlist:api_buscar_osm"),
            data=json.dumps(
                {
                    "ciudad": "Sevilla",
                    "categorias": [CategoriaOSM.MONUMENTO],
                    "pais": "España",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "OK")
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["resultados"][0]["nombre"], "Giralda")
        self.assertEqual(payload["resultados"][0]["categoria"], CategoriaOSM.MONUMENTO)

    def test_importar_osm_persiste_y_es_idempotente(self):
        self.client.force_login(self.superuser)

        payload = {
            "ciudad": "Sevilla",
            "elementos": [
                {
                    "osm_id": 777,
                    "osm_type": "node",
                    "nombre": "Torre del Oro",
                    "lat": 37.3826,
                    "lon": -5.9963,
                    "categoria": CategoriaOSM.MONUMENTO,
                }
            ],
        }

        first_response = self.client.post(
            reverse("allowlist:api_importar_osm"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["status"], "OK")
        self.assertEqual(first_response.json()["creados"], 1)
        self.assertTrue(POI.objects.filter(osm_id=777, fuente=POI.Fuente.OSM).exists())

        second_response = self.client.post(
            reverse("allowlist:api_importar_osm"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["ya_existian"], 1)
        self.assertEqual(POI.objects.filter(osm_id=777).count(), 1)

    def test_resolver_poi_local(self):
        from .services import resolver_poi
        poi = resolver_poi("POI existente", "Sevilla", "")
        self.assertIsNotNone(poi)
        self.assertEqual(poi.id, self.poi_existente.id)
        self.assertEqual(poi.fuente, POI.Fuente.MANUAL)

    @patch('allowList.services.requests.get')
    def test_resolver_poi_google_fallback(self, mock_get):
        from .services import resolver_poi
        from django.test import override_settings

        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": [{
                "name": "Nuevo POI Google",
                "geometry": {
                    "location": {
                        "lat": 37.1234,
                        "lng": -5.1234
                    }
                },
                "formatted_address": "Calle Falsa 123"
            }]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with override_settings(GOOGLE_PLACES_API_KEY='dummy_key'):
            poi = resolver_poi("Nuevo POI", "Madrid", "")
            
        self.assertIsNotNone(poi)
        self.assertEqual(poi.nombre, "Nuevo POI Google")
        self.assertEqual(poi.ciudad, "Madrid")
        self.assertEqual(poi.direccion, "Calle Falsa 123")
        self.assertEqual(poi.fuente, POI.Fuente.GOOGLE)
        self.assertEqual(poi.coordenadas.x, -5.1234)
        self.assertEqual(poi.coordenadas.y, 37.1234)
        
        # Verify it was saved to DB
        self.assertTrue(POI.objects.filter(nombre="Nuevo POI Google", fuente=POI.Fuente.GOOGLE).exists())
