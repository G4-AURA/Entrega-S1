from unittest.mock import Mock, patch

import requests
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.urls import reverse

from rutas.models import AuthUser, Guia, Parada, Ruta


class GraphHopperRecalculoIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="guia_graphhopper", password="1234")
        auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=auth_user)

        self.ruta = Ruta.objects.create(
            titulo="Ruta con recalculo",
            descripcion="Cobertura de integracion GraphHopper",
            duracion_horas=2.0,
            num_personas=12,
            guia=self.guia,
        )
        self.parada_1 = Parada.objects.create(
            ruta=self.ruta,
            orden=1,
            nombre="Inicio",
            coordenadas=Point(-5.9920, 37.3860, srid=4326),
        )
        self.parada_2 = Parada.objects.create(
            ruta=self.ruta,
            orden=2,
            nombre="Final",
            coordenadas=Point(-5.9900, 37.3870, srid=4326),
        )

        self.client.force_login(self.user)
        self.url = reverse("ruta-recalcular", args=[self.ruta.id])

    @patch("rutas.graphhopper.requests.post")
    def test_recalculo_persiste_geometria_metricas_y_devuelve_contrato_json(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "paths": [
                {
                    "distance": 1200.0,
                    "time": 600000,
                    "points": {
                        "coordinates": [
                            [-5.9920, 37.3860],
                            [-5.9900, 37.3870],
                        ]
                    },
                    "instructions": [
                        {"sign": 0, "distance": 1200.0, "time": 600000},
                        {"sign": 4, "distance": 0.0, "time": 0},
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertTrue(call_args.args[0].endswith("/route"))
        self.assertIn("json", call_args.kwargs)
        self.assertEqual(
            call_args.kwargs["json"]["points"],
            [[-5.9920, 37.3860], [-5.9900, 37.3870]],
        )
        self.assertIn("params", call_args.kwargs)
        self.assertIn("key", call_args.kwargs["params"])

        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["distancia_total_km"], "1.2")
        self.assertEqual(payload["duracion_total_min"], 10)
        self.assertEqual(payload["geometria"], [[37.386, -5.992], [37.387, -5.99]])
        self.assertEqual(len(payload["segmentos"]), 1)
        self.assertEqual(payload["segmentos"][0]["parada_id"], self.parada_1.id)

        self.ruta.refresh_from_db()
        self.parada_1.refresh_from_db()
        self.parada_2.refresh_from_db()

        self.assertIsNotNone(self.ruta.geometria_ruta)
        self.assertEqual(self.ruta.distancia_total_m, 1200.0)
        self.assertEqual(self.ruta.duracion_total_s, 600)
        self.assertEqual(self.parada_1.distancia_siguiente_m, 1200.0)
        self.assertEqual(self.parada_1.duracion_siguiente_s, 600)
        self.assertIsNone(self.parada_2.distancia_siguiente_m)
        self.assertIsNone(self.parada_2.duracion_siguiente_s)

    @patch("rutas.graphhopper.requests.post", side_effect=requests.Timeout)
    def test_recalculo_con_error_externo_mantiene_respuesta_defensiva(self, _mock_post):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["geometria"])
        self.assertIsNone(payload["distancia_total_km"])
        self.assertIsNone(payload["duracion_total_min"])
        self.assertEqual(payload["segmentos"], [])

        self.ruta.refresh_from_db()
        self.assertIsNone(self.ruta.geometria_ruta)
        self.assertIsNone(self.ruta.distancia_total_m)
        self.assertIsNone(self.ruta.duracion_total_s)