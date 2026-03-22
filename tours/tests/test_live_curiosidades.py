from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Curiosidad, Guia, Parada, Ruta
from tours.models import SesionTour, Turista, TuristaSesion


class LiveCuriosidadesEndpointTests(TestCase):
    def setUp(self):
        self.guia_user = User.objects.create_user(username="guia_live_cur", password="1234")
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)

        self.ruta = Ruta.objects.create(
            titulo="Ruta curiosidades en vivo",
            descripcion="Pruebas de curiosidades por parada",
            duracion_horas=2.0,
            num_personas=15,
            mood=["Historia"],
            guia=guia,
        )

        self.ruta_otra = Ruta.objects.create(
            titulo="Ruta alternativa",
            descripcion="Validación de parada fuera de sesión",
            duracion_horas=1.5,
            num_personas=10,
            mood=["Cultura"],
            guia=guia,
        )

        self.parada_1 = Parada.objects.create(
            ruta=self.ruta,
            orden=1,
            nombre="Catedral",
            coordenadas=Point(-5.9927, 37.3861, srid=4326),
        )
        self.parada_fuera = Parada.objects.create(
            ruta=self.ruta_otra,
            orden=1,
            nombre="Plaza fuera",
            coordenadas=Point(-5.9870, 37.3898, srid=4326),
        )

        self.curiosidad = Curiosidad.objects.create(
            parada=self.parada_1,
            ciudad="Sevilla",
            titulo="Una puerta escondida",
            texto="Existe una puerta lateral que usaban antiguos canónigos para entrar al templo.",
            tipo=Curiosidad.TipoCuriosidad.HISTORIA,
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso="LVC001",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.turista = Turista.objects.create(alias="ana-live", user=None)
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
            activo=True,
        )

    def _client_turista(self):
        client = Client()
        session = client.session
        session["turista_id"] = self.turista.id
        session["turista_alias"] = self.turista.alias
        session.save()
        return client

    def test_turista_participante_obtiene_curiosidad(self):
        client = self._client_turista()
        response = client.get(
            reverse("tours:obtener_curiosidad_parada", args=[self.sesion.id, self.parada_1.id])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["parada"]["id"], self.parada_1.id)
        self.assertEqual(payload["curiosidad"]["id"], self.curiosidad.id)
        self.assertEqual(payload["curiosidad"]["titulo"], "Una puerta escondida")

    def test_rechaza_usuario_sin_acceso(self):
        client = Client()
        response = client.get(
            reverse("tours:obtener_curiosidad_parada", args=[self.sesion.id, self.parada_1.id])
        )

        self.assertEqual(response.status_code, 403)

    def test_rechaza_parada_fuera_de_ruta(self):
        client = self._client_turista()
        response = client.get(
            reverse("tours:obtener_curiosidad_parada", args=[self.sesion.id, self.parada_fuera.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_404_si_parada_sin_curiosidad(self):
        parada_sin_curiosidad = Parada.objects.create(
            ruta=self.ruta,
            orden=2,
            nombre="Archivo de Indias",
            coordenadas=Point(-5.9930, 37.3858, srid=4326),
        )

        client = self._client_turista()
        response = client.get(
            reverse("tours:obtener_curiosidad_parada", args=[self.sesion.id, parada_sin_curiosidad.id])
        )

        self.assertEqual(response.status_code, 404)
