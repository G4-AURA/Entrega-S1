from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Parada, Ruta
from tours.models import SesionTour, Turista, TuristaSesion


class EstadoSesionApiTests(TestCase):
    def setUp(self):
        self.guia_user = User.objects.create_user(username="guia_estado", password="1234")
        auth_user = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_user)

        self.ruta = Ruta.objects.create(
            titulo="Ruta Estado",
            descripcion="Ruta para tests de estado",
            duracion_horas=2,
            num_personas=10,
            mood=[Ruta.Mood.HISTORIA],
            guia=guia,
        )

        self.parada_1 = Parada.objects.create(
            ruta=self.ruta,
            orden=1,
            nombre="Parada 1",
            coordenadas=Point(-5.9845, 37.3891, srid=4326),
        )
        self.parada_2 = Parada.objects.create(
            ruta=self.ruta,
            orden=2,
            nombre="Parada 2",
            coordenadas=Point(-5.9900, 37.3920, srid=4326),
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso="EST001",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
            parada_actual=self.parada_2,
        )

        self.turista = Turista.objects.create(alias="nico")
        TuristaSesion.objects.create(turista=self.turista, sesion_tour=self.sesion, activo=True)

    def test_estado_sesion_permte_turista_anonimo_de_la_sesion(self):
        client = Client()
        session = client.session
        session["turista_id"] = self.turista.id
        session.save()

        response = client.get(reverse("tours:estado_sesion", args=[self.sesion.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sesion_id"], self.sesion.id)
        self.assertEqual(data["estado"], SesionTour.EN_CURSO)
        self.assertEqual(data["parada_actual_id"], self.parada_2.id)

        paradas = {p["id"]: p["es_actual"] for p in data["paradas"]}
        self.assertIn(self.parada_1.id, paradas)
        self.assertIn(self.parada_2.id, paradas)
        self.assertFalse(paradas[self.parada_1.id])
        self.assertTrue(paradas[self.parada_2.id])

    def test_estado_sesion_permite_guia_autenticado(self):
        client = Client()
        client.force_login(self.guia_user)

        response = client.get(reverse("tours:estado_sesion", args=[self.sesion.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sesion_id"], self.sesion.id)

    def test_estado_sesion_deniega_usuario_sin_acceso(self):
        client = Client()

        response = client.get(reverse("tours:estado_sesion", args=[self.sesion.id]))

        self.assertEqual(response.status_code, 403)

    def test_estado_sesion_finalizada_permite_turista_ya_unido(self):
        TuristaSesion.objects.filter(turista=self.turista, sesion_tour=self.sesion).update(activo=False)
        self.sesion.estado = SesionTour.FINALIZADO
        self.sesion.save(update_fields=["estado"])

        client = Client()
        session = client.session
        session["turista_id"] = self.turista.id
        session.save()

        response = client.get(reverse("tours:estado_sesion", args=[self.sesion.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["estado"], SesionTour.FINALIZADO)
