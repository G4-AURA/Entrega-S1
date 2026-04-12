from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours import services
from tours.models import SesionTour, Turista, TuristaSesion


class SesionesServicesUnitTests(TestCase):
    def setUp(self):
        self.guia_user = User.objects.create_user(username="guia_unit", password="1234")
        auth_user = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_user)

        self.ruta = Ruta.objects.create(
            titulo="Ruta unit sesiones",
            descripcion="Pruebas unitarias de lógica interna de sesiones",
            duracion_horas=2.0,
            num_personas=20,
            mood=["Historia"],
            guia=guia,
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso="UNIT01",
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        self.turista = Turista.objects.create(alias="turista_unit", user=None)
        self.factory = RequestFactory()

    def test_generar_codigo_unico_con_colision_reintenta(self):
        SesionTour.objects.create(
            codigo_acceso="ABC123",
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

        with patch("tours.services.secrets.choice", side_effect=list("ABC123XYZ789")):
            codigo = services.generar_codigo_unico(length=6)

        self.assertEqual(codigo, "XYZ789")

    def test_iniciar_sesion_actualiza_estado_fecha_y_codigo(self):
        codigo_original = self.sesion.codigo_acceso

        with patch("tours.services.generar_codigo_unico", return_value="UNIT02"):
            services.iniciar_sesion(self.sesion)
        self.sesion.refresh_from_db()

        self.assertEqual(self.sesion.estado, SesionTour.EN_CURSO)
        self.assertNotEqual(self.sesion.codigo_acceso, codigo_original)
        self.assertIsNotNone(self.sesion.fecha_inicio)

    def test_cerrar_sesion_finaliza_y_desactiva_participantes(self):
        turista2 = Turista.objects.create(alias="turista2_unit", user=None)
        TuristaSesion.objects.create(turista=self.turista, sesion_tour=self.sesion, activo=True)
        TuristaSesion.objects.create(turista=turista2, sesion_tour=self.sesion, activo=True)

        services.cerrar_sesion(self.sesion)
        self.sesion.refresh_from_db()

        self.assertEqual(self.sesion.estado, SesionTour.FINALIZADO)
        activos = TuristaSesion.objects.filter(sesion_tour=self.sesion, activo=True).count()
        self.assertEqual(activos, 0)

    def test_unir_turista_anonimo_alias_activo_de_otro_devuelve_error(self):
        turista_existente = Turista.objects.create(alias="AliasDuplicado", user=None)
        TuristaSesion.objects.create(
            turista=turista_existente,
            sesion_tour=self.sesion,
            activo=True,
        )

        turista, error = services.unir_turista_anonimo(
            self.sesion,
            "AliasDuplicado",
            turista_id_cookie=None,
        )

        self.assertIsNone(turista)
        self.assertIsNotNone(error)
        self.assertIn("ya está en uso", error)

    def test_unir_turista_anonimo_reactiva_inactivo_misma_cookie(self):
        turista_reconecta = Turista.objects.create(alias="Reconecta", user=None)
        TuristaSesion.objects.create(
            turista=turista_reconecta,
            sesion_tour=self.sesion,
            activo=False,
        )

        turista, error = services.unir_turista_anonimo(
            self.sesion,
            "Reconecta",
            turista_id_cookie=turista_reconecta.id,
        )

        self.assertIsNone(error)
        self.assertIsNotNone(turista)
        self.assertEqual(turista.id, turista_reconecta.id)
        self.assertTrue(
            TuristaSesion.objects.get(turista=turista_reconecta, sesion_tour=self.sesion).activo
        )

    def test_unir_turista_anonimo_crea_nuevo_turista(self):
        turista, error = services.unir_turista_anonimo(
            self.sesion,
            "NuevoAlias",
            turista_id_cookie=None,
        )

        self.assertIsNone(error)
        self.assertIsNotNone(turista)
        self.assertEqual(turista.alias, "NuevoAlias")
        self.assertTrue(
            TuristaSesion.objects.filter(turista=turista, sesion_tour=self.sesion, activo=True).exists()
        )

    def test_tiene_acceso_a_sesion_false_si_no_esta_en_la_sesion(self):
        request = self.factory.get("/")
        request.session = {"turista_id": self.turista.id}
        request.user = AnonymousUser()

        tiene_acceso = services.tiene_acceso_a_sesion(request, self.sesion)
        self.assertFalse(tiene_acceso)

    def test_es_guia_de_sesion_false_con_sesion_mal_formada(self):
        sesion_invalida = SimpleNamespace(ruta=SimpleNamespace())
        self.assertFalse(services.es_guia_de_sesion(self.guia_user, sesion_invalida))
