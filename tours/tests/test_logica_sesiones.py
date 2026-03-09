from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours import services
from tours.models import SesionTour, Turista, TuristaSesion


class LogicaSesionesTourUnitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        self.guia_owner_user = User.objects.create_user(
            username="s2149_owner", password="1234"
        )
        owner_auth = AuthUser.objects.create(user=self.guia_owner_user)
        self.guia_owner = Guia.objects.create(user=owner_auth)

        self.guia_other_user = User.objects.create_user(
            username="s2149_other", password="1234"
        )
        other_auth = AuthUser.objects.create(user=self.guia_other_user)
        self.guia_other = Guia.objects.create(user=other_auth)

        self.ruta = Ruta.objects.create(
            titulo="Ruta S2149",
            descripcion="Pruebas unitarias de sesiones",
            duracion_horas=2.0,
            num_personas=20,
            mood=["Historia"],
            guia=self.guia_owner,
        )

    def _request_with_session(self, user=None, turista=None):
        request = self.factory.get("/")
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        request.user = user if user is not None else AnonymousUser()

        if turista is not None:
            request.session["turista_id"] = turista.id
            request.session["turista_alias"] = turista.alias
            request.session.save()

        return request

    def test_creacion_sesion_asocia_ruta_y_estado(self):
        sesion = SesionTour.objects.create(
            codigo_acceso=services.generar_codigo_unico(),
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.assertEqual(sesion.ruta_id, self.ruta.id)
        self.assertEqual(sesion.estado, SesionTour.PENDIENTE)
        self.assertIsNotNone(sesion.token)

    def test_generar_codigo_unico_formato_valido(self):
        codigo = services.generar_codigo_unico()

        self.assertEqual(len(codigo), 6)
        self.assertTrue(codigo.isalnum())
        self.assertEqual(codigo, codigo.upper())

    @patch("tours.services.secrets.choice")
    def test_generar_codigo_unico_reintenta_colision(self, mock_choice):
        SesionTour.objects.create(
            codigo_acceso="AAAAAA",
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        mock_choice.side_effect = list("AAAAAABBBBBB")

        codigo = services.generar_codigo_unico()

        self.assertEqual(codigo, "BBBBBB")

    def test_iniciar_sesion_desde_pendiente(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149P",
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now() - timezone.timedelta(days=1),
            ruta=self.ruta,
        )
        codigo_anterior = sesion.codigo_acceso

        services.iniciar_sesion(sesion)
        sesion.refresh_from_db()

        self.assertEqual(sesion.estado, SesionTour.EN_CURSO)
        self.assertNotEqual(sesion.codigo_acceso, codigo_anterior)

    def test_iniciar_sesion_en_curso_lanza_estado_invalido(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149A",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        with self.assertRaises(services.EstadoSesionInvalidoError):
            services.iniciar_sesion(sesion)

    def test_iniciar_sesion_finalizada_lanza_error(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149F",
            estado=SesionTour.FINALIZADO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        with self.assertRaises(services.SesionFinalizadaError):
            services.iniciar_sesion(sesion)

    def test_cerrar_sesion_finaliza_y_desactiva_participantes(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149C",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        turista1 = Turista.objects.create(alias="turista-1", user=None)
        turista2 = Turista.objects.create(alias="turista-2", user=None)
        TuristaSesion.objects.create(turista=turista1, sesion_tour=sesion, activo=True)
        TuristaSesion.objects.create(turista=turista2, sesion_tour=sesion, activo=True)

        services.cerrar_sesion(sesion)
        sesion.refresh_from_db()

        self.assertEqual(sesion.estado, SesionTour.FINALIZADO)
        self.assertFalse(
            TuristaSesion.objects.filter(sesion_tour=sesion, activo=True).exists()
        )

    def test_cerrar_sesion_ya_finalizada_lanza_error(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149Z",
            estado=SesionTour.FINALIZADO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        with self.assertRaises(services.EstadoSesionInvalidoError):
            services.cerrar_sesion(sesion)

    def test_validar_guia_de_sesion_rechaza_no_propietario(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149G",
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        with self.assertRaises(services.AccesoSesionDenegadoError):
            services.validar_guia_de_sesion(
                self.guia_other_user,
                sesion,
                "iniciar el tour",
            )

    def test_tiene_acceso_a_sesion_para_guia_y_turista_miembro(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149H",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        turista = Turista.objects.create(alias="miembro", user=None)
        TuristaSesion.objects.create(turista=turista, sesion_tour=sesion, activo=True)

        req_guia = self._request_with_session(user=self.guia_owner_user)
        req_turista = self._request_with_session(turista=turista)
        req_fuera = self._request_with_session(user=self.guia_other_user)

        self.assertTrue(services.tiene_acceso_a_sesion(req_guia, sesion))
        self.assertTrue(services.tiene_acceso_a_sesion(req_turista, sesion))
        self.assertFalse(services.tiene_acceso_a_sesion(req_fuera, sesion))

    def test_unir_turista_anonimo_rechaza_sesion_pendiente(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149U",
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        with self.assertRaises(services.EstadoSesionInvalidoError):
            services.unir_turista_anonimo(sesion, "anonimo", None)

    def test_unir_turista_anonimo_alias_activo_duplicado(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149M",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        existente = Turista.objects.create(alias="pepe", user=None)
        TuristaSesion.objects.create(turista=existente, sesion_tour=sesion, activo=True)

        turista, error = services.unir_turista_anonimo(sesion, "pepe", None)

        self.assertIsNone(turista)
        self.assertIsNotNone(error)
        self.assertIn("ya está en uso", error)

    def test_obtener_nombre_remitente_lanza_sin_pertenencia(self):
        sesion = SesionTour.objects.create(
            codigo_acceso="S2149R",
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        turista = Turista.objects.create(alias="sin-acceso", user=None)
        request = self._request_with_session(turista=turista)

        with self.assertRaises(services.AccesoSesionDenegadoError):
            services.obtener_nombre_remitente(request, sesion)
