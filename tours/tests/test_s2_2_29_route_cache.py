from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from rutas.models import AuthUser, Guia, Parada, Ruta
from tours import services
from tours.models import SESION_TOUR


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-route-cache",
        }
    },
    ROUTE_SNAPSHOT_CACHE_TTL=300,
)
class RouteSnapshotCacheTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cache_guia", password="1234")
        auth_guia = AuthUser.objects.create(user=self.user)
        guia = Guia.objects.create(user=auth_guia)

        self.ruta = Ruta.objects.create(
            titulo="Ruta Cache",
            descripcion="Prueba cache",
            duracion_horas=2.0,
            num_personas=20,
            mood=["Historia"],
            guia=guia,
        )

        self.parada_1 = Parada.objects.create(
            ruta=self.ruta,
            orden=1,
            nombre="Parada Uno",
            coordenadas="POINT(-5.9845 37.3891)",
        )
        self.parada_2 = Parada.objects.create(
            ruta=self.ruta,
            orden=2,
            nombre="Parada Dos",
            coordenadas="POINT(-5.9900 37.3920)",
        )

        self.sesion = SESION_TOUR.objects.create(
            codigo_acceso="CACHE1",
            estado=SESION_TOUR.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
            parada_actual=self.parada_1,
        )

    def tearDown(self):
        cache.clear()

    def test_cache_miss_builds_and_stores_snapshot(self):
        key = services.route_snapshot_cache_key(self.sesion.id)
        cache.delete(key)

        snapshot = services.get_route_snapshot(self.sesion)
        snapshot_in_cache = cache.get(key)

        self.assertIsNotNone(snapshot_in_cache)
        self.assertEqual(snapshot["sesion_id"], self.sesion.id)
        self.assertEqual(snapshot["ruta_id"], self.ruta.id)
        self.assertEqual(len(snapshot["paradas"]), 2)
        self.assertTrue(snapshot["paradas"][0]["es_actual"])

    def test_cache_hit_does_not_rebuild_snapshot(self):
        initial_snapshot = services.set_route_snapshot(self.sesion)

        with mock.patch("tours.services._build_route_snapshot", side_effect=AssertionError("No debe reconstruir en cache hit")):
            cached_snapshot = services.get_route_snapshot(self.sesion)

        self.assertEqual(cached_snapshot, initial_snapshot)

    def test_invalidation_when_current_stop_changes(self):
        key = services.route_snapshot_cache_key(self.sesion.id)
        services.set_route_snapshot(self.sesion)
        self.assertIsNotNone(cache.get(key))

        self.sesion.parada_actual = self.parada_2
        self.sesion.save(update_fields=["parada_actual"])

        self.assertIsNone(cache.get(key))
