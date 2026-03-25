"""
Tests unitarios para tours/signals.py

Valida los handlers de señales Django para invalidación de caché.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache
from django.contrib.gis.geos import Point

from rutas.models import AuthUser, Guia, Ruta, Parada
from tours.models import SesionTour, Turista, TuristaSesion
from tours import services
from tours import signals  # Para asegurar que se registren los handlers


class SignalSesionTourSaveTests(TestCase):
    """Tests para signal post_save de SesionTour"""

    def setUp(self):
        """Setup con sesión"""
        self.guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Signal',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        cache.clear()

    def test_signal_invalidate_on_save(self):
        """Verifica invalidación de caché al guardar sesión"""
        sesion = SesionTour.objects.create(
            codigo_acceso='SIG001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        # Poner snapshot en caché
        services.set_route_snapshot(sesion)
        key = services.route_snapshot_cache_key(sesion.id)
        self.assertIsNotNone(cache.get(key))
        
        # Guardar sesión (debería disparar signal)
        sesion.estado = SesionTour.EN_CURSO
        sesion.save()
        
        # Verificar que caché fue invalidado
        self.assertIsNone(cache.get(key))

    def test_signal_invalidate_cambio_parada(self):
        """Verifica invalidación al cambiar parada"""
        parada = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada Signal',
            orden=1,
            coordenadas=Point(37.3891, -5.9845),
        )
        
        sesion = SesionTour.objects.create(
            codigo_acceso='SIG002',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        # Poner snapshot en caché
        services.set_route_snapshot(sesion)
        key = services.route_snapshot_cache_key(sesion.id)
        self.assertIsNotNone(cache.get(key))
        
        # Cambiar parada actual
        sesion.parada_actual = parada
        sesion.save()
        
        # Verificar que caché fue invalidado
        self.assertIsNone(cache.get(key))


class SignalSesionTourDeleteTests(TestCase):
    """Tests para signal post_delete de SesionTour"""

    def setUp(self):
        """Setup con sesión"""
        self.guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Delete',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        cache.clear()

    def test_signal_invalidate_on_delete(self):
        """Verifica invalidación de caché al eliminar sesión"""
        sesion = SesionTour.objects.create(
            codigo_acceso='SIG003',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        sesion_id = sesion.id
        
        # Poner snapshot en caché
        services.set_route_snapshot(sesion)
        key = services.route_snapshot_cache_key(sesion_id)
        self.assertIsNotNone(cache.get(key))
        
        # Eliminar sesión (debería disparar signal)
        sesion.delete()
        
        # Verificar que caché fue invalidado
        self.assertIsNone(cache.get(key))


class SignalRutaSaveTests(TestCase):
    """Tests para signal post_save de Ruta"""

    def setUp(self):
        """Setup"""
        self.guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Signal2',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=self.guia,
        )
        cache.clear()

    def test_signal_invalidate_snapshots_on_ruta_save(self):
        """Verifica invalidación de todos los snapshots de una ruta"""
        # Crear múltiples sesiones de la misma ruta
        sesion1 = SesionTour.objects.create(
            codigo_acceso='RUTA001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        sesion2 = SesionTour.objects.create(
            codigo_acceso='RUTA002',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        # Poner snapshots en caché
        services.set_route_snapshot(sesion1)
        services.set_route_snapshot(sesion2)
        
        key1 = services.route_snapshot_cache_key(sesion1.id)
        key2 = services.route_snapshot_cache_key(sesion2.id)
        
        self.assertIsNotNone(cache.get(key1))
        self.assertIsNotNone(cache.get(key2))
        
        # Guardar ruta (debería disparar signal y invalidar todos)
        self.ruta.descripcion = 'Nueva descripción'
        self.ruta.save()
        
        # Verificar que ambos cachés fueron invalidados
        self.assertIsNone(cache.get(key1))
        self.assertIsNone(cache.get(key2))


class SignalRutaDeleteTests(TestCase):
    """Tests para signal post_delete de Ruta"""

    def setUp(self):
        """Setup"""
        self.guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Delete2',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=self.guia,
        )
        cache.clear()

    def test_signal_invalidate_snapshots_on_ruta_delete(self):
        """Verifica invalidación al eliminar ruta"""
        sesion1 = SesionTour.objects.create(
            codigo_acceso='RUTADEL001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        sesion2 = SesionTour.objects.create(
            codigo_acceso='RUTADEL002',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        ruta_id = self.ruta.id
        
        # Poner snapshots en caché
        services.set_route_snapshot(sesion1)
        services.set_route_snapshot(sesion2)
        
        key1 = services.route_snapshot_cache_key(sesion1.id)
        key2 = services.route_snapshot_cache_key(sesion2.id)
        
        self.assertIsNotNone(cache.get(key1))
        self.assertIsNotNone(cache.get(key2))
        
        # Eliminar ruta (debería disparar signal)
        self.ruta.delete()
        
        # Verificar que ambos cachés fueron invalidados
        self.assertIsNone(cache.get(key1))
        self.assertIsNone(cache.get(key2))


class SignalParadaSaveTests(TestCase):
    """Tests para signal post_save de Parada"""

    def setUp(self):
        """Setup"""
        self.guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Parada Signal',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.parada = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada 1',
            orden=1,
            coordenadas=Point(37.3891, -5.9845),
        )
        cache.clear()

    def test_signal_invalidate_snapshots_on_parada_save(self):
        """Verifica invalidación de snapshots al guardar parada"""
        sesion = SesionTour.objects.create(
            codigo_acceso='PARADA001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        # Poner snapshot en caché
        services.set_route_snapshot(sesion)
        key = services.route_snapshot_cache_key(sesion.id)
        self.assertIsNotNone(cache.get(key))
        
        # Guardar parada (debería disparar signal)
        self.parada.nombre = 'Parada 1 - Modificada'
        self.parada.save()
        
        # Verificar que caché fue invalidado
        self.assertIsNone(cache.get(key))

    def test_signal_invalidate_solo_paradas_de_ruta(self):
        """Verifica que solo se invalidan paradas de la misma ruta"""
        # Crear otra ruta con otra sesión
        guia_user = User.objects.create_user(username='guia2', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        otra_ruta = Ruta.objects.create(
            titulo='Otra Ruta',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        
        sesion1 = SesionTour.objects.create(
            codigo_acceso='SES001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        sesion2 = SesionTour.objects.create(
            codigo_acceso='SES002',
            fecha_inicio=timezone.now(),
            ruta=otra_ruta,
        )
        
        # Poner snapshots en caché
        services.set_route_snapshot(sesion1)
        services.set_route_snapshot(sesion2)
        
        key1 = services.route_snapshot_cache_key(sesion1.id)
        key2 = services.route_snapshot_cache_key(sesion2.id)
        
        self.assertIsNotNone(cache.get(key1))
        self.assertIsNotNone(cache.get(key2))
        
        # Guardar parada de primera ruta
        self.parada.nombre = 'Parada Modificada'
        self.parada.save()
        
        # Verificar que solo sesion1 fue invalidada
        self.assertIsNone(cache.get(key1))
        self.assertIsNotNone(cache.get(key2))


class SignalParadaDeleteTests(TestCase):
    """Tests para signal post_delete de Parada"""

    def setUp(self):
        """Setup"""
        self.guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Parada Delete',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.parada = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada a Eliminar',
            orden=1,
            coordenadas=Point(37.3891, -5.9845),
        )
        cache.clear()

    def test_signal_invalidate_snapshots_on_parada_delete(self):
        """Verifica invalidación al eliminar parada"""
        sesion = SesionTour.objects.create(
            codigo_acceso='PARADEL001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        # Poner snapshot en caché
        services.set_route_snapshot(sesion)
        key = services.route_snapshot_cache_key(sesion.id)
        self.assertIsNotNone(cache.get(key))
        
        # Eliminar parada (debería disparar signal)
        self.parada.delete()
        
        # Verificar que caché fue invalidado
        self.assertIsNone(cache.get(key))


class SignalCascadingInvalidationTests(TestCase):
    """Tests para validar que todas las invalidaciones funcionan juntas"""

    def setUp(self):
        """Setup completo"""
        self.guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Cascada',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=self.guia,
        )
        self.parada1 = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada Cascada 1',
            orden=1,
            coordenadas=Point(37.3891, -5.9845),
        )
        cache.clear()

    def test_multiple_invalidations(self):
        """Verifica múltiples invalidaciones consecutivas"""
        sesion = SesionTour.objects.create(
            codigo_acceso='CASC001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        key = services.route_snapshot_cache_key(sesion.id)
        
        # Primera invalidación - guardar sesión
        services.set_route_snapshot(sesion)
        sesion.estado = SesionTour.EN_CURSO
        sesion.save()
        self.assertIsNone(cache.get(key))
        
        # Segunda invalidación - guardar parada
        services.set_route_snapshot(sesion)
        self.parada1.nombre = 'Parada Modificada'
        self.parada1.save()
        self.assertIsNone(cache.get(key))
        
        # Tercera invalidación - guardar ruta
        services.set_route_snapshot(sesion)
        self.ruta.descripcion = 'Nueva descripción'
        self.ruta.save()
        self.assertIsNone(cache.get(key))
