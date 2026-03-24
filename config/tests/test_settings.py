import importlib
import os
import sys
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase


class SettingsDefaultValuesTest(SimpleTestCase):

    def test_installed_apps_contiene_apps_del_proyecto(self):
        for app in ['tours', 'creacion', 'rutas', 'allowList', 'django.contrib.gis']:
            self.assertIn(app, settings.INSTALLED_APPS)

    def test_codigo_idioma_es_espanol(self):
        self.assertEqual(settings.LANGUAGE_CODE, 'es-es')

    def test_uso_de_zona_horaria_activado(self):
        self.assertTrue(settings.USE_TZ)

    def test_celery_acepta_contenido_json(self):
        self.assertIn('json', settings.CELERY_ACCEPT_CONTENT)

    def test_celery_serializador_de_tarea_es_json(self):
        self.assertEqual(settings.CELERY_TASK_SERIALIZER, 'json')

    def test_celery_serializador_de_resultado_es_json(self):
        self.assertEqual(settings.CELERY_RESULT_SERIALIZER, 'json')

    def test_allowed_hosts_contiene_localhost(self):
        self.assertIn('localhost', settings.ALLOWED_HOSTS)

    def test_allowed_hosts_contiene_comodin_run_app(self):
        self.assertIn('.run.app', settings.ALLOWED_HOSTS)

    def test_csrf_trusted_origins_contiene_localhost(self):
        self.assertIn('http://localhost:8000', settings.CSRF_TRUSTED_ORIGINS)

    def test_url_archivos_estaticos(self):
        self.assertIn('static', settings.STATIC_URL)

    def test_campo_auto_por_defecto(self):
        self.assertEqual(
            settings.DEFAULT_AUTO_FIELD, 'django.db.models.BigAutoField'
        )

    def test_motor_base_de_datos_es_postgis(self):
        self.assertEqual(
            settings.DATABASES['default']['ENGINE'],
            'django.contrib.gis.db.backends.postgis',
        )

    def test_debug_es_booleano(self):
        self.assertIsInstance(settings.DEBUG, bool)

    def test_ttl_cache_ruta_es_entero(self):
        self.assertIsInstance(settings.ROUTE_SNAPSHOT_CACHE_TTL, int)


class SettingsConditionalBranchesTest(SimpleTestCase):

    _original_env_snapshot: dict = {}

    def _reload_with(self, env_overrides: dict):
        mod = sys.modules['config.settings']
        with patch.dict(os.environ, env_overrides, clear=False):
            importlib.reload(mod)
        return mod

    def tearDown(self):
        mod = sys.modules.get('config.settings')
        if mod:
            importlib.reload(mod)

    def test_rama_env_hosts_agrega_hosts_adicionales(self):
        mod = self._reload_with({'ALLOWED_HOSTS': 'myhost.com,otherhost.com'})
        self.assertIn('myhost.com', mod.ALLOWED_HOSTS)
        self.assertIn('otherhost.com', mod.ALLOWED_HOSTS)

    def test_rama_env_csrf_agrega_origenes_adicionales(self):
        mod = self._reload_with({'CSRF_TRUSTED_ORIGINS': 'https://mysite.com'})
        self.assertIn('https://mysite.com', mod.CSRF_TRUSTED_ORIGINS)

    def test_debug_verdadero_desde_variable_entorno(self):
        mod = self._reload_with({'DEBUG': 'True'})
        self.assertTrue(mod.DEBUG)

    def test_debug_falso_desde_variable_entorno(self):
        mod = self._reload_with({'DEBUG': 'False'})
        self.assertFalse(mod.DEBUG)

    def test_use_redis_cache_true_usa_backend_redis(self):
        mod = self._reload_with({'USE_REDIS_CACHE': 'True'})
        self.assertEqual(
            mod.CACHES['default']['BACKEND'],
            'django_redis.cache.RedisCache',
        )

    def test_use_redis_cache_false_usa_backend_locmem(self):
        mod = self._reload_with({'USE_REDIS_CACHE': 'False'})
        self.assertEqual(
            mod.CACHES['default']['BACKEND'],
            'django.core.cache.backends.locmem.LocMemCache',
        )

    def test_ruta_gdal_se_toma_de_variable_entorno(self):
        mod = self._reload_with({'GDAL_LIBRARY_PATH': '/fake/gdal.dll'})
        self.assertEqual(mod.GDAL_LIBRARY_PATH, '/fake/gdal.dll')

    def test_ruta_geos_se_toma_de_variable_entorno(self):
        mod = self._reload_with({'GEOS_LIBRARY_PATH': '/fake/geos.dll'})
        self.assertEqual(mod.GEOS_LIBRARY_PATH, '/fake/geos.dll')

    def test_rutas_gdal_geos_son_none_sin_variable_entorno(self):
        current_gdal = os.environ.pop('GDAL_LIBRARY_PATH', None)
        current_geos = os.environ.pop('GEOS_LIBRARY_PATH', None)
        try:
            with patch('dotenv.load_dotenv'), \
                 patch.dict(os.environ, {}, clear=False):
                mod = sys.modules['config.settings']
                importlib.reload(mod)
            self.assertIsNone(mod.GDAL_LIBRARY_PATH)
            self.assertIsNone(mod.GEOS_LIBRARY_PATH)
        finally:
            if current_gdal is not None:
                os.environ['GDAL_LIBRARY_PATH'] = current_gdal
            if current_geos is not None:
                os.environ['GEOS_LIBRARY_PATH'] = current_geos

    def test_database_url_fuerza_motor_postgis(self):
        fake_db = {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'testdb',
            'USER': 'u',
            'PASSWORD': 'p',
            'HOST': 'h',
            'PORT': '5432',
        }
        mod = sys.modules['config.settings']
        with patch('dj_database_url.config', return_value=fake_db):
            importlib.reload(mod)
        self.assertEqual(
            mod.DATABASES['default']['ENGINE'],
            'django.contrib.gis.db.backends.postgis',
        )
