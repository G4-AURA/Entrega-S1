from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import SesionTour, Turista, TuristaSesion, UbicacionVivo


class TuristasUbicacionSesionTests(TestCase):
    def setUp(self):
        guia_user = User.objects.create_user(username="guia_s2210", password="1234")
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)

        self.ruta = Ruta.objects.create(
            titulo="Ruta S2.2-10",
            descripcion="Validacion ubicacion turistas",
            duracion_horas=2.0,
            num_personas=20,
            mood=["Historia"],
            guia=guia,
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso="S2210A",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.sesion_otro = SesionTour.objects.create(
            codigo_acceso="S2210B",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.turista_a = Turista.objects.create(alias="turista-a", user=None)
        self.turista_b = Turista.objects.create(alias="turista-b", user=None)
        self.turista_c = Turista.objects.create(alias="turista-c", user=None)

        TuristaSesion.objects.create(turista=self.turista_a, sesion_tour=self.sesion, activo=True)
        TuristaSesion.objects.create(turista=self.turista_b, sesion_tour=self.sesion, activo=True)
        TuristaSesion.objects.create(turista=self.turista_c, sesion_tour=self.sesion_otro, activo=True)

    def _client_turista(self, turista_id):
        client = Client()
        session = client.session
        session["turista_id"] = turista_id
        session.save()
        return client

    def test_no_expone_turistas_fuera_de_sesion(self):
        UbicacionVivo.objects.create(
            coordenadas=Point(-5.9845, 37.3891, srid=4326),
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            turista=self.turista_b,
        )
        UbicacionVivo.objects.create(
            coordenadas=Point(-3.7038, 40.4168, srid=4326),
            timestamp=timezone.now(),
            sesion_tour=self.sesion_otro,
            turista=self.turista_c,
        )

        client = self._client_turista(self.turista_a.id)
        response = client.get(reverse("tours:ubicaciones_turistas", args=[self.sesion.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["turistas"]), 1)
        self.assertEqual(payload["turistas"][0]["turista_id"], self.turista_b.id)

    def test_formato_coordenadas_y_lista_vacia(self):
        client = self._client_turista(self.turista_a.id)
        response_vacio = client.get(reverse("tours:ubicaciones_turistas", args=[self.sesion.id]))

        self.assertEqual(response_vacio.status_code, 200)
        self.assertEqual(response_vacio.json()["turistas"], [])

        UbicacionVivo.objects.create(
            coordenadas=Point(-5.9900, 37.3800, srid=4326),
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            turista=self.turista_b,
        )

        response = client.get(reverse("tours:ubicaciones_turistas", args=[self.sesion.id]))
        self.assertEqual(response.status_code, 200)

        item = response.json()["turistas"][0]
        self.assertIsInstance(item["lat"], float)
        self.assertIsInstance(item["lng"], float)
        self.assertIn("timestamp", item)

    def test_registrar_ubicacion_turista_crea_registro(self):
        client = self._client_turista(self.turista_a.id)
        response = client.post(
            reverse("tours:registrar_ubicacion_turista", args=[self.sesion.id]),
            data='{"latitud": 37.3901, "longitud": -5.9820}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        ubicacion = UbicacionVivo.objects.get(turista=self.turista_a, sesion_tour=self.sesion)
        self.assertIsNone(ubicacion.usuario)
        self.assertAlmostEqual(ubicacion.coordenadas.y, 37.3901, places=4)
        self.assertAlmostEqual(ubicacion.coordenadas.x, -5.9820, places=4)
