from django.contrib.auth.models import User
from django.test import TestCase
from unittest.mock import Mock, patch
import requests

from creacion import services
from creacion.views import (
    _guardar_ruta_ia_en_bd,
    _normalizar_moods,
    _obtener_guia_para_usuario,
)
from rutas.models import AuthUser, Guia, Parada, Ruta
from tours.models import TURISTA


class GeminiBypassResilienceTests(TestCase):
    def test_reintenta_timeout_y_recupera_respuesta(self):
        ok_response = Mock()
        ok_response.status_code = 200
        ok_response.raise_for_status.return_value = None
        ok_response.json.return_value = {
            'candidates': [{'content': {'parts': [{'text': '[{"nombre":"A"}]'}]}}]
        }

        with patch.dict('os.environ', {'GEMINI_MAX_RETRIES': '1', 'GEMINI_TIMEOUT_SECONDS': '10'}, clear=False):
            with patch('creacion.services.requests.post', side_effect=[requests.Timeout('boom'), ok_response]) as mock_post:
                resultado = services.llamar_gemini_bypass('prompt', 'api-key')

        self.assertEqual(resultado, [{'nombre': 'A'}])
        self.assertEqual(mock_post.call_count, 2)

    def test_lanza_error_integracion_si_agota_reintentos(self):
        with patch.dict('os.environ', {'GEMINI_MAX_RETRIES': '1', 'GEMINI_TIMEOUT_SECONDS': '10'}, clear=False):
            with patch('creacion.services.requests.post', side_effect=requests.Timeout('boom')) as mock_post:
                with self.assertRaisesMessage(
                    services.ErrorIntegracionIA,
                    'La conexión con Gemini agotó el tiempo de espera tras 2 intentos.',
                ):
                    services.llamar_gemini_bypass('prompt', 'api-key')

        self.assertEqual(mock_post.call_count, 2)


class MoodAndExigenciaNormalizationTests(TestCase):
    def test_normalizar_moods_acepta_alias_y_descarta_invalidos(self):
        moods = _normalizar_moods(['  historia ', 'cine-series', 'desconocido', ''])

        self.assertEqual(moods, [Ruta.Mood.HISTORIA, Ruta.Mood.CINE_Y_SERIES])

    def test_guardado_ruta_ia_normaliza_exigencia_y_moods(self):
        user = User.objects.create_user(username='guia_norm', password='1234')
        auth_profile = AuthUser.objects.create(user=user)
        guia = Guia.objects.create(user=auth_profile)

        payload = {
            'ciudad': 'Sevilla',
            'duracion': 2,
            'personas': 8,
            'exigencia': 'baja',
            'mood': ['historia', 'cine-series'],
        }
        ruta_generada = {
            'descripcion': 'Ruta de prueba',
            'nivel_exigencia': 'medio',
            'mood': ['historia', 'cine-series', 'no_valido'],
            'paradas': [
                {'nombre': 'A', 'coordenadas': {'lat': 37.38, 'lon': -5.99}},
                {'nombre': 'B', 'coordenadas': [37.39, -6.0]},
            ],
        }

        ruta = _guardar_ruta_ia_en_bd(guia=guia, payload=payload, ruta_generada=ruta_generada)

        self.assertEqual(ruta.nivel_exigencia, Ruta.Exigencia.MEDIA)
        self.assertEqual(ruta.mood, [Ruta.Mood.HISTORIA, Ruta.Mood.CINE_Y_SERIES])


class GuiaValidationTests(TestCase):
    def test_obtener_guia_crea_perfil_para_usuario_valido(self):
        user = User.objects.create_user(username='guia_new', password='1234')

        guia = _obtener_guia_para_usuario(user)

        self.assertIsNotNone(guia)
        self.assertTrue(AuthUser.objects.filter(user=user).exists())
        self.assertTrue(Guia.objects.filter(user__user=user).exists())

    def test_obtener_guia_retorna_none_para_turista(self):
        turista_user = User.objects.create_user(username='turista_user', password='1234')
        TURISTA.objects.create(user=turista_user, alias='Turista')

        guia = _obtener_guia_para_usuario(turista_user)

        self.assertIsNone(guia)


class RutaStorageServiceTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='guia_storage', password='1234')
        auth_profile = AuthUser.objects.create(user=user)
        self.guia = Guia.objects.create(user=auth_profile)

    def test_guardado_ruta_ia_persiste_ruta_y_paradas(self):
        payload = {
            'ciudad': 'Sevilla',
            'duracion': 3,
            'personas': 6,
            'exigencia': 'media',
            'mood': ['historia'],
        }
        ruta_generada = {
            'descripcion': 'Ruta IA Sevilla',
            'nivel_exigencia': 'alta',
            'mood': ['historia'],
            'duracion_horas': 3,
            'num_personas': 6,
            'paradas': [
                {'orden': 1, 'nombre': 'Parada 1', 'coordenadas': {'lat': 37.38, 'lon': -5.99}},
                {'orden': 2, 'nombre': 'Parada 2', 'coords': [37.39, -6.0]},
            ],
        }

        ruta = _guardar_ruta_ia_en_bd(guia=self.guia, payload=payload, ruta_generada=ruta_generada)

        self.assertTrue(ruta.es_generada_ia)
        self.assertEqual(Parada.objects.filter(ruta=ruta).count(), 2)
        self.assertIn('id', ruta_generada)
        self.assertEqual(ruta_generada['paradas'][0]['coordenadas'], [37.38, -5.99])

    def test_guardado_ruta_ia_lanza_error_con_paradas_invalidas(self):
        payload = {'ciudad': 'Sevilla'}
        ruta_generada = {'paradas': [{'nombre': 'Sin coordenadas'}]}

        with self.assertRaisesMessage(ValueError, 'La ruta generada contiene paradas sin coordenadas válidas.'):
            _guardar_ruta_ia_en_bd(guia=self.guia, payload=payload, ruta_generada=ruta_generada)

        self.assertEqual(Ruta.objects.count(), 0)
        self.assertEqual(Parada.objects.count(), 0)

    def test_guardado_ruta_ia_lanza_error_sin_lista_de_paradas(self):
        payload = {'ciudad': 'Sevilla'}
        ruta_generada = {'paradas': 'no_es_lista'}

        with self.assertRaisesMessage(ValueError, 'La ruta generada no contiene paradas válidas para guardar.'):
            _guardar_ruta_ia_en_bd(guia=self.guia, payload=payload, ruta_generada=ruta_generada)


class GenerarCandidatosParadasIATests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='guia_candidatos', password='1234')
        auth_profile = AuthUser.objects.create(user=user)
        self.guia = Guia.objects.create(user=auth_profile)
        self.ruta = Ruta.objects.create(
            titulo='Sevilla Histórica',
            descripcion='Centro histórico',
            duracion_horas=2.5,
            num_personas=12,
            nivel_exigencia=Ruta.Exigencia.MEDIA,
            mood=[Ruta.Mood.HISTORIA],
            es_generada_ia=True,
            guia=self.guia,
        )
        Parada.objects.create(ruta=self.ruta, orden=1, nombre='Catedral', coordenadas='POINT(-5.99 37.39)')

    @staticmethod
    def _mock_osm_buscar_lugares(*, nombre, ciudad, centro, limit=6):
        nombre = str(nombre).strip().lower()
        mapping = {
            'archivo de indias': [37.3851, -5.9930],
            'real alcázar': [37.3838, -5.9902],
            'giralda': [37.3860, -5.9924],
            'puerta del sol': [40.4168, -3.7038],
            'catedral': [37.3861, -5.9925],
        }
        coords = mapping.get(nombre)
        if not coords:
            return []
        return [
            {
                'nombre': nombre.title(),
                'coordenadas': coords,
                'tipo_geometria': 'point',
                'linea': None,
                'poligono': None,
                'fuente_validacion': 'osm_nominatim',
                'score': 3.0,
            }
        ]

    def test_genera_candidatos_exactos_y_regenera_hasta_completar_cantidad(self):
        respuesta_primera = [
            {
                'nombre': 'Puerta del Sol',  # fuera de Sevilla
                'coordenadas': [40.4168, -3.7038],
                'categoria': 'historia',
                'nivel_confianza': 0.82,
                'justificacion': 'Muy conocida.',
            },
            {
                'nombre': 'Archivo de Indias',
                'coordenadas': [37.3850, -5.9930],
                'categoria': 'historia',
                'nivel_confianza': 0.91,
                'justificacion': 'Complementa el recorrido histórico.',
            },
        ]
        respuesta_regenerada = [
            {
                'nombre': 'Real Alcázar',
                'coordenadas': [37.3838, -5.9902],
                'categoria': 'historia',
                'nivel_confianza': 0.95,
                'justificacion': 'Muy cerca del eje histórico actual.',
            }
        ]

        with self.settings(GEMINI_API_KEY='test-key'):
            with patch('creacion.services.llamar_gemini_bypass', side_effect=[respuesta_primera, respuesta_regenerada]) as mock_ia, \
                patch.object(services.MapboxGeocodingClient, 'buscar_lugares', return_value=[]), \
                patch.object(services.OSMGeocodingClient, 'buscar_lugares', side_effect=self._mock_osm_buscar_lugares), \
                patch.object(services.OSMGeocodingClient, 'buscar_geometria_lineal_cercana', return_value=[]):
                resultado = services.generar_candidatos_paradas_ia(ruta=self.ruta, cantidad=2)

        self.assertEqual(resultado['ruta_id'], self.ruta.id)
        self.assertEqual(len(resultado['candidatos']), 2)
        self.assertEqual(
            [c['nombre'] for c in resultado['candidatos']],
            ['Archivo de Indias', 'Real Alcázar'],
        )
        self.assertEqual(mock_ia.call_count, 2)
        self.assertIn('fuente_validacion', resultado['candidatos'][0])
        self.assertIn('tipo_geometria', resultado['candidatos'][0])
        self.assertIn('error_m', resultado['candidatos'][0])
        self.assertIn('corregida', resultado['candidatos'][0])

    def test_falla_con_cantidad_fuera_de_rango(self):
        with self.assertRaisesMessage(services.ErrorValidacionRuta, 'La cantidad de sugerencias debe estar entre 1 y 10.'):
            services.generar_candidatos_paradas_ia(ruta=self.ruta, cantidad=0)

    def test_falla_si_no_puede_completar_cantidad_objetivo(self):
        respuesta_ia = [
            {
                'nombre': 'Puerta del Sol',
                'coordenadas': [40.4168, -3.7038],
                'categoria': 'historia',
                'nivel_confianza': 0.9,
                'justificacion': 'Centro turístico muy visitado.',
            }
        ]
        with self.settings(GEMINI_API_KEY='test-key'):
            with patch('creacion.services.llamar_gemini_bypass', return_value=respuesta_ia), \
                patch.object(services.MapboxGeocodingClient, 'buscar_lugares', return_value=[]), \
                patch.object(services.OSMGeocodingClient, 'buscar_lugares', side_effect=self._mock_osm_buscar_lugares), \
                patch.object(services.OSMGeocodingClient, 'buscar_geometria_lineal_cercana', return_value=[]):
                with self.assertRaisesMessage(
                    services.ErrorIntegracionIA,
                    'No fue posible completar la cantidad solicitada de paradas válidas y no duplicadas para esta ruta.',
                ):
                    services.generar_candidatos_paradas_ia(ruta=self.ruta, cantidad=1)

    def test_descarta_duplicados_y_respeta_dedupe_en_regeneracion(self):
        respuesta_primera = [
            {
                'nombre': 'Catedral',  # duplicado con parada existente
                'coordenadas': [37.3861, -5.9925],
                'categoria': 'historia',
                'nivel_confianza': 0.9,
                'justificacion': 'Duplicado existente.',
            },
            {
                'nombre': 'Archivo de Indias',
                'coordenadas': [37.3850, -5.9930],
                'categoria': 'historia',
                'nivel_confianza': 0.91,
                'justificacion': 'Candidato válido.',
            },
        ]
        respuesta_regenerada = [
            {
                'nombre': 'Giralda',
                'coordenadas': [37.3860, -5.9924],
                'categoria': 'historia',
                'nivel_confianza': 0.93,
                'justificacion': 'Segundo candidato válido no duplicado.',
            },
            {
                'nombre': 'Archivo de Indias',
                'coordenadas': [37.3850, -5.9930],
                'categoria': 'historia',
                'nivel_confianza': 0.84,
                'justificacion': 'Duplicado entre iteraciones.',
            },
        ]

        with self.settings(GEMINI_API_KEY='test-key'):
            with patch('creacion.services.llamar_gemini_bypass', side_effect=[respuesta_primera, respuesta_regenerada]), \
                patch.object(services.MapboxGeocodingClient, 'buscar_lugares', return_value=[]), \
                patch.object(services.OSMGeocodingClient, 'buscar_lugares', side_effect=self._mock_osm_buscar_lugares), \
                patch.object(services.OSMGeocodingClient, 'buscar_geometria_lineal_cercana', return_value=[]):
                resultado = services.generar_candidatos_paradas_ia(ruta=self.ruta, cantidad=2)

        self.assertEqual(len(resultado['candidatos']), 2)
        self.assertEqual(
            [c['nombre'] for c in resultado['candidatos']],
            ['Archivo de Indias', 'Giralda'],
        )
