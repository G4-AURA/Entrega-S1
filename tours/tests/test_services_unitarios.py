"""
Tests unitarios para tours/services.py

Valida la lógica de negocio de servicios (autorización, turistas, códigos).
"""
from django.contrib.auth.models import User, AnonymousUser
from django.test import TestCase, RequestFactory
from django.utils import timezone
from django.core.cache import cache
from django.contrib.gis.geos import Point
import json

from rutas.models import AuthUser, Guia, Ruta, Parada
from tours.models import Turista, SesionTour, TuristaSesion
from tours import services


class AutorizacionTests(TestCase):
    """Tests para funciones de autorización"""

    def setUp(self):
        """Setup con guía, turista y ruta"""
        # Crear guía
        self.guia_user = User.objects.create_user(
            username='guia_auth', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(user=auth_guia)
        
        # Crear ruta
        self.ruta = Ruta.objects.create(
            titulo='Ruta Auth Test',
            descripcion='Descripción',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=self.guia,
        )
        
        # Crear sesión
        self.sesion = SesionTour.objects.create(
            codigo_acceso='AUTH001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        # Crear otro usuario que no es guía
        self.otro_user = User.objects.create_user(
            username='otro_user', password='pass123'
        )

    def test_es_guia_de_sesion_verdadero(self):
        """Verifica que es_guia_de_sesion retorna True para el guía correcto"""
        resultado = services.es_guia_de_sesion(self.guia_user, self.sesion)
        self.assertTrue(resultado)

    def test_es_guia_de_sesion_falso_otro_usuario(self):
        """Verifica que es_guia_de_sesion retorna False para otro usuario"""
        resultado = services.es_guia_de_sesion(self.otro_user, self.sesion)
        self.assertFalse(resultado)

    def test_es_guia_de_sesion_maneja_atributos_faltantes(self):
        """Verifica que maneja AttributeError gracefully"""
        # Crear un usuario normal sin estructura de guía
        user_sin_guia = User.objects.create_user(
            username='sin_guia', password='pass123'
        )
        resultado = services.es_guia_de_sesion(user_sin_guia, self.sesion)
        self.assertFalse(resultado)


class TuristaAnonimoTests(TestCase):
    """Tests para funciones de turistas anónimos"""

    def setUp(self):
        """Setup con request factory y turistas"""
        self.factory = RequestFactory()
        self.turista = Turista.objects.create(alias='turista_anon')

    def test_obtener_turista_anonimo_desde_cookie(self):
        """Verifica obtención de turista desde session cookie"""
        request = self.factory.get('/')
        request.session = {'turista_id': self.turista.id}
        
        resultado = services.obtener_turista_anonimo(request)
        
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.id, self.turista.id)

    def test_obtener_turista_anonimo_sin_cookie(self):
        """Verifica que retorna None sin turista_id en sesión"""
        request = self.factory.get('/')
        request.session = {}
        
        resultado = services.obtener_turista_anonimo(request)
        
        self.assertIsNone(resultado)

    def test_obtener_turista_anonimo_cookie_turista_inexistente(self):
        """Verifica que retorna None si turista fue eliminado"""
        request = self.factory.get('/')
        request.session = {'turista_id': 9999}
        
        resultado = services.obtener_turista_anonimo(request)
        
        self.assertIsNone(resultado)

    def test_obtener_turista_request_desde_anonimo(self):
        """Verifica obtención desde cookie anónima"""
        request = self.factory.get('/')
        request.session = {'turista_id': self.turista.id}
        request.user = AnonymousUser()
        
        resultado = services.obtener_turista_request(request)
        
        self.assertEqual(resultado.id, self.turista.id)

    def test_obtener_turista_request_desde_usuario_autenticado(self):
        """Verifica obtención desde usuario autenticado (compatibilidad)"""
        user = User.objects.create_user(username='usr_hist', password='pass123')
        turista_hist = Turista.objects.create(user=user, alias='turista_hist')
        
        request = self.factory.get('/')
        request.session = {}
        request.user = user
        
        resultado = services.obtener_turista_request(request)
        
        self.assertEqual(resultado.id, turista_hist.id)

    def test_obtener_turista_request_prioriza_anonimo(self):
        """Verifica que turista anónimo tiene prioridad sobre autenticado"""
        user = User.objects.create_user(username='user_prio', password='pass123')
        Turista.objects.create(user=user, alias='turista_user')
        
        request = self.factory.get('/')
        request.session = {'turista_id': self.turista.id}
        request.user = user
        
        resultado = services.obtener_turista_request(request)
        
        self.assertEqual(resultado.id, self.turista.id)

    def test_obtener_turista_request_sin_turista(self):
        """Verifica que retorna None sin turista"""
        request = self.factory.get('/')
        request.session = {}
        request.user = AnonymousUser()
        
        resultado = services.obtener_turista_request(request)
        
        self.assertIsNone(resultado)


class AccesoSesionTests(TestCase):
    """Tests para verificación de acceso a sesión"""

    def setUp(self):
        """Setup con sesión, turista y guía"""
        self.factory = RequestFactory()
        
        # Crear guía y ruta
        self.guia_user = User.objects.create_user(
            username='guia_acceso', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Acceso',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=self.guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='ACC001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        # Crear turista
        self.turista = Turista.objects.create(alias='turista_acceso')
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
            activo=True,
        )

    def test_acceso_guia_autenticado(self):
        """Verifica acceso para guía autenticado"""
        request = self.factory.get('/')
        request.user = self.guia_user
        
        resultado = services.tiene_acceso_a_sesion(request, self.sesion)
        
        self.assertTrue(resultado)

    def test_acceso_turista_anonimo_activo(self):
        """Verifica acceso para turista anónimo activo"""
        request = self.factory.get('/')
        request.session = {'turista_id': self.turista.id}
        request.user = AnonymousUser()
        
        resultado = services.tiene_acceso_a_sesion(request, self.sesion)
        
        self.assertTrue(resultado)

    def test_acceso_turista_anonimo_inactivo(self):
        """Verifica denegación de acceso para turista inactivo"""
        ts = TuristaSesion.objects.get(turista=self.turista)
        ts.activo = False
        ts.save()
        
        request = self.factory.get('/')
        request.session = {'turista_id': self.turista.id}
        request.user = AnonymousUser()
        
        resultado = services.tiene_acceso_a_sesion(request, self.sesion)
        
        self.assertFalse(resultado)

    def test_acceso_usuario_no_registrado(self):
        """Verifica denegación de acceso para usuario no registrado"""
        otro_turista = Turista.objects.create(alias='otro_turista')
        
        request = self.factory.get('/')
        request.session = {'turista_id': otro_turista.id}
        request.user = AnonymousUser()
        
        resultado = services.tiene_acceso_a_sesion(request, self.sesion)
        
        self.assertFalse(resultado)

    def test_acceso_usuario_no_autenticado_sin_turista(self):
        """Verifica denegación de acceso para usuario sin turista"""
        request = self.factory.get('/')
        request.session = {}
        request.user = AnonymousUser()
        
        resultado = services.tiene_acceso_a_sesion(request, self.sesion)
        
        self.assertFalse(resultado)


class GeneradorCodigoTests(TestCase):
    """Tests para generador de códigos únicos"""

    def test_generar_codigo_formato(self):
        """Verifica que el código tiene el formato correcto"""
        codigo = services.generar_codigo_unico(length=6)
        
        self.assertEqual(len(codigo), 6)
        self.assertTrue(codigo.isupper())
        self.assertTrue(codigo.isalnum())

    def test_generar_codigo_longitud_personalizada(self):
        """Verifica generación con longitud personalizada"""
        codigo1 = services.generar_codigo_unico(length=4)
        codigo2 = services.generar_codigo_unico(length=8)
        
        self.assertEqual(len(codigo1), 4)
        self.assertEqual(len(codigo2), 8)

    def test_generar_codigo_unico_en_bd(self):
        """Verifica que los códigos son únicos en BD"""
        # Crear varias sesiones para asegurar unicidad
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        
        codigos = set()
        for i in range(10):
            codigo = services.generar_codigo_unico()
            codigos.add(codigo)
        
        # Todos deben ser únicos
        self.assertEqual(len(codigos), 10)

    def test_generar_codigo_evita_colisiones(self):
        """Verifica que el generador evita códigos duplicados"""
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Col',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        
        # Crear una sesión con un código
        codigo1 = services.generar_codigo_unico(length=4)
        SesionTour.objects.create(
            codigo_acceso=codigo1,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )
        
        # Generar más códigos y verificar que no colisionan
        for i in range(5):
            codigo = services.generar_codigo_unico(length=4)
            self.assertNotEqual(codigo, codigo1)


class UnirTuristaAnonimoTests(TestCase):
    """Tests para la lógica de unión de turista anónimo"""

    def setUp(self):
        """Setup con sesión"""
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Union',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='UNI001',
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_crear_turista_nuevo(self):
        """Verifica creación de turista nuevo"""
        turista, error = services.unir_turista_anonimo(
            self.sesion, 'Juan', None
        )
        
        self.assertIsNotNone(turista)
        self.assertIsNone(error)
        self.assertEqual(turista.alias, 'Juan')
        # Verificar que la relación fue creada
        self.assertTrue(
            TuristaSesion.objects.filter(
                turista=turista,
                sesion_tour=self.sesion,
                activo=True,
            ).exists()
        )

    def test_error_alias_en_uso(self):
        """Verifica error cuando alias ya está en uso"""
        turista1 = Turista.objects.create(alias='Carlos')
        TuristaSesion.objects.create(
            turista=turista1,
            sesion_tour=self.sesion,
            activo=True,
        )
        
        turista2, error = services.unir_turista_anonimo(
            self.sesion, 'Carlos', None
        )
        
        self.assertIsNone(turista2)
        self.assertIsNotNone(error)
        self.assertIn('Carlos', error)

    def test_reconectar_mismo_usuario(self):
        """Verifica reconexión del mismo usuario"""
        turista = Turista.objects.create(alias='Maria')
        TuristaSesion.objects.create(
            turista=turista,
            sesion_tour=self.sesion,
            activo=True,
        )
        
        turista_reconec, error = services.unir_turista_anonimo(
            self.sesion, 'Maria', turista.id
        )
        
        self.assertEqual(turista_reconec.id, turista.id)
        self.assertIsNone(error)

    def test_reactivar_sesion_inactiva(self):
        """Verifica reactivación de sesión inactiva del mismo usuario"""
        turista = Turista.objects.create(alias='Pedro')
        ts = TuristaSesion.objects.create(
            turista=turista,
            sesion_tour=self.sesion,
            activo=False,
        )
        
        turista_reac, error = services.unir_turista_anonimo(
            self.sesion, 'Pedro', turista.id
        )
        
        self.assertEqual(turista_reac.id, turista.id)
        self.assertIsNone(error)
        # Verificar que fue reactivado
        ts.refresh_from_db()
        self.assertTrue(ts.activo)


class RutaSnapshotCacheTests(TestCase):
    """Tests para caché de snapshot de rutas"""

    def setUp(self):
        """Setup con sesión y paradas"""
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        
        self.ruta = Ruta.objects.create(
            titulo='Ruta Cache',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        
        # Crear paradas
        self.parada1 = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada 1',
            orden=1,
            coordenadas=Point(37.3891, -5.9845),
        )
        self.parada2 = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada 2',
            orden=2,
            coordenadas=Point(37.3900, -5.9850),
        )
        
        self.sesion = SesionTour.objects.create(
            codigo_acceso='CACHE001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        # Limpiar caché
        cache.clear()

    def test_build_route_snapshot(self):
        """Verifica construción del snapshot"""
        snapshot = services._build_route_snapshot(self.sesion)
        
        self.assertIn('sesion_id', snapshot)
        self.assertIn('ruta_id', snapshot)
        self.assertIn('paradas', snapshot)
        self.assertEqual(snapshot['sesion_id'], self.sesion.id)

    def test_set_route_snapshot(self):
        """Verifica guardado en caché"""
        snapshot = services.set_route_snapshot(self.sesion)
        
        self.assertIsNotNone(snapshot)
        # Verificar que está en caché
        key = services.route_snapshot_cache_key(self.sesion.id)
        cached = cache.get(key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached['sesion_id'], self.sesion.id)

    def test_get_route_snapshot_desde_cache(self):
        """Verifica obtención desde caché"""
        # Guardar en caché
        snapshot1 = services.set_route_snapshot(self.sesion)
        
        # Obtener desde caché
        snapshot2 = services.get_route_snapshot(self.sesion)
        
        self.assertEqual(snapshot1['sesion_id'], snapshot2['sesion_id'])

    def test_get_route_snapshot_genera_si_no_existe(self):
        """Verifica que genera snapshot si no está en caché"""
        snapshot = services.get_route_snapshot(self.sesion)
        
        self.assertIsNotNone(snapshot)
        self.assertIn('paradas', snapshot)

    def test_invalidate_route_snapshot(self):
        """Verifica invalidación de snapshot"""
        # Guardar en caché
        services.set_route_snapshot(self.sesion)
        
        # Invalidar
        services.invalidate_route_snapshot(self.sesion.id)
        
        # Verificar que fue eliminado
        key = services.route_snapshot_cache_key(self.sesion.id)
        self.assertIsNone(cache.get(key))

    def test_invalidate_route_snapshots_for_route(self):
        """Verifica invalidación de todos los snapshots de una ruta"""
        sesion2 = SesionTour.objects.create(
            codigo_acceso='CACHE002',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        # Guardar ambos en caché
        services.set_route_snapshot(self.sesion)
        services.set_route_snapshot(sesion2)
        
        # Invalidar todos de la ruta
        services.invalidate_route_snapshots_for_route(self.ruta.id)
        
        # Verificar que ambos fueron eliminados
        key1 = services.route_snapshot_cache_key(self.sesion.id)
        key2 = services.route_snapshot_cache_key(sesion2.id)
        self.assertIsNone(cache.get(key1))
        self.assertIsNone(cache.get(key2))


class SerializacionParadasTests(TestCase):
    """Tests para serialización de paradas"""

    def setUp(self):
        """Setup con sesión y paradas"""
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        
        self.ruta = Ruta.objects.create(
            titulo='Ruta Serializ',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        
        self.parada1 = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada A',
            orden=1,
            coordenadas=Point(37.3891, -5.9845),
        )
        
        self.sesion = SesionTour.objects.create(
            codigo_acceso='SER001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

    def test_serializar_paradas_json_valido(self):
        """Verifica que serializa a JSON válido"""
        json_str = services.serializar_paradas(self.sesion)
        
        # Debe ser JSON válido
        data = json.loads(json_str)
        self.assertIsInstance(data, list)

    def test_serializar_paradas_contiene_info(self):
        """Verifica que contiene información correcta"""
        json_str = services.serializar_paradas(self.sesion)
        data = json.loads(json_str)
        
        self.assertEqual(len(data), 1)
        parada_data = data[0]
        self.assertEqual(parada_data['nombre'], 'Parada A')
        self.assertEqual(parada_data['orden'], 1)

    def test_serializar_paradas_marca_actual(self):
        """Verifica que marca parada actual"""
        self.sesion.parada_actual = self.parada1
        self.sesion.save()
        
        json_str = services.serializar_paradas(self.sesion)
        data = json.loads(json_str)
        
        self.assertTrue(data[0]['es_actual'])
