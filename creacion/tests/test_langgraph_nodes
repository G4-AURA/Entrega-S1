"""
creacion/tests/test_langgraph_nodes.py

Tests unitarios para los 4 nodos del pipeline modularizado (Tarea 2.1-25).

Cada clase testea un nodo en aislamiento mockeando sus dependencias externas
(Gemini, geo_validation, OR-Tools) para que los tests sean rápidos y
deterministas.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

# ─────────────────────────────────────────────────────────────────────────────
# Helpers compartidos
# ─────────────────────────────────────────────────────────────────────────────

def _estado_base(ciudad='Sevilla', duracion=2, personas=4, exigencia='media', mood=None):
    return {
        'usuario_input': {
            'ciudad': ciudad,
            'duracion': duracion,
            'personas': personas,
            'exigencia': exigencia,
            'mood': mood or ['historia'],
        }
    }


def _poi_crudo(nombre='Catedral de Sevilla', lat=37.386, lon=-5.992, categoria='historia'):
    return {'nombre': nombre, 'coords': [lat, lon], 'desc': 'Descripción', 'categoria': categoria}


def _poi_validado(nombre='Catedral de Sevilla', lat=37.386, lon=-5.992):
    return {
        'nombre': nombre,
        'coords': [lat, lon],
        'desc': 'Descripción',
        'categoria': 'historia',
        'fuente_validacion': 'mapbox',
        'tipo_geometria': 'point',
        'error_m': 0.0,
        'corregida': False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Nodo 1: Generación
# ─────────────────────────────────────────────────────────────────────────────

class NodoGeneracionTestCase(TestCase):

    @patch('creacion.langgraph.nodes.generacion._obtener_pois_allowlist', return_value=[])
    @patch('creacion.langgraph.nodes.generacion.llamar_gemini')
    def test_devuelve_pois_crudos_de_gemini(self, mock_gemini, _mock_allowlist):
        pois_esperados = [_poi_crudo('A'), _poi_crudo('B')]
        mock_gemini.return_value = pois_esperados

        from creacion.langgraph.nodes.generacion import nodo_generacion
        state = _estado_base()
        resultado = nodo_generacion(state)

        self.assertIn('pois_crudos', resultado)
        self.assertEqual(resultado['pois_crudos'], pois_esperados)

    @patch('creacion.langgraph.nodes.generacion._construir_pois_fallback_allowlist')
    @patch('creacion.langgraph.nodes.generacion._obtener_pois_allowlist', return_value=[])
    @patch('creacion.langgraph.nodes.generacion.llamar_gemini')
    def test_usa_fallback_si_gemini_falla(self, mock_gemini, _mock_allowlist, mock_fallback):
        from creacion.services import ErrorIntegracionIA
        mock_gemini.side_effect = ErrorIntegracionIA('timeout')
        fallback_pois = [_poi_crudo('Fallback A'), _poi_crudo('Fallback B'),
                         _poi_crudo('Fallback C'), _poi_crudo('Fallback D')]
        mock_fallback.return_value = fallback_pois

        from creacion.langgraph.nodes.generacion import nodo_generacion
        state = _estado_base(duracion=2)  # objetivo = 4 paradas
        resultado = nodo_generacion(state)

        self.assertEqual(resultado['pois_crudos'], fallback_pois)

    @patch('creacion.langgraph.nodes.generacion._construir_pois_fallback_allowlist', return_value=[])
    @patch('creacion.langgraph.nodes.generacion._obtener_pois_allowlist', return_value=[])
    @patch('creacion.langgraph.nodes.generacion.llamar_gemini')
    def test_lanza_error_si_gemini_y_fallback_fallan(self, mock_gemini, _mock_allowlist, _mock_fallback):
        from creacion.services import ErrorIntegracionIA
        mock_gemini.side_effect = ErrorIntegracionIA('timeout')

        from creacion.langgraph.nodes.generacion import nodo_generacion
        state = _estado_base(duracion=2)
        with self.assertRaises(ErrorIntegracionIA):
            nodo_generacion(state)

    @patch('creacion.langgraph.nodes.generacion._obtener_pois_allowlist', return_value=[])
    @patch('creacion.langgraph.nodes.generacion.llamar_gemini')
    def test_lanza_error_si_gemini_devuelve_no_lista(self, mock_gemini, _mock_allowlist):
        from creacion.services import ErrorIntegracionIA
        mock_gemini.return_value = {'error': 'formato incorrecto'}

        from creacion.langgraph.nodes.generacion import nodo_generacion
        state = _estado_base()
        with self.assertRaises(ErrorIntegracionIA):
            nodo_generacion(state)


# ─────────────────────────────────────────────────────────────────────────────
# Nodo 2: Validación
# ─────────────────────────────────────────────────────────────────────────────

class NodoValidacionTestCase(TestCase):

    def _state_con_pois_crudos(self, pois=None):
        state = _estado_base()
        state['pois_crudos'] = pois or [_poi_crudo('A'), _poi_crudo('B'),
                                         _poi_crudo('C'), _poi_crudo('D')]
        return state

    @patch('creacion.langgraph.nodes.validacion.OSMGeocodingClient')
    @patch('creacion.langgraph.nodes.validacion.MapboxGeocodingClient')
    @patch('creacion.langgraph.nodes.validacion.completar_lista_paradas_validadas')
    def test_devuelve_pois_validados_y_razones_descarte(
        self, mock_completar, _mock_mapbox, _mock_osm
    ):
        validadas = [
            {**_poi_crudo('A'), 'coordenadas': [37.386, -5.992],
             'fuente_validacion': 'mapbox', 'tipo_geometria': 'point',
             'error_m': 0.0, 'corregida': False},
            {**_poi_crudo('B'), 'coordenadas': [37.387, -5.993],
             'fuente_validacion': 'osm', 'tipo_geometria': 'point',
             'error_m': 0.0, 'corregida': False},
        ]
        mock_completar.return_value = validadas

        from creacion.langgraph.nodes.validacion import nodo_validacion
        state = self._state_con_pois_crudos([_poi_crudo('A'), _poi_crudo('B')])
        resultado = nodo_validacion(state)

        self.assertIn('pois_validados', resultado)
        self.assertIn('razones_descarte', resultado)
        self.assertEqual(len(resultado['pois_validados']), 2)

    @patch('creacion.langgraph.nodes.validacion.OSMGeocodingClient')
    @patch('creacion.langgraph.nodes.validacion.MapboxGeocodingClient')
    @patch('creacion.langgraph.nodes.validacion.completar_lista_paradas_validadas')
    def test_registra_descarte_de_poi_invalido(
        self, mock_completar, _mock_mapbox, _mock_osm
    ):
        # Solo A pasa validación; B es descartado
        validadas = [
            {**_poi_crudo('A'), 'coordenadas': [37.386, -5.992],
             'fuente_validacion': 'mapbox', 'tipo_geometria': 'point',
             'error_m': 0.0, 'corregida': False},
        ]
        mock_completar.return_value = validadas

        from creacion.langgraph.nodes.validacion import nodo_validacion
        state = self._state_con_pois_crudos([_poi_crudo('A'), _poi_crudo('B')])
        resultado = nodo_validacion(state)

        self.assertEqual(len(resultado['pois_validados']), 1)
        self.assertGreaterEqual(len(resultado['razones_descarte']), 1)

    @patch('creacion.langgraph.nodes.validacion.OSMGeocodingClient')
    @patch('creacion.langgraph.nodes.validacion.MapboxGeocodingClient')
    @patch('creacion.langgraph.nodes.validacion.completar_lista_paradas_validadas')
    def test_lanza_error_si_no_convergen_coordenadas(
        self, mock_completar, _mock_mapbox, _mock_osm
    ):
        from creacion.geo_validation import NoConvergenciaCoordenadasError
        from creacion.services import ErrorIntegracionIA
        mock_completar.side_effect = NoConvergenciaCoordenadasError('sin convergencia')

        from creacion.langgraph.nodes.validacion import nodo_validacion
        state = self._state_con_pois_crudos()
        with self.assertRaises(ErrorIntegracionIA):
            nodo_validacion(state)


# ─────────────────────────────────────────────────────────────────────────────
# Nodo 3: Scoring
# ─────────────────────────────────────────────────────────────────────────────

class NodoScoringTestCase(TestCase):

    def _state_con_pois_validados(self, pois=None):
        state = _estado_base()
        state['pois_crudos'] = []
        state['razones_descarte'] = []
        state['pois_validados'] = pois or [
            _poi_validado('Catedral', 37.386, -5.992),
            _poi_validado('Alcázar', 37.383, -5.990),
            _poi_validado('Plaza España', 37.377, -5.987),
        ]
        return state

    def test_devuelve_metricas_con_claves_esperadas(self):
        from creacion.langgraph.nodes.scoring import nodo_scoring
        state = self._state_con_pois_validados()
        resultado = nodo_scoring(state)

        self.assertIn('metricas_scoring', resultado)
        metricas = resultado['metricas_scoring']
        self.assertIn('distancia_total_km', metricas)
        self.assertIn('diversidad', metricas)
        self.assertIn('coherencia_tematica', metricas)

    def test_metricas_son_numericas_y_en_rango(self):
        from creacion.langgraph.nodes.scoring import nodo_scoring
        state = self._state_con_pois_validados()
        metricas = nodo_scoring(state)['metricas_scoring']

        self.assertGreaterEqual(metricas['distancia_total_km'], 0.0)
        self.assertGreaterEqual(metricas['diversidad'], 0.0)
        self.assertLessEqual(metricas['diversidad'], 1.0)
        self.assertGreaterEqual(metricas['coherencia_tematica'], 0.0)
        self.assertLessEqual(metricas['coherencia_tematica'], 1.0)

    def test_lista_vacia_devuelve_ceros(self):
        from creacion.langgraph.nodes.scoring import nodo_scoring
        state = _estado_base()
        state['pois_crudos'] = []
        state['razones_descarte'] = []
        state['pois_validados'] = []
        metricas = nodo_scoring(state)['metricas_scoring']

        self.assertEqual(metricas['distancia_total_km'], 0.0)
        self.assertEqual(metricas['diversidad'], 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Nodo 4: Optimización
# ─────────────────────────────────────────────────────────────────────────────

class NodoOptimizacionTestCase(TestCase):

    def _state_con_pois_validados(self, pois=None):
        state = _estado_base()
        state['pois_crudos'] = []
        state['razones_descarte'] = []
        state['metricas_scoring'] = {}
        state['pois_validados'] = pois or [
            _poi_validado('A', 37.386, -5.992),
            _poi_validado('B', 37.383, -5.990),
            _poi_validado('C', 37.377, -5.987),
        ]
        return state

    def test_devuelve_ruta_final_con_paradas_ordenadas(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion
        state = self._state_con_pois_validados()
        resultado = nodo_optimizacion(state)

        self.assertIn('ruta_final', resultado)
        ruta = resultado['ruta_final']
        self.assertIn('paradas', ruta)
        self.assertEqual(len(ruta['paradas']), 3)

    def test_paradas_tienen_orden_secuencial(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion
        state = self._state_con_pois_validados()
        paradas = nodo_optimizacion(state)['ruta_final']['paradas']

        ordenes = [p['orden'] for p in paradas]
        self.assertEqual(ordenes, list(range(1, len(paradas) + 1)))

    def test_un_poi_no_requiere_ortools(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion
        state = self._state_con_pois_validados(pois=[_poi_validado('Solo', 37.386, -5.992)])
        ruta = nodo_optimizacion(state)['ruta_final']

        self.assertEqual(len(ruta['paradas']), 1)
        self.assertIn('Sin optimización', ruta['descripcion'])

    def test_lista_vacia_devuelve_paradas_vacias(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion
        state = self._state_con_pois_validados(pois=[])
        ruta = nodo_optimizacion(state)['ruta_final']

        self.assertEqual(ruta['paradas'], [])

    def test_ruta_final_contiene_campos_requeridos(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion
        state = self._state_con_pois_validados()
        ruta = nodo_optimizacion(state)['ruta_final']

        for campo in ('titulo', 'descripcion', 'duracion_estimada', 'nivel_exigencia', 'mood', 'paradas'):
            self.assertIn(campo, ruta)


# ─────────────────────────────────────────────────────────────────────────────
# Integración: grafo completo
# ─────────────────────────────────────────────────────────────────────────────

class GrafoCompletoTestCase(TestCase):
    """
    Verifica que el grafo compilado ejecuta los 4 nodos en orden y devuelve
    el state con todos los artefactos intermedios.
    """

    @patch('creacion.langgraph.nodes.optimizacion.pywrapcp')
    @patch('creacion.langgraph.nodes.validacion.OSMGeocodingClient')
    @patch('creacion.langgraph.nodes.validacion.MapboxGeocodingClient')
    @patch('creacion.langgraph.nodes.validacion.completar_lista_paradas_validadas')
    @patch('creacion.langgraph.nodes.generacion._obtener_pois_allowlist', return_value=[])
    @patch('creacion.langgraph.nodes.generacion.llamar_gemini')
    def test_grafo_produce_todos_los_artefactos_de_estado(
        self,
        mock_gemini,
        _mock_allowlist,
        mock_completar,
        _mock_mapbox,
        _mock_osm,
        mock_pywrapcp,
    ):
        pois_gemini = [_poi_crudo('A'), _poi_crudo('B'), _poi_crudo('C'), _poi_crudo('D')]
        mock_gemini.return_value = pois_gemini

        validadas = [
            {**_poi_crudo('A'), 'coordenadas': [37.386, -5.992],
             'fuente_validacion': 'mapbox', 'tipo_geometria': 'point',
             'error_m': 0.0, 'corregida': False},
            {**_poi_crudo('B'), 'coordenadas': [37.383, -5.990],
             'fuente_validacion': 'mapbox', 'tipo_geometria': 'point',
             'error_m': 0.0, 'corregida': False},
        ]
        mock_completar.return_value = validadas

        # OR-Tools mock — solución nula → fallback a orden original
        mock_routing = MagicMock()
        mock_routing.SolveWithParameters.return_value = None
        mock_pywrapcp.RoutingModel.return_value = mock_routing
        mock_manager = MagicMock()
        mock_manager.IndexToNode.side_effect = lambda i: i
        mock_pywrapcp.RoutingIndexManager.return_value = mock_manager

        from creacion.langgraph.graph import construir_grafo
        grafo = construir_grafo()
        state_resultado = grafo.invoke({'usuario_input': {
            'ciudad': 'Sevilla',
            'duracion': 2,
            'personas': 4,
            'exigencia': 'media',
            'mood': ['historia'],
        }})

        # Verifica artefactos intermedios presentes
        self.assertIn('pois_crudos', state_resultado)
        self.assertIn('pois_validados', state_resultado)
        self.assertIn('razones_descarte', state_resultado)
        self.assertIn('metricas_scoring', state_resultado)
        self.assertIn('ruta_final', state_resultado)

        # Verifica que las métricas tienen las claves correctas
        metricas = state_resultado['metricas_scoring']
        self.assertIn('distancia_total_km', metricas)
        self.assertIn('diversidad', metricas)
        self.assertIn('coherencia_tematica', metricas)

        # Verifica que la ruta final tiene paradas
        self.assertGreater(len(state_resultado['ruta_final']['paradas']), 0)