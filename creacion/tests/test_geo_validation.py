import unittest

from creacion.geo_validation import (
    NoConvergenciaCoordenadasError,
    completar_lista_paradas_validadas,
    validar_y_corregir_parada,
)


class FakeMapboxClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = 0

    def buscar_lugares(self, *, nombre, ciudad, centro, limit=5):
        self.calls += 1
        return list(self.responses.get(str(nombre).strip().lower(), []))


class FakeOSMClient:
    def __init__(self, nominatim_responses=None, overpass_responses=None):
        self.nominatim_responses = nominatim_responses or {}
        self.overpass_responses = overpass_responses or {}
        self.nominatim_calls = 0
        self.overpass_calls = 0

    def buscar_lugares(self, *, nombre, ciudad, centro, limit=6):
        self.nominatim_calls += 1
        return list(self.nominatim_responses.get(str(nombre).strip().lower(), []))

    def buscar_geometria_lineal_cercana(self, *, nombre, centro, radio_m=250, limit=10):
        self.overpass_calls += 1
        return list(self.overpass_responses.get(str(nombre).strip().lower(), []))


def _normalizador_simple(raw, idx):
    if not isinstance(raw, dict):
        return None
    nombre = str(raw.get('nombre') or '').strip()
    coords = raw.get('coordenadas')
    if not nombre or not isinstance(coords, list) or len(coords) < 2:
        return None
    return {
        'id_sugerencia': idx,
        'nombre': nombre,
        'coordenadas': [float(coords[0]), float(coords[1])],
        'categoria': str(raw.get('categoria') or 'general'),
        'nivel_confianza': 1.0,
        'justificacion': str(raw.get('justificacion') or ''),
    }


class GeoValidationUnitTests(unittest.TestCase):
    def setUp(self):
        self.contexto = {'centro': [37.385, -5.992], 'radio_km': 3.0}

    def test_edificio_corrige_a_borde(self):
        parada = {
            'nombre': 'Edificio Test',
            'coordenadas': [37.3850, -5.9920],
            'categoria': 'edificio',
        }
        poligono = [
            [37.3849, -5.9921],
            [37.3851, -5.9921],
            [37.3851, -5.9919],
            [37.3849, -5.9919],
            [37.3849, -5.9921],
        ]
        osm = FakeOSMClient(
            nominatim_responses={
                'edificio test': [
                    {
                        'nombre': 'Edificio Test',
                        'coordenadas': [37.3850, -5.9920],
                        'tipo_geometria': 'building',
                        'linea': None,
                        'poligono': poligono,
                        'fuente_validacion': 'osm_nominatim',
                        'score': 4.0,
                    }
                ]
            }
        )
        mapbox = FakeMapboxClient()

        resultado = validar_y_corregir_parada(
            parada,
            ciudad='Sevilla',
            contexto_geo=self.contexto,
            mapbox_client=mapbox,
            osm_client=osm,
            max_reintentos=3,
        )

        self.assertIsNotNone(resultado)
        self.assertTrue(resultado['corregida'])
        self.assertEqual(resultado['tipo_geometria'], 'building')
        self.assertGreater(resultado['error_m'], 0)
        # Debe quedar en uno de los bordes del polígono.
        lat, lon = resultado['coordenadas']
        self.assertTrue(
            round(lat, 4) in {37.3849, 37.3851} or round(lon, 4) in {-5.9921, -5.9919}
        )

    def test_puente_corrige_a_sobre_linea(self):
        parada = {
            'nombre': 'Puente de Triana',
            'coordenadas': [37.3901, -5.9935],
            'categoria': 'puente',
        }
        linea = [[37.3900, -5.9950], [37.3900, -5.9920]]
        osm = FakeOSMClient(
            nominatim_responses={
                'puente de triana': [
                    {
                        'nombre': 'Puente de Triana',
                        'coordenadas': [37.3900, -5.9935],
                        'tipo_geometria': 'linear',
                        'linea': linea,
                        'poligono': None,
                        'fuente_validacion': 'osm_overpass',
                        'score': 5.0,
                    }
                ]
            }
        )

        resultado = validar_y_corregir_parada(
            parada,
            ciudad='Sevilla',
            contexto_geo=self.contexto,
            mapbox_client=FakeMapboxClient(),
            osm_client=osm,
            max_reintentos=3,
        )

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado['tipo_geometria'], 'linear')
        self.assertTrue(resultado['corregida'])
        self.assertAlmostEqual(resultado['coordenadas'][0], 37.3900, places=4)
        self.assertLessEqual(resultado['error_m'], 20.0)

    def test_punto_mantiene_coordenada_si_error_bajo_umbral(self):
        parada = {
            'nombre': 'Archivo de Indias',
            'coordenadas': [37.38502, -5.99298],
            'categoria': 'historia',
        }
        osm = FakeOSMClient(
            nominatim_responses={
                'archivo de indias': [
                    {
                        'nombre': 'Archivo de Indias',
                        'coordenadas': [37.38500, -5.99300],
                        'tipo_geometria': 'point',
                        'linea': None,
                        'poligono': None,
                        'fuente_validacion': 'osm_nominatim',
                        'score': 4.0,
                    }
                ]
            }
        )

        resultado = validar_y_corregir_parada(
            parada,
            ciudad='Sevilla',
            contexto_geo=self.contexto,
            mapbox_client=FakeMapboxClient(),
            osm_client=osm,
            max_reintentos=3,
        )

        self.assertIsNotNone(resultado)
        self.assertFalse(resultado['corregida'])
        self.assertLessEqual(resultado['error_m'], 20.0)

    def test_reintentos_hasta_tercera_variante(self):
        parada = {
            'nombre': 'Puente de Triana (Sevilla) - histórico',
            'coordenadas': [37.3901, -5.9935],
            'categoria': 'puente',
        }
        osm = FakeOSMClient(
            nominatim_responses={
                'puente de triana - histórico': [
                    {
                        'nombre': 'Puente de Triana',
                        'coordenadas': [37.3900, -5.9935],
                        'tipo_geometria': 'point',
                        'linea': None,
                        'poligono': None,
                        'fuente_validacion': 'osm_nominatim',
                        'score': 4.0,
                    }
                ]
            }
        )

        resultado = validar_y_corregir_parada(
            parada,
            ciudad='Sevilla',
            contexto_geo=self.contexto,
            mapbox_client=FakeMapboxClient(),
            osm_client=osm,
            max_reintentos=3,
        )

        self.assertIsNotNone(resultado)
        self.assertGreaterEqual(osm.nominatim_calls, 2)


class GeoCompletionOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.contexto = {'centro': [37.385, -5.992], 'radio_km': 3.0}

    def test_no_convergente_regenera_reemplazo(self):
        osm = FakeOSMClient(
            nominatim_responses={
                'valida': [
                    {
                        'nombre': 'Valida',
                        'coordenadas': [37.3852, -5.9922],
                        'tipo_geometria': 'point',
                        'linea': None,
                        'poligono': None,
                        'fuente_validacion': 'osm_nominatim',
                        'score': 3.0,
                    }
                ]
            }
        )
        mapbox = FakeMapboxClient()
        llamadas = {'proveedor': 0}

        def proveedor(cantidad, nombres_excluidos, coords_excluidas):
            llamadas['proveedor'] += 1
            return [{'nombre': 'Valida', 'coordenadas': [37.3852, -5.9922], 'categoria': 'general'}]

        resultado = completar_lista_paradas_validadas(
            cantidad_objetivo=1,
            candidatos_iniciales=[{'nombre': 'Invalida', 'coordenadas': [37.39, -5.99], 'categoria': 'general'}],
            normalizador_candidato=_normalizador_simple,
            proveedor_candidatos=proveedor,
            paradas_existentes=[],
            ciudad='Sevilla',
            contexto_geo=self.contexto,
            mapbox_client=mapbox,
            osm_client=osm,
            max_reintentos_por_parada=3,
            factor_presupuesto_global=2,
        )

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['nombre'], 'Valida')
        self.assertEqual(llamadas['proveedor'], 1)

    def test_falla_si_no_completa_objetivo_con_presupuesto_global(self):
        osm = FakeOSMClient()
        mapbox = FakeMapboxClient()
        llamadas = {'proveedor': 0}

        def proveedor(cantidad, nombres_excluidos, coords_excluidas):
            llamadas['proveedor'] += 1
            return [
                {'nombre': f'Invalida {llamadas["proveedor"]}a', 'coordenadas': [37.3900, -5.9900]},
                {'nombre': f'Invalida {llamadas["proveedor"]}b', 'coordenadas': [37.3910, -5.9910]},
            ]

        with self.assertRaises(NoConvergenciaCoordenadasError):
            completar_lista_paradas_validadas(
                cantidad_objetivo=2,
                candidatos_iniciales=[
                    {'nombre': 'Inicio 1', 'coordenadas': [37.3900, -5.9900]},
                    {'nombre': 'Inicio 2', 'coordenadas': [37.3910, -5.9910]},
                ],
                normalizador_candidato=_normalizador_simple,
                proveedor_candidatos=proveedor,
                paradas_existentes=[],
                ciudad='Sevilla',
                contexto_geo=self.contexto,
                mapbox_client=mapbox,
                osm_client=osm,
                max_reintentos_por_parada=3,
                factor_presupuesto_global=2,
            )

        # Objetivo=2 => presupuesto total=4; tras consumirlo debe fallar.
        self.assertEqual(llamadas['proveedor'], 1)

    def test_dedupe_contra_descartadas_no_reintenta_misma_parada(self):
        osm = FakeOSMClient()  # no devuelve nada, todas no convergen
        mapbox = FakeMapboxClient()

        def proveedor(cantidad, nombres_excluidos, coords_excluidas):
            return []

        with self.assertRaises(NoConvergenciaCoordenadasError):
            completar_lista_paradas_validadas(
                cantidad_objetivo=1,
                candidatos_iniciales=[
                    {'nombre': 'Duplicada', 'coordenadas': [37.3900, -5.9900]},
                    {'nombre': 'Duplicada', 'coordenadas': [37.3901, -5.9901]},
                ],
                normalizador_candidato=_normalizador_simple,
                proveedor_candidatos=proveedor,
                paradas_existentes=[],
                ciudad='Sevilla',
                contexto_geo=self.contexto,
                mapbox_client=mapbox,
                osm_client=osm,
                max_reintentos_por_parada=3,
                factor_presupuesto_global=2,
            )

        # Solo la primera "Duplicada" debería intentar validación real; la segunda se filtra por dedupe de descartadas.
        self.assertEqual(osm.nominatim_calls, 1)
        self.assertEqual(mapbox.calls, 1)


if __name__ == '__main__':
    unittest.main()
