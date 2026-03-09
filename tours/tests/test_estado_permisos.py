from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import SesionTour, Turista, TuristaSesion


class S2148EstadoPermisosTests(TestCase):
    def setUp(self):
        self.guia_owner_user = User.objects.create_user(
            username="s2148_owner", password="1234"
        )
        auth_owner = AuthUser.objects.create(user=self.guia_owner_user)
        self.guia_owner = Guia.objects.create(user=auth_owner)

        self.usuario_no_propietario = User.objects.create_user(
            username="s2148_other", password="1234"
        )

        self.ruta = Ruta.objects.create(
            titulo="Ruta S2148",
            descripcion="Ruta para validaciones S2.1-48",
            duracion_horas=2.0,
            num_personas=20,
            mood=["Historia"],
            guia=self.guia_owner,
        )

        self.sesion_pendiente = SesionTour.objects.create(
            codigo_acceso="S248P1",
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.sesion_activa = SesionTour.objects.create(
            codigo_acceso="S248A1",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.turista = Turista.objects.create(alias="anon-s2148", user=None)

    def _set_turista_cookie(self, client: Client, turista_id: int):
        session = client.session
        session["turista_id"] = turista_id
        session["turista_alias"] = self.turista.alias
        session.save()

    def test_solo_guia_propietario_puede_iniciar_y_cerrar(self):
        client = Client()
        client.force_login(self.usuario_no_propietario)

        response_iniciar = client.post(
            reverse("tours:iniciar_tour", args=[self.sesion_pendiente.id])
        )
        response_cerrar = client.post(
            reverse("tours:cerrar_acceso", args=[self.sesion_activa.id])
        )

        self.assertEqual(response_iniciar.status_code, 403)
        self.assertEqual(response_cerrar.status_code, 403)

    def test_turista_solo_puede_unirse_a_sesion_activa(self):
        client = Client()

        response_pendiente = client.get(
            reverse("tours:join_tour_by_code", args=[self.sesion_pendiente.codigo_acceso])
        )
        response_activa = client.get(
            reverse("tours:join_tour_by_code", args=[self.sesion_activa.codigo_acceso])
        )

        self.assertEqual(response_pendiente.status_code, 409)
        self.assertEqual(response_activa.status_code, 302)

    def test_chat_y_ubicacion_requieren_pertenecer_a_sesion(self):
        client = Client()

        response_mensajes_sin_acceso = client.get(
            reverse("tours:obtener_mensajes", args=[self.sesion_activa.id])
        )
        response_ubicacion_sin_acceso = client.get(
            reverse("tours:ubicacion_guia", args=[self.sesion_activa.id])
        )

        self.assertEqual(response_mensajes_sin_acceso.status_code, 403)
        self.assertEqual(response_ubicacion_sin_acceso.status_code, 403)

        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion_activa,
            activo=True,
        )
        self._set_turista_cookie(client, self.turista.id)

        response_mensajes_con_acceso = client.get(
            reverse("tours:obtener_mensajes", args=[self.sesion_activa.id])
        )
        response_ubicacion_con_acceso = client.get(
            reverse("tours:ubicacion_guia", args=[self.sesion_activa.id])
        )

        self.assertEqual(response_mensajes_con_acceso.status_code, 200)
        self.assertEqual(response_ubicacion_con_acceso.status_code, 200)

    def test_sesion_inexistente_en_chat_devuelve_404(self):
        client = Client()

        response = client.get(reverse("tours:obtener_mensajes", args=[999999]))

        self.assertEqual(response.status_code, 404)
