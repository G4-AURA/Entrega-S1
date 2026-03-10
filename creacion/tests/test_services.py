from django.contrib.auth.models import User
from django.test import TestCase

from creacion import services
from creacion.views import (
    _guardar_ruta_ia_en_bd,
    _normalizar_moods,
    _obtener_guia_para_usuario,
)
from rutas.models import AuthUser, Guia, Parada, Ruta
from tours.models import TURISTA


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

        with self.assertRaisesMessage(ValueError, 'No se han podido guardar coordenadas válidas para las paradas.'):
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

    def test_genera_candidatos_normalizados(self):
        with self.settings(GEMINI_API_KEY='test-key'):
            with self.subTest('candidatos ok'):
                mocked = [
                    {
                        'nombre': 'Archivo de Indias',
                        'coordenadas': [37.385, -5.993],
                        'categoria': 'historia',
                        'nivel_confianza': 0.91,
                        'justificacion': 'Complementa el recorrido histórico.',
                    }
                ]
                from unittest.mock import patch
                with patch('creacion.services.llamar_gemini_bypass', return_value=mocked):
                    resultado = services.generar_candidatos_paradas_ia(ruta=self.ruta, cantidad=1)

        self.assertEqual(resultado['ruta_id'], self.ruta.id)
        self.assertEqual(len(resultado['candidatos']), 1)
        self.assertEqual(resultado['candidatos'][0]['nombre'], 'Archivo de Indias')
        self.assertEqual(resultado['candidatos'][0]['nivel_confianza'], 0.91)

    def test_falla_con_cantidad_fuera_de_rango(self):
        with self.assertRaisesMessage(services.ErrorValidacionRuta, 'La cantidad de sugerencias debe estar entre 1 y 10.'):
            services.generar_candidatos_paradas_ia(ruta=self.ruta, cantidad=0)

    def test_filtra_candidatos_fuera_del_contexto_geografico(self):
        mocked = [
            {
                'nombre': 'Puerta del Sol',
                'coordenadas': [40.4168, -3.7038],  # Madrid
                'categoria': 'historia',
                'nivel_confianza': 0.9,
                'justificacion': 'Centro turístico muy visitado.',
            },
            {
                'nombre': 'Real Alcázar',
                'coordenadas': [37.3838, -5.9902],  # Sevilla
                'categoria': 'historia',
                'nivel_confianza': 0.95,
                'justificacion': 'Muy cerca del eje histórico actual.',
            },
        ]
        with self.settings(GEMINI_API_KEY='test-key'):
            from unittest.mock import patch
            with patch('creacion.services.llamar_gemini_bypass', return_value=mocked):
                resultado = services.generar_candidatos_paradas_ia(ruta=self.ruta, cantidad=2)

        self.assertEqual(len(resultado['candidatos']), 1)
        self.assertEqual(resultado['candidatos'][0]['nombre'], 'Real Alcázar')

    def test_falla_si_todos_los_candidatos_estan_fuera_del_contexto_geografico(self):
        mocked = [
            {
                'nombre': 'Puerta del Sol',
                'coordenadas': [40.4168, -3.7038],  # Madrid
                'categoria': 'historia',
                'nivel_confianza': 0.9,
                'justificacion': 'Centro turístico muy visitado.',
            }
        ]
        with self.settings(GEMINI_API_KEY='test-key'):
            from unittest.mock import patch
            with patch('creacion.services.llamar_gemini_bypass', return_value=mocked):
                with self.assertRaisesMessage(
                    services.ErrorIntegracionIA,
                    'La IA no devolvió candidatos válidos y no duplicados para esta ruta.',
                ):
                    services.generar_candidatos_paradas_ia(ruta=self.ruta, cantidad=1)

    def test_descarta_candidatos_duplicados_existentes_y_entre_sugerencias(self):
        mocked = [
            {
                'nombre': 'Catedral',  # duplicado por nombre con parada existente
                'coordenadas': [37.3900, -5.9900],
                'categoria': 'historia',
                'nivel_confianza': 0.9,
                'justificacion': 'Duplicado de prueba.',
            },
            {
                'nombre': 'Archivo de Indias',
                'coordenadas': [37.3850, -5.9930],
                'categoria': 'historia',
                'nivel_confianza': 0.91,
                'justificacion': 'Candidato válido.',
            },
            {
                'nombre': 'Archivo de Indias',  # duplicado entre candidatos
                'coordenadas': [37.3850, -5.9930],
                'categoria': 'historia',
                'nivel_confianza': 0.88,
                'justificacion': 'Duplicado entre sugerencias.',
            },
            {
                'nombre': 'Plaza Nueva',  # duplicado por coordenadas con candidato válido
                'coordenadas': [37.3850, -5.9930],
                'categoria': 'local',
                'nivel_confianza': 0.86,
                'justificacion': 'Mismas coordenadas con otro nombre.',
            },
        ]
        with self.settings(GEMINI_API_KEY='test-key'):
            from unittest.mock import patch
            with patch('creacion.services.llamar_gemini_bypass', return_value=mocked):
                resultado = services.generar_candidatos_paradas_ia(ruta=self.ruta, cantidad=4)

        self.assertEqual(len(resultado['candidatos']), 1)
        self.assertEqual(resultado['candidatos'][0]['nombre'], 'Archivo de Indias')
