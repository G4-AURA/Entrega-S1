import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import SesionTour, Turista, TuristaSesion, UbicacionVivo


class SesionPermisosEstadoTests(TestCase):
    def setUp(self):
        self.guia_owner_user = User.objects.create_user(username="guia_owner", password="1234")
        self.guia_otro_user = User.objects.create_user(username="guia_otro", password="1234")

        owner_auth = AuthUser.objects.create(user=self.guia_owner_user)
        otro_auth = AuthUser.objects.create(user=self.guia_otro_user)

        self.guia_owner = Guia.objects.create(user=owner_auth)
        Guia.objects.create(user=otro_auth)

        self.ruta = Ruta.objects.create(
            titulo="Ruta permisos sesión",
            descripcion="Validaciones de estado y permisos",
            duracion_horas=2.0,
            num_personas=20,
            mood=["Historia"],
            guia=self.guia_owner,
        )

        self.sesion_pendiente = SesionTour.objects.create(
            codigo_acceso="PEND01",
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.sesion_activa = SesionTour.objects.create(
            codigo_acceso="ACTV01",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.sesion_finalizada = SesionTour.objects.create(
            codigo_acceso="FINL01",
            estado=SesionTour.FINALIZADO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.turista = Turista.objects.create(alias="turista_ok", user=None)
        self.turista_intruso = Turista.objects.create(alias="turista_intruso", user=None)

        TuristaSesion.objects.create(turista=self.turista, sesion_tour=self.sesion_activa, activo=True)

    def _client_guia_owner(self):
        client = Client()
        client.force_login(self.guia_owner_user)
        return client

    def _client_guia_otro(self):
        client = Client()
        client.force_login(self.guia_otro_user)
        return client

    def _client_turista(self, turista_id):
        client = Client()
        session = client.session
        session["turista_id"] = turista_id
        session.save()
        return client

    def test_iniciar_tour_restringido_al_guia_propietario(self):
        client_owner = self._client_guia_owner()
        response_owner = client_owner.post(reverse("tours:iniciar_tour", args=[self.sesion_pendiente.id]))
        self.assertEqual(response_owner.status_code, 200)

        sesion_owner = SesionTour.objects.get(id=self.sesion_pendiente.id)
        self.assertEqual(sesion_owner.estado, SesionTour.EN_CURSO)

        sesion_nueva = SesionTour.objects.create(
            codigo_acceso="PEND02",
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        client_otro = self._client_guia_otro()
        response_otro = client_otro.post(reverse("tours:iniciar_tour", args=[sesion_nueva.id]))
        self.assertEqual(response_otro.status_code, 403)

    def test_cerrar_acceso_restringido_y_no_repite_cierre(self):
        client_otro = self._client_guia_otro()
        response_no_auth = client_otro.post(reverse("tours:cerrar_acceso", args=[self.sesion_activa.id]))
        self.assertEqual(response_no_auth.status_code, 403)

        client_owner = self._client_guia_owner()
        response_ok = client_owner.post(reverse("tours:cerrar_acceso", args=[self.sesion_activa.id]))
        self.assertEqual(response_ok.status_code, 200)

        response_repetido = client_owner.post(reverse("tours:cerrar_acceso", args=[self.sesion_activa.id]))
        self.assertEqual(response_repetido.status_code, 409)

    def test_join_tour_by_code_permite_pendiente_y_activa_pero_no_finalizada(self):
        client = Client()

        response_pendiente = client.get(reverse("tours:join_tour_by_code", args=[self.sesion_pendiente.codigo_acceso]))
        self.assertEqual(response_pendiente.status_code, 302)

        response_finalizada = client.get(reverse("tours:join_tour_by_code", args=[self.sesion_finalizada.codigo_acceso]))
        self.assertEqual(response_finalizada.status_code, 410)

        response_activa = client.get(reverse("tours:join_tour_by_code", args=[self.sesion_activa.codigo_acceso]))
        self.assertEqual(response_activa.status_code, 302)

    def test_registrar_ubicacion_turista_valida_estado_y_pertenencia(self):
        client_turista = self._client_turista(self.turista.id)

        response_ok = client_turista.post(
            reverse("tours:registrar_ubicacion_turista", args=[self.sesion_activa.id]),
            data=json.dumps({"latitud": 37.3901, "longitud": -5.9820}),
            content_type="application/json",
        )
        self.assertEqual(response_ok.status_code, 201)

        response_pendiente = client_turista.post(
            reverse("tours:registrar_ubicacion_turista", args=[self.sesion_pendiente.id]),
            data=json.dumps({"latitud": 37.3901, "longitud": -5.9820}),
            content_type="application/json",
        )
        self.assertEqual(response_pendiente.status_code, 409)

        TuristaSesion.objects.create(turista=self.turista, sesion_tour=self.sesion_finalizada, activo=True)
        response_finalizada = client_turista.post(
            reverse("tours:registrar_ubicacion_turista", args=[self.sesion_finalizada.id]),
            data=json.dumps({"latitud": 37.3901, "longitud": -5.9820}),
            content_type="application/json",
        )
        self.assertEqual(response_finalizada.status_code, 410)

        client_intruso = self._client_turista(self.turista_intruso.id)
        response_intruso = client_intruso.post(
            reverse("tours:registrar_ubicacion_turista", args=[self.sesion_activa.id]),
            data=json.dumps({"latitud": 37.3901, "longitud": -5.9820}),
            content_type="application/json",
        )
        self.assertEqual(response_intruso.status_code, 403)

    def test_obtener_ubicacion_guia_exige_pertenecer_a_sesion(self):
        UbicacionVivo.objects.create(
            coordenadas=Point(-5.9845, 37.3891, srid=4326),
            timestamp=timezone.now(),
            sesion_tour=self.sesion_activa,
            usuario=self.guia_owner_user,
        )

        client_intruso = self._client_turista(self.turista_intruso.id)
        response_intruso = client_intruso.get(reverse("tours:ubicacion_guia", args=[self.sesion_activa.id]))
        self.assertEqual(response_intruso.status_code, 403)

        client_turista = self._client_turista(self.turista.id)
        response_ok = client_turista.get(reverse("tours:ubicacion_guia", args=[self.sesion_activa.id]))
        self.assertEqual(response_ok.status_code, 200)

    def test_crear_sesion_controla_ruta_inexistente(self):
        client_owner = self._client_guia_owner()
        response = client_owner.get(reverse("tours:crear_sesion"), {"ruta_id": 999999})

        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.json())

    def test_join_tour_controla_token_invalido(self):
        client = Client()
        response = client.get("/tours/live/00000000-0000-0000-0000-000000000000/")

        self.assertEqual(response.status_code, 404)

    def test_endpoints_json_devuelven_404_si_sesion_no_existe(self):
        client_owner = self._client_guia_owner()

        response_iniciar = client_owner.post(reverse("tours:iniciar_tour", args=[999999]))
        self.assertEqual(response_iniciar.status_code, 404)
        self.assertIn("error", response_iniciar.json())

        response_cronometro = client_owner.get(reverse("tours:estado_cronometro", args=[999999]))
        self.assertEqual(response_cronometro.status_code, 404)
        self.assertIn("error", response_cronometro.json())

    def test_chat_y_ubicacion_guia_requieren_sesion_en_curso(self):
        client_owner = self._client_guia_owner()

        response_chat_pendiente = client_owner.post(
            reverse("tours:enviar_mensaje", args=[self.sesion_pendiente.id]),
            data=json.dumps({"texto": "hola"}),
            content_type="application/json",
        )
        self.assertEqual(response_chat_pendiente.status_code, 409)

        response_ubi_pendiente = client_owner.post(
            reverse("tours:registrar_ubicacion"),
            data=json.dumps(
                {
                    "sesion_id": self.sesion_pendiente.id,
                    "latitud": 37.3901,
                    "longitud": -5.9820,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response_ubi_pendiente.status_code, 409)
