from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import SesionTour, Turista, TuristaSesion, UbicacionVivo


class TuristasUbicacionSesionTests(TestCase):
    def setUp(self):
        self.guia_user = User.objects.create_user(username="guia_s2210", password="1234")
        auth_guia = AuthUser.objects.create(user=self.guia_user)
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

    def _client_guia(self):
        client = Client()
        client.force_login(self.guia_user)
        return client

    def test_guia_no_expone_turistas_fuera_de_sesion(self):
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

        client = self._client_guia()
        response = client.get(reverse("tours:ubicaciones_turistas", args=[self.sesion.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["turistas"]), 1)
        self.assertEqual(payload["turistas"][0]["turista_id"], self.turista_b.id)

    def test_guia_recibe_formato_coordenadas_y_lista_vacia(self):
        client = self._client_guia()
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

    def test_turista_no_puede_listar_ubicaciones_turistas(self):
        client = self._client_turista(self.turista_a.id)
        response = client.get(reverse("tours:ubicaciones_turistas", args=[self.sesion.id]))
        self.assertEqual(response.status_code, 403)

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


class ResumenMapaSesionTests(TestCase):
    def setUp(self):
        self.guia_user = User.objects.create_user(username="guia_summary", password="1234")
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)

        self.ruta = Ruta.objects.create(
            titulo="Ruta Summary",
            descripcion="Resumen mapa",
            duracion_horas=3.0,
            num_personas=12,
            mood=["Historia"],
            guia=guia,
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso="SUM001",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.turista = Turista.objects.create(alias="turista-summary", user=None)
        TuristaSesion.objects.create(turista=self.turista, sesion_tour=self.sesion, activo=True)

        self.guia_client = Client()
        self.guia_client.force_login(self.guia_user)

        self.turista_client = Client()
        turista_session = self.turista_client.session
        turista_session["turista_id"] = self.turista.id
        turista_session["turista_alias"] = self.turista.alias
        turista_session.save()

    def test_resumen_mapa_permite_turista_participante(self):
        response = self.turista_client.get(
            reverse("tours:resumen_mapa_sesion", args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["sesion_id"], self.sesion.id)
        self.assertEqual(payload["ruta"]["titulo"], "Ruta Summary")
        self.assertEqual(payload["participantes_activos"], 1)
        self.assertFalse(payload["es_guia"])

    def test_resumen_mapa_incluye_participantes_para_guia(self):
        response = self.guia_client.get(
            reverse("tours:resumen_mapa_sesion", args=[self.sesion.id])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["es_guia"])
        self.assertEqual(len(payload["participantes"]), 1)
        self.assertEqual(payload["participantes"][0]["alias"], "turista-summary")

    def test_resumen_mapa_bloquea_usuario_ajeno(self):
        intruso = User.objects.create_user(username="intruso_summary", password="1234")
        intruso_client = Client()
        intruso_client.force_login(intruso)

        response = intruso_client.get(
            reverse("tours:resumen_mapa_sesion", args=[self.sesion.id])
        )
        self.assertEqual(response.status_code, 403)
