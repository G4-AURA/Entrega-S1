"""
tests/test_e2e_generacion_ruta_ia.py

Pruebas end-to-end del flujo completo de generación de rutas con IA.

Cubren:
  1. Generación de POIs con Gemini (mockeado).
  2. Validación y corrección de coordenadas (mocks de Mapbox/OSM).
  3. Scoring (distancia, diversidad, coherencia temática).
  4. Optimización del orden de paradas con OR-Tools.
  5. Recálculo de geometría real con GraphHopper (mockeado).
  6. Persistencia en BD (Ruta + Parada).
  7. Flujo HTTP completo a través de las vistas Django.
  8. Sesión de generación: checkpoints y recuperación de estado.
  9. Modo selección: propuesta → confirmación parcial.
  10. Serialización JSON para el mapa interactivo (frontend).

IMPORTANTE: Ningún test realiza llamadas reales a Gemini, Mapbox,
OSM ni GraphHopper. Todos los servicios externos se mockean para
garantizar determinismo, velocidad y cero gasto de cuota API.

Ejecución:
    python manage.py test creacion.tests.test_e2e_generacion_ruta_ia --verbosity=2
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth.models import User
from django.contrib.gis.geos import LineString, Point
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from creacion import services as creacion_services
from creacion.langgraph.utils import (
    calcular_coherencia_tematica,
    calcular_distancia_total_km,
    calcular_diversidad_paradas,
)
from creacion.services import (
    ErrorIntegracionIA,
    ErrorValidacionRuta,
    consultar_langgraph,
    guardar_ruta_ia,
    normalizar_payload_ia,
)
from rutas.models import AuthUser, Guia, Parada, Ruta
from rutas.services import (
    obtener_paradas_json,
    recalcular_ruta_graphhopper,
    serializar_resultado_graphhopper,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures reutilizables
# ─────────────────────────────────────────────────────────────────────────────

def _crear_guia(username: str = "guia_e2e") -> tuple[User, Guia]:
    """Crea un usuario + perfil de guía para usar en tests."""
    user = User.objects.create_user(username=username, password="testpass123")
    auth_user = AuthUser.objects.create(user=user)
    guia = Guia.objects.create(user=auth_user, tipo_suscripcion=Guia.Suscripcion.PREMIUM)
    return user, guia


# POIs que simula devolver Gemini para una ruta histórica en Sevilla.
_POIS_GEMINI_SEVILLA = [
    {
        "nombre": "Catedral de Sevilla",
        "coords": [37.3861, -5.9927],
        "desc": "La catedral gótica más grande del mundo.",
        "categoria": "historia",
    },
    {
        "nombre": "Real Alcázar",
        "coords": [37.3836, -5.9902],
        "desc": "Palacio árabe declarado Patrimonio de la Humanidad.",
        "categoria": "historia",
    },
    {
        "nombre": "Archivo de Indias",
        "coords": [37.3851, -5.9927],
        "desc": "Archivo histórico de la colonización americana.",
        "categoria": "historia",
    },
    {
        "nombre": "Plaza de España",
        "coords": [37.3771, -5.9863],
        "desc": "Monumento emblemático de la Exposición de 1929.",
        "categoria": "arquitectura",
    },
    {
        "nombre": "Torre del Oro",
        "coords": [37.3824, -5.9963],
        "desc": "Torre albarrana del siglo XIII a orillas del Guadalquivir.",
        "categoria": "historia",
    },
]

# Resultado que devuelve el grafo LangGraph tras el pipeline completo.
_RUTA_GENERADA_COMPLETA = {
    "titulo": "Ruta Historia Inteligente",
    "descripcion": "Ruta optimizada con algoritmo TSP.",
    "duracion_estimada": 3.0,
    "nivel_exigencia": "media",
    "mood": ["Historia"],
    "paradas": [
        {
            "nombre": "Catedral de Sevilla",
            "coordenadas": [37.3861, -5.9927],
            "orden": 1,
            "descripcion": "La catedral gótica más grande del mundo.",
            "fuente_validacion": "osm_nominatim",
            "tipo_geometria": "building",
            "error_m": 4.2,
            "corregida": False,
        },
        {
            "nombre": "Archivo de Indias",
            "coordenadas": [37.3851, -5.9927],
            "orden": 2,
            "descripcion": "Archivo histórico de la colonización americana.",
            "fuente_validacion": "osm_nominatim",
            "tipo_geometria": "point",
            "error_m": 2.1,
            "corregida": False,
        },
        {
            "nombre": "Real Alcázar",
            "coordenadas": [37.3836, -5.9902],
            "orden": 3,
            "descripcion": "Palacio árabe declarado Patrimonio de la Humanidad.",
            "fuente_validacion": "mapbox",
            "tipo_geometria": "point",
            "error_m": 8.5,
            "corregida": True,
        },
        {
            "nombre": "Torre del Oro",
            "coordenadas": [37.3824, -5.9963],
            "orden": 4,
            "descripcion": "Torre albarrana del siglo XIII.",
            "fuente_validacion": "osm_nominatim",
            "tipo_geometria": "point",
            "error_m": 1.0,
            "corregida": False,
        },
        {
            "nombre": "Plaza de España",
            "coordenadas": [37.3771, -5.9863],
            "orden": 5,
            "descripcion": "Monumento emblemático de la Exposición de 1929.",
            "fuente_validacion": "mapbox",
            "tipo_geometria": "area",
            "error_m": 6.3,
            "corregida": True,
        },
    ],
    "paradas_rechazadas_validacion": [],
    "alternativas_evaluadas": [
        {"score_total": 0.82, "metricas": {"distancia_total_km": 3.1, "diversidad": 0.8, "coherencia_tematica": 0.9}},
    ],
    "metricas_seleccion": {
        "distancia_total_km": 3.1,
        "diversidad": 0.8,
        "coherencia_tematica": 0.9,
    },
}

# Payload normalizado que envía el frontend al endpoint /api/generar/
_PAYLOAD_FRONTEND = {
    "ciudad": "Sevilla",
    "duracion": 3,
    "personas": 8,
    "exigencia": "media",
    "mood": ["historia"],
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Normalización y validación de payload
# ─────────────────────────────────────────────────────────────────────────────

class NormalizacionPayloadE2ETest(TestCase):
    """Valida que el payload del frontend se normaliza correctamente antes
    de entrar al pipeline de IA."""

    @patch("creacion.services.validar_ciudad_existe", return_value=True)
    def test_payload_valido_se_normaliza_con_exigencia_y_moods(self, _mock_ciudad):
        payload = normalizar_payload_ia(_PAYLOAD_FRONTEND)

        self.assertEqual(payload["ciudad"], "Sevilla")
        self.assertAlmostEqual(payload["duracion"], 3.0)
        self.assertEqual(payload["personas"], 8)
        self.assertEqual(payload["exigencia"], Ruta.Exigencia.MEDIA)
        self.assertIn(Ruta.Mood.HISTORIA, payload["mood"])

    @patch("creacion.services.validar_ciudad_existe", return_value=True)
    def test_payload_sin_ciudad_lanza_error_validacion(self, _mock_ciudad):
        datos = {**_PAYLOAD_FRONTEND, "ciudad": ""}
        with self.assertRaises(ErrorValidacionRuta):
            normalizar_payload_ia(datos)

    @patch("creacion.services.validar_ciudad_existe", return_value=True)
    def test_payload_con_duracion_no_valida_lanza_error(self, _mock_ciudad):
        """Duración que no es múltiplo de 0.5 debe rechazarse."""
        datos = {**_PAYLOAD_FRONTEND, "duracion": 2.3}
        with self.assertRaises(ErrorValidacionRuta):
            normalizar_payload_ia(datos)

    @patch("creacion.services.validar_ciudad_existe", return_value=True)
    def test_payload_sin_moods_lanza_error(self, _mock_ciudad):
        datos = {**_PAYLOAD_FRONTEND, "mood": []}
        with self.assertRaises(ErrorValidacionRuta):
            normalizar_payload_ia(datos)

    @patch("creacion.services.validar_ciudad_existe", return_value=True)
    def test_payload_con_deseos_personalizados_se_preservan(self, _mock_ciudad):
        datos = {**_PAYLOAD_FRONTEND, "deseos": ["Evitar escaleras", "Rutas con sombra"]}
        payload = normalizar_payload_ia(datos)
        self.assertIn("Evitar escaleras", payload["deseos"])
        self.assertIn("Rutas con sombra", payload["deseos"])


# ─────────────────────────────────────────────────────────────────────────────
# 2. Pipeline LangGraph — nodo a nodo
# ─────────────────────────────────────────────────────────────────────────────

class NodoGeneracionE2ETest(TestCase):
    """Prueba el nodo de generación de POIs de forma aislada."""

    @patch("creacion.langgraph.nodes.generacion._obtener_pois_allowlist", return_value=[])
    @patch("creacion.langgraph.nodes.generacion.llamar_gemini")
    def test_nodo_devuelve_lista_de_pois_validos(self, mock_gemini, _mock_allowlist):
        mock_gemini.return_value = _POIS_GEMINI_SEVILLA

        from creacion.langgraph.nodes.generacion import nodo_generacion

        state = {
            "usuario_input": {
                "ciudad": "Sevilla",
                "duracion": 3.0,
                "personas": 8,
                "exigencia": "media",
                "mood": ["Historia"],
            }
        }
        resultado = nodo_generacion(state)

        self.assertIn("pois_crudos", resultado)
        self.assertEqual(len(resultado["pois_crudos"]), 5)
        self.assertEqual(resultado["pois_crudos"][0]["nombre"], "Catedral de Sevilla")

    @patch("creacion.langgraph.nodes.generacion.calcular_objetivo_paradas_ia", return_value=5)
    @patch("creacion.langgraph.nodes.generacion._construir_pois_fallback_allowlist")
    @patch("creacion.langgraph.nodes.generacion._obtener_pois_allowlist", return_value=[])
    @patch("creacion.langgraph.nodes.generacion.llamar_gemini")
    def test_nodo_usa_fallback_cuando_gemini_falla(
        self, mock_gemini, _mock_allowlist, mock_fallback, mock_calcular_obj
    ):
        from creacion.langgraph.nodes.generacion import ErrorIntegracionIA
        
        mock_gemini.side_effect = ErrorIntegracionIA("timeout simulado")
        mock_fallback.return_value = _POIS_GEMINI_SEVILLA

        from creacion.langgraph.nodes.generacion import nodo_generacion

        state = {
            "usuario_input": {
                "ciudad": "Sevilla",
                "duracion": 3.0,
                "personas": 8,
                "exigencia": "media",
                "mood": ["Historia"],
            }
        }
        resultado = nodo_generacion(state)
        
        self.assertEqual(len(resultado["pois_crudos"]), 5)
        mock_fallback.assert_called_once()


class NodoValidacionE2ETest(TestCase):
    """Prueba el nodo de validación geográfica de POIs."""

    def _state_con_pois(self, pois=None):
        return {
            "usuario_input": {
                "ciudad": "Sevilla",
                "duracion": 3.0,
                "personas": 8,
                "exigencia": "media",
                "mood": ["Historia"],
            },
            "pois_crudos": pois or _POIS_GEMINI_SEVILLA,
        }

    @patch("creacion.langgraph.nodes.validacion.OSMGeocodingClient")
    @patch("creacion.langgraph.nodes.validacion.MapboxGeocodingClient")
    @patch("creacion.langgraph.nodes.validacion.completar_lista_paradas_validadas")
    def test_nodo_devuelve_pois_validados_con_metadatos(
        self, mock_completar, _mock_mapbox, _mock_osm
    ):
        validadas = [
            {
                **_POIS_GEMINI_SEVILLA[i],
                "coordenadas": _POIS_GEMINI_SEVILLA[i]["coords"],
                "fuente_validacion": "osm_nominatim",
                "tipo_geometria": "point",
                "error_m": 3.0,
                "corregida": False,
            }
            for i in range(5)
        ]
        mock_completar.return_value = validadas

        from creacion.langgraph.nodes.validacion import nodo_validacion

        resultado = nodo_validacion(self._state_con_pois())

        self.assertEqual(len(resultado["pois_validados"]), 5)
        self.assertIsInstance(resultado["razones_descarte"], list)
        # Todos los POIs validados deben tener metadatos de validación
        for poi in resultado["pois_validados"]:
            self.assertIn("fuente_validacion", poi)
            self.assertIn("tipo_geometria", poi)

    @patch("creacion.langgraph.nodes.validacion.OSMGeocodingClient")
    @patch("creacion.langgraph.nodes.validacion.MapboxGeocodingClient")
    @patch("creacion.langgraph.nodes.validacion.completar_lista_paradas_validadas")
    def test_nodo_registra_paradas_descartadas(
        self, mock_completar, _mock_mapbox, _mock_osm
    ):
        """Solo 3 de 5 POIs pasan la validación; los 2 restantes deben aparecer en razones_descarte."""
        validadas = [
            {
                **_POIS_GEMINI_SEVILLA[i],
                "coordenadas": _POIS_GEMINI_SEVILLA[i]["coords"],
                "fuente_validacion": "mapbox",
                "tipo_geometria": "point",
                "error_m": 2.0,
                "corregida": False,
            }
            for i in range(3)
        ]
        mock_completar.return_value = validadas

        from creacion.langgraph.nodes.validacion import nodo_validacion

        resultado = nodo_validacion(self._state_con_pois())

        self.assertEqual(len(resultado["pois_validados"]), 3)
        self.assertGreaterEqual(len(resultado["razones_descarte"]), 2)


class NodoScoringE2ETest(TestCase):
    """Prueba el nodo de scoring de calidad."""

    def _state_con_pois_validados(self):
        pois_validados = [
            {
                "nombre": p["nombre"],
                "coords": p["coords"],
                "desc": p["desc"],
                "categoria": p["categoria"],
                "fuente_validacion": "osm_nominatim",
                "tipo_geometria": "point",
                "error_m": 2.0,
                "corregida": False,
            }
            for p in _POIS_GEMINI_SEVILLA
        ]
        return {
            "usuario_input": {
                "ciudad": "Sevilla",
                "duracion": 3.0,
                "personas": 8,
                "exigencia": "media",
                "mood": ["Historia"],
            },
            "pois_crudos": _POIS_GEMINI_SEVILLA,
            "razones_descarte": [],
            "pois_validados": pois_validados,
        }

    def test_metricas_contienen_las_tres_dimensiones(self):
        from creacion.langgraph.nodes.scoring import nodo_scoring

        resultado = nodo_scoring(self._state_con_pois_validados())
        metricas = resultado["metricas_scoring"]

        self.assertIn("distancia_total_km", metricas)
        self.assertIn("diversidad", metricas)
        self.assertIn("coherencia_tematica", metricas)

    def test_distancia_total_es_positiva_con_multiples_paradas(self):
        from creacion.langgraph.nodes.scoring import nodo_scoring

        resultado = nodo_scoring(self._state_con_pois_validados())
        distancia = resultado["metricas_scoring"]["distancia_total_km"]
        self.assertGreater(distancia, 0.0)

    def test_diversidad_esta_normalizada_entre_0_y_1(self):
        from creacion.langgraph.nodes.scoring import nodo_scoring

        resultado = nodo_scoring(self._state_con_pois_validados())
        diversidad = resultado["metricas_scoring"]["diversidad"]
        self.assertGreaterEqual(diversidad, 0.0)
        self.assertLessEqual(diversidad, 1.0)

    def test_coherencia_tematica_es_alta_para_ruta_historica(self):
        """Paradas con categoría 'historia' deben dar coherencia alta."""
        from creacion.langgraph.nodes.scoring import nodo_scoring

        resultado = nodo_scoring(self._state_con_pois_validados())
        coherencia = resultado["metricas_scoring"]["coherencia_tematica"]
        self.assertGreaterEqual(coherencia, 0.5)

    def test_estado_vacio_devuelve_ceros(self):
        from creacion.langgraph.nodes.scoring import nodo_scoring

        state_vacio = {
            "usuario_input": {"ciudad": "Sevilla", "duracion": 2.0, "personas": 4, "exigencia": "media", "mood": []},
            "pois_crudos": [],
            "razones_descarte": [],
            "pois_validados": [],
        }
        resultado = nodo_scoring(state_vacio)
        self.assertEqual(resultado["metricas_scoring"]["distancia_total_km"], 0.0)
        self.assertEqual(resultado["metricas_scoring"]["diversidad"], 0.0)


class NodoOptimizacionE2ETest(TestCase):
    """Prueba el nodo de optimización OR-Tools."""

    def _state_con_pois_validados(self, n: int = 5):
        pois = [
            {
                "nombre": _POIS_GEMINI_SEVILLA[i]["nombre"],
                "coords": _POIS_GEMINI_SEVILLA[i]["coords"],
                "desc": _POIS_GEMINI_SEVILLA[i]["desc"],
                "categoria": _POIS_GEMINI_SEVILLA[i]["categoria"],
                "fuente_validacion": "osm_nominatim",
                "tipo_geometria": "point",
                "error_m": 2.0,
                "corregida": False,
            }
            for i in range(n)
        ]
        return {
            "usuario_input": {
                "ciudad": "Sevilla",
                "duracion": 3.0,
                "personas": 8,
                "exigencia": "media",
                "mood": ["Historia"],
            },
            "pois_crudos": [],
            "razones_descarte": [],
            "metricas_scoring": {"distancia_total_km": 3.1, "diversidad": 0.8, "coherencia_tematica": 0.9},
            "pois_validados": pois,
        }

    def test_ruta_final_tiene_paradas_con_orden_secuencial(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion

        resultado = nodo_optimizacion(self._state_con_pois_validados())
        paradas = resultado["ruta_final"]["paradas"]

        self.assertEqual(len(paradas), 5)
        ordenes = [p["orden"] for p in paradas]
        self.assertEqual(ordenes, list(range(1, 6)))

    def test_ruta_final_contiene_campos_obligatorios(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion

        resultado = nodo_optimizacion(self._state_con_pois_validados())
        ruta = resultado["ruta_final"]

        for campo in ("titulo", "descripcion", "duracion_estimada", "nivel_exigencia", "mood", "paradas"):
            self.assertIn(campo, ruta)

    def test_paradas_conservan_metadatos_de_validacion(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion

        resultado = nodo_optimizacion(self._state_con_pois_validados())
        for parada in resultado["ruta_final"]["paradas"]:
            self.assertIn("nombre", parada)
            self.assertIn("coordenadas", parada)
            self.assertIn("fuente_validacion", parada)

    def test_lista_vacia_de_pois_devuelve_ruta_con_cero_paradas(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion

        resultado = nodo_optimizacion(self._state_con_pois_validados(n=0))
        self.assertEqual(resultado["ruta_final"]["paradas"], [])

    def test_un_solo_poi_no_necesita_ortools(self):
        from creacion.langgraph.nodes.optimizacion import nodo_optimizacion

        resultado = nodo_optimizacion(self._state_con_pois_validados(n=1))
        self.assertEqual(len(resultado["ruta_final"]["paradas"]), 1)
        # Con 1 parada la descripción no indica optimización TSP
        self.assertNotIn("TSP", resultado["ruta_final"]["descripcion"])


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pipeline completo vía grafo LangGraph
# ─────────────────────────────────────────────────────────────────────────────

class GrafoCompletoE2ETest(TestCase):
    """Ejecuta el pipeline de 4 nodos de extremo a extremo con mocks mínimos."""

    @patch("creacion.langgraph.nodes.optimizacion.pywrapcp")
    @patch("creacion.langgraph.nodes.validacion.OSMGeocodingClient")
    @patch("creacion.langgraph.nodes.validacion.MapboxGeocodingClient")
    @patch("creacion.langgraph.nodes.validacion.completar_lista_paradas_validadas")
    @patch("creacion.langgraph.nodes.generacion._obtener_pois_allowlist", return_value=[])
    @patch("creacion.langgraph.nodes.generacion.llamar_gemini")
    def test_pipeline_produce_ruta_final_con_todos_los_artefactos(
        self,
        mock_gemini,
        _mock_allowlist,
        mock_completar,
        _mock_mapbox,
        _mock_osm,
        mock_pywrapcp,
    ):
        mock_gemini.return_value = _POIS_GEMINI_SEVILLA

        validadas = [
            {
                **poi,
                "coordenadas": poi["coords"],
                "fuente_validacion": "osm_nominatim",
                "tipo_geometria": "point",
                "error_m": 3.0,
                "corregida": False,
            }
            for poi in _POIS_GEMINI_SEVILLA
        ]
        mock_completar.return_value = validadas

        # OR-Tools: sin solución óptima → fallback al orden original
        mock_routing = MagicMock()
        mock_routing.SolveWithParameters.return_value = None
        mock_pywrapcp.RoutingModel.return_value = mock_routing
        mock_manager = MagicMock()
        mock_manager.IndexToNode.side_effect = lambda i: i
        mock_pywrapcp.RoutingIndexManager.return_value = mock_manager

        from creacion.langgraph.graph import construir_grafo

        grafo = construir_grafo()
        state = grafo.invoke({
            "usuario_input": {
                "ciudad": "Sevilla",
                "duracion": 3.0,
                "personas": 8,
                "exigencia": "media",
                "mood": ["Historia"],
            }
        })

        # Todos los artefactos deben estar presentes
        self.assertIn("pois_crudos", state)
        self.assertIn("pois_validados", state)
        self.assertIn("razones_descarte", state)
        self.assertIn("metricas_scoring", state)
        self.assertIn("ruta_final", state)

        # La ruta final tiene paradas con orden correcto
        paradas = state["ruta_final"]["paradas"]
        self.assertEqual(len(paradas), 5)
        ordenes = [p["orden"] for p in paradas]
        self.assertEqual(ordenes, list(range(1, 6)))

        # Las métricas son coherentes
        metricas = state["metricas_scoring"]
        self.assertGreater(metricas["distancia_total_km"], 0)
        self.assertGreaterEqual(metricas["diversidad"], 0)
        self.assertGreaterEqual(metricas["coherencia_tematica"], 0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Persistencia en base de datos
# ─────────────────────────────────────────────────────────────────────────────

class PersistenciaRutaE2ETest(TestCase):
    """Verifica que la ruta generada por IA se persiste correctamente en BD."""

    def setUp(self):
        _, self.guia = _crear_guia("guia_persistencia")

    def test_guardar_ruta_ia_crea_ruta_y_paradas(self):
        payload = {
            "ciudad": "Sevilla",
            "duracion": 3.0,
            "personas": 8,
            "exigencia": Ruta.Exigencia.MEDIA,
            "mood": [Ruta.Mood.HISTORIA],
        }

        ruta = guardar_ruta_ia(
            guia=self.guia,
            payload=payload,
            ruta_generada=_RUTA_GENERADA_COMPLETA,
        )

        self.assertIsNotNone(ruta.id)
        self.assertTrue(ruta.es_generada_ia)
        self.assertEqual(ruta.guia, self.guia)
        self.assertEqual(ruta.nivel_exigencia, Ruta.Exigencia.MEDIA)
        self.assertIn(Ruta.Mood.HISTORIA, ruta.mood)

    def test_guardar_ruta_ia_crea_paradas_con_coordenadas_correctas(self):
        payload = {
            "ciudad": "Sevilla",
            "duracion": 3.0,
            "personas": 8,
            "exigencia": Ruta.Exigencia.MEDIA,
            "mood": [Ruta.Mood.HISTORIA],
        }

        ruta = guardar_ruta_ia(
            guia=self.guia,
            payload=payload,
            ruta_generada=_RUTA_GENERADA_COMPLETA,
        )

        paradas = list(ruta.paradas.order_by("orden"))
        self.assertEqual(len(paradas), 5)

        # La primera parada debe ser la Catedral
        primera = paradas[0]
        self.assertEqual(primera.nombre, "Catedral de Sevilla")
        self.assertAlmostEqual(primera.coordenadas.y, 37.3861, places=3)
        self.assertAlmostEqual(primera.coordenadas.x, -5.9927, places=3)

    def test_guardar_ruta_ia_lanza_error_si_paradas_sin_coordenadas(self):
        payload = {"ciudad": "Sevilla"}
        ruta_invalida = {
            "paradas": [{"nombre": "Sin coordenadas"}]
        }
        with self.assertRaises(ErrorValidacionRuta):
            guardar_ruta_ia(guia=self.guia, payload=payload, ruta_generada=ruta_invalida)

    def test_guardar_ruta_ia_lanza_error_si_no_hay_paradas(self):
        payload = {"ciudad": "Sevilla"}
        with self.assertRaises(ErrorValidacionRuta):
            guardar_ruta_ia(guia=self.guia, payload=payload, ruta_generada={"paradas": []})

    def test_titulo_generado_contiene_ciudad_y_fecha(self):
        from django.utils import timezone

        payload = {
            "ciudad": "Sevilla",
            "duracion": 3.0,
            "personas": 8,
            "exigencia": Ruta.Exigencia.MEDIA,
            "mood": [Ruta.Mood.HISTORIA],
        }
        ruta = guardar_ruta_ia(
            guia=self.guia,
            payload=payload,
            ruta_generada=_RUTA_GENERADA_COMPLETA,
        )
        fecha_hoy = timezone.localtime().strftime("%Y-%m-%d")
        self.assertIn("Sevilla", ruta.titulo)
        self.assertIn(fecha_hoy, ruta.titulo)

    def test_descripcion_de_paradas_se_persiste(self):
        payload = {
            "ciudad": "Sevilla",
            "duracion": 3.0,
            "personas": 8,
            "exigencia": Ruta.Exigencia.MEDIA,
            "mood": [Ruta.Mood.HISTORIA],
        }
        ruta = guardar_ruta_ia(
            guia=self.guia,
            payload=payload,
            ruta_generada=_RUTA_GENERADA_COMPLETA,
        )
        primera_parada = ruta.paradas.order_by("orden").first()
        self.assertIn("gótica", primera_parada.descripcion)


# ─────────────────────────────────────────────────────────────────────────────
# 5. GraphHopper — recálculo de geometría
# ─────────────────────────────────────────────────────────────────────────────

class GraphHopperE2ETest(TestCase):
    """Prueba el recálculo de geometría vía GraphHopper (mockeado)."""

    def setUp(self):
        _, self.guia = _crear_guia("guia_graphhopper")
        self.ruta = Ruta.objects.create(
            titulo="Ruta GH E2E",
            duracion_horas=3.0,
            num_personas=8,
            nivel_exigencia=Ruta.Exigencia.MEDIA,
            mood=[Ruta.Mood.HISTORIA],
            es_generada_ia=True,
            guia=self.guia,
        )
        # Crear 3 paradas con coordenadas reales de Sevilla
        coords_sevilla = [
            (37.3861, -5.9927),  # Catedral
            (37.3836, -5.9902),  # Alcázar
            (37.3824, -5.9963),  # Torre del Oro
        ]
        for i, (lat, lon) in enumerate(coords_sevilla, start=1):
            Parada.objects.create(
                ruta=self.ruta,
                orden=i,
                nombre=f"Parada {i}",
                coordenadas=Point(lon, lat, srid=4326),
            )

    @patch("rutas.graphhopper.calcular_ruta")
    def test_recalculo_persiste_geometria_y_distancia_en_bd(self, mock_calcular):
        from django.contrib.gis.geos import LineString as GEOSLineString
        from rutas.graphhopper import ResultadoRuta, SegmentoMetricas

        geometria_simulada = GEOSLineString(
            [(-5.9927, 37.3861), (-5.9902, 37.3836), (-5.9963, 37.3824)],
            srid=4326,
        )
        mock_calcular.return_value = ResultadoRuta(
            geometria=geometria_simulada,
            distancia_total_m=2850.0,
            duracion_total_s=2040,
            segmentos=[
                SegmentoMetricas(parada_origen_id=self.ruta.paradas.order_by("orden")[0].id, distancia_m=1500.0, duracion_s=1080),
                SegmentoMetricas(parada_origen_id=self.ruta.paradas.order_by("orden")[1].id, distancia_m=1350.0, duracion_s=960),
            ],
        )

        exitoso = recalcular_ruta_graphhopper(self.ruta)

        self.assertTrue(exitoso)
        self.ruta.refresh_from_db()
        self.assertAlmostEqual(self.ruta.distancia_total_m, 2850.0)
        self.assertEqual(self.ruta.duracion_total_s, 2040)
        self.assertIsNotNone(self.ruta.geometria_ruta)

    @patch("rutas.graphhopper.calcular_ruta")
    def test_recalculo_guarda_metricas_por_segmento_en_paradas(self, mock_calcular):
        from django.contrib.gis.geos import LineString as GEOSLineString
        from rutas.graphhopper import ResultadoRuta, SegmentoMetricas

        paradas_ordenadas = list(self.ruta.paradas.order_by("orden"))
        geometria_simulada = GEOSLineString(
            [(-5.9927, 37.3861), (-5.9902, 37.3836), (-5.9963, 37.3824)],
            srid=4326,
        )
        mock_calcular.return_value = ResultadoRuta(
            geometria=geometria_simulada,
            distancia_total_m=2850.0,
            duracion_total_s=2040,
            segmentos=[
                SegmentoMetricas(parada_origen_id=paradas_ordenadas[0].id, distancia_m=1500.0, duracion_s=1080),
                SegmentoMetricas(parada_origen_id=paradas_ordenadas[1].id, distancia_m=1350.0, duracion_s=960),
            ],
        )

        recalcular_ruta_graphhopper(self.ruta)

        paradas_actualizadas = list(self.ruta.paradas.order_by("orden"))
        # Primera parada: tiene segmento hacia la siguiente
        self.assertAlmostEqual(paradas_actualizadas[0].distancia_siguiente_m, 1500.0)
        self.assertEqual(paradas_actualizadas[0].duracion_siguiente_s, 1080)
        # Segunda parada: tiene segmento hacia la siguiente
        self.assertAlmostEqual(paradas_actualizadas[1].distancia_siguiente_m, 1350.0)
        # Tercera parada (última): sin segmento hacia siguiente
        self.assertIsNone(paradas_actualizadas[2].distancia_siguiente_m)

    @patch("rutas.graphhopper.calcular_ruta")
    def test_recalculo_retorna_false_si_graphhopper_falla(self, mock_calcular):
        from rutas.graphhopper import GraphHopperError

        mock_calcular.side_effect = GraphHopperError("API key inválida simulada")

        exitoso = recalcular_ruta_graphhopper(self.ruta)

        self.assertFalse(exitoso)
        # La geometría no debe quedar con datos sucios
        self.ruta.refresh_from_db()
        # distancia sigue None ya que no se actualizó
        self.assertIsNone(self.ruta.distancia_total_m)

    def test_recalculo_retorna_false_con_menos_de_dos_paradas(self):
        """Con 1 parada no hay ruta que calcular."""
        ruta_1_parada = Ruta.objects.create(
            titulo="Ruta 1 Parada",
            duracion_horas=1.0,
            num_personas=4,
            guia=self.guia,
        )
        Parada.objects.create(
            ruta=ruta_1_parada,
            orden=1,
            nombre="Única Parada",
            coordenadas=Point(-5.9927, 37.3861, srid=4326),
        )

        exitoso = recalcular_ruta_graphhopper(ruta_1_parada)
        self.assertFalse(exitoso)

    @patch("rutas.graphhopper.calcular_ruta")
    def test_serializar_resultado_devuelve_formato_leaflet(self, mock_calcular):
        """La geometría debe convertirse a [[lat, lon], ...] para Leaflet."""
        from django.contrib.gis.geos import LineString as GEOSLineString
        from rutas.graphhopper import ResultadoRuta, SegmentoMetricas

        paradas_ordenadas = list(self.ruta.paradas.order_by("orden"))
        geometria_simulada = GEOSLineString(
            [(-5.9927, 37.3861), (-5.9902, 37.3836), (-5.9963, 37.3824)],
            srid=4326,
        )
        mock_calcular.return_value = ResultadoRuta(
            geometria=geometria_simulada,
            distancia_total_m=2850.0,
            duracion_total_s=2040,
            segmentos=[
                SegmentoMetricas(parada_origen_id=paradas_ordenadas[0].id, distancia_m=1500.0, duracion_s=1080),
            ],
        )
        recalcular_ruta_graphhopper(self.ruta)

        datos = serializar_resultado_graphhopper(self.ruta)

        self.assertEqual(datos["status"], "ok")
        self.assertIsNotNone(datos["geometria"])
        # Formato Leaflet: [lat, lon] (y, x)
        primer_punto = datos["geometria"][0]
        self.assertEqual(len(primer_punto), 2)
        # Latitud debe ser el primer elemento (~37.x para Sevilla)
        self.assertGreater(primer_punto[0], 30)  # lat > 30
        # Distancia en km con 1 decimal
        self.assertEqual(datos["distancia_total_km"], "2.9")
        self.assertEqual(datos["duracion_total_min"], 34)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Flujo HTTP completo (vistas Django)
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class FlujHttpGeneracionRutaE2ETest(TestCase):
    """Prueba el flujo completo a través de las vistas HTTP."""

    def setUp(self):
        self.client = Client()
        self.user, self.guia = _crear_guia("guia_http_e2e")
        self.client.force_login(self.user)
        self.url_generar = reverse("creacion:generar_ruta_ia")
        self.url_catalogo = reverse("rutas-catalogo")

    @patch("creacion.services.guardar_ruta_ia")
    @patch("creacion.views._obtener_guia_para_usuario")
    @patch("creacion.tasks.consultar_langgraph")
    def test_flujo_completo_crea_ruta_y_devuelve_200_con_campos_esperados(
        self, mock_langgraph, mock_get_guia, mock_guardar
    ):
        mock_langgraph.return_value = _RUTA_GENERADA_COMPLETA
        mock_get_guia.return_value = self.guia
        ruta_stub = Ruta.objects.create(
            titulo="Sevilla 2026-03-24",
            duracion_horas=3.0,
            num_personas=8,
            nivel_exigencia=Ruta.Exigencia.MEDIA,
            mood=[Ruta.Mood.HISTORIA],
            es_generada_ia=True,
            guia=self.guia,
        )
        mock_guardar.return_value = ruta_stub

        response = self.client.post(
            self.url_generar,
            data=json.dumps(_PAYLOAD_FRONTEND),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertIn("historial_id", data)
        self.assertIn("sesion_generacion_id", data)
        self.assertEqual(data["checkpoint_actual"], "procesando_ia")
        
        # Como estamos en ALWAYS_EAGER, la tarea ya terminó. 
        # Al consultar la sesión, el "lazy sync" debería actualizarla a ruta_guardada.
        session_id = data["sesion_generacion_id"]
        response_poll = self.client.get(
            reverse("creacion:obtener_sesion_generacion_ia", kwargs={"session_id": session_id})
        )
        self.assertEqual(response_poll.status_code, 200)
        data_poll = response_poll.json()["datos"]
        self.assertEqual(data_poll["checkpoint_actual"], "ruta_guardada")
        self.assertIn("paradas_propuestas", data_poll)

    def test_endpoint_rechaza_usuario_no_autenticado_con_401(self):
        cliente_anonimo = Client()
        response = cliente_anonimo.post(
            self.url_generar,
            data=json.dumps(_PAYLOAD_FRONTEND),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_endpoint_rechaza_json_malformado_con_400(self):
        response = self.client.post(
            self.url_generar,
            data="{ciudad: sin_comillas}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_endpoint_rechaza_payload_con_campos_faltantes_con_400(self):
        response = self.client.post(
            self.url_generar,
            data=json.dumps({"ciudad": "Sevilla"}),  # faltan duracion, personas, etc.
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("creacion.tasks.consultar_langgraph")
    def test_endpoint_retorna_202_y_luego_error_en_sesion_si_langgraph_falla(self, mock_langgraph):
        mock_langgraph.side_effect = ErrorIntegracionIA("Gemini caído simulado")

        response = self.client.post(
            self.url_generar,
            data=json.dumps(_PAYLOAD_FRONTEND),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        session_id = response.json()["sesion_generacion_id"]

        # Polling para ver el error
        response_poll = self.client.get(
            reverse("creacion:obtener_sesion_generacion_ia", kwargs={"session_id": session_id})
        )
        data_poll = response_poll.json()["datos"]
        self.assertEqual(data_poll["checkpoint_actual"], "error")
        self.assertIn("Gemini caído simulado", data_poll["mensaje_error"])

    @patch("creacion.services.guardar_ruta_ia")
    @patch("creacion.views._obtener_guia_para_usuario")
    @patch("creacion.tasks.consultar_langgraph")
    def test_catalogo_muestra_ruta_ia_recien_creada(
        self, mock_langgraph, mock_get_guia, mock_guardar
    ):
        """Tras crear la ruta, debe aparecer en el catálogo del guía."""
        mock_langgraph.return_value = _RUTA_GENERADA_COMPLETA
        mock_get_guia.return_value = self.guia

        # Crear la ruta real en BD para que aparezca en el catálogo
        ruta = Ruta.objects.create(
            titulo="Sevilla E2E",
            duracion_horas=3.0,
            num_personas=8,
            nivel_exigencia=Ruta.Exigencia.MEDIA,
            mood=[Ruta.Mood.HISTORIA],
            es_generada_ia=True,
            guia=self.guia,
        )
        mock_guardar.return_value = ruta

        self.client.post(
            self.url_generar,
            data=json.dumps(_PAYLOAD_FRONTEND),
            content_type="application/json",
        )

        response = self.client.get(self.url_catalogo, {"tipo": "ia"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        titulos = [r["titulo"] for r in data["results"]]
        self.assertIn("Sevilla E2E", titulos)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Recálculo de ruta via endpoint AJAX
# ─────────────────────────────────────────────────────────────────────────────

class RecalcularRutaAjaxE2ETest(TestCase):
    """Prueba el endpoint AJAX de recálculo GraphHopper desde la vista de detalle."""

    def setUp(self):
        self.client = Client()
        self.user, self.guia = _crear_guia("guia_recalc")
        self.client.force_login(self.user)

        self.ruta = Ruta.objects.create(
            titulo="Ruta Recálculo E2E",
            duracion_horas=2.0,
            num_personas=10,
            nivel_exigencia=Ruta.Exigencia.BAJA,
            mood=[Ruta.Mood.HISTORIA],
            es_generada_ia=True,
            guia=self.guia,
        )
        coords = [(37.3861, -5.9927), (37.3836, -5.9902), (37.3771, -5.9863)]
        for i, (lat, lon) in enumerate(coords, start=1):
            Parada.objects.create(
                ruta=self.ruta,
                orden=i,
                nombre=f"Parada Recalc {i}",
                coordenadas=Point(lon, lat, srid=4326),
            )

    @patch("rutas.graphhopper.calcular_ruta")
    def test_endpoint_recalcular_devuelve_geometria_y_metricas(self, mock_calcular):
        from django.contrib.gis.geos import LineString as GEOSLineString
        from rutas.graphhopper import ResultadoRuta, SegmentoMetricas

        paradas_ordenadas = list(self.ruta.paradas.order_by("orden"))
        mock_calcular.return_value = ResultadoRuta(
            geometria=GEOSLineString(
                [(-5.9927, 37.3861), (-5.9902, 37.3836), (-5.9863, 37.3771)],
                srid=4326,
            ),
            distancia_total_m=4200.0,
            duracion_total_s=3000,
            segmentos=[
                SegmentoMetricas(parada_origen_id=paradas_ordenadas[0].id, distancia_m=2000.0, duracion_s=1440),
                SegmentoMetricas(parada_origen_id=paradas_ordenadas[1].id, distancia_m=2200.0, duracion_s=1560),
            ],
        )

        url = reverse("ruta-recalcular", args=[self.ruta.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIsNotNone(data["geometria"])
        self.assertEqual(data["distancia_total_km"], "4.2")
        self.assertEqual(data["duracion_total_min"], 50)
        self.assertIsInstance(data["segmentos"], list)
        self.assertEqual(len(data["segmentos"]), 2)

    @patch("rutas.graphhopper.calcular_ruta")
    def test_endpoint_recalcular_geometria_en_formato_leaflet(self, mock_calcular):
        """Verifica que cada punto de la geometría sea [lat, lon] para Leaflet."""
        from django.contrib.gis.geos import LineString as GEOSLineString
        from rutas.graphhopper import ResultadoRuta, SegmentoMetricas

        paradas_ordenadas = list(self.ruta.paradas.order_by("orden"))
        mock_calcular.return_value = ResultadoRuta(
            geometria=GEOSLineString(
                [(-5.9927, 37.3861), (-5.9902, 37.3836), (-5.9863, 37.3771)],
                srid=4326,
            ),
            distancia_total_m=4200.0,
            duracion_total_s=3000,
            segmentos=[
                SegmentoMetricas(parada_origen_id=paradas_ordenadas[0].id, distancia_m=2000.0, duracion_s=1440),
            ],
        )

        url = reverse("ruta-recalcular", args=[self.ruta.id])
        response = self.client.post(url)

        data = response.json()
        geometria = data["geometria"]
        self.assertIsInstance(geometria, list)
        # Formato Leaflet: primer elemento es lat (~37.x para Sevilla)
        for punto in geometria:
            self.assertEqual(len(punto), 2)
            lat, lon = punto
            self.assertGreater(lat, 30)   # lat de Sevilla > 30
            self.assertLess(lat, 45)
            self.assertLess(lon, 0)       # lon de Sevilla < 0 (hemisferio oeste)

    def test_endpoint_recalcular_requiere_autenticacion(self):
        cliente_anonimo = Client()
        url = reverse("ruta-recalcular", args=[self.ruta.id])
        response = cliente_anonimo.post(url)
        self.assertIn(response.status_code, [302, 401, 403])

    def test_endpoint_recalcular_rechaza_ruta_de_otro_guia(self):
        _, otro_guia = _crear_guia("otro_guia_recalc")
        ruta_ajena = Ruta.objects.create(
            titulo="Ruta Ajena",
            duracion_horas=2.0,
            num_personas=5,
            guia=otro_guia,
        )
        url = reverse("ruta-recalcular", args=[ruta_ajena.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Sesión de generación IA — checkpoints
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class SesionGeneracionE2ETest(TestCase):
    """Prueba el ciclo completo de checkpoints de la sesión de generación."""

    def setUp(self):
        self.client = Client()
        self.user, self.guia = _crear_guia("guia_sesion_e2e")
        self.client.force_login(self.user)

    @patch("creacion.services.guardar_ruta_ia")
    @patch("creacion.views._obtener_guia_para_usuario")
    @patch("creacion.tasks.consultar_langgraph")
    def test_ciclo_completo_generar_obtener_actualizar_sesion(
        self, mock_langgraph, mock_get_guia, mock_guardar
    ):
        mock_langgraph.return_value = _RUTA_GENERADA_COMPLETA
        mock_get_guia.return_value = self.guia
        ruta_stub = Mock()
        ruta_stub.id = 42
        mock_guardar.return_value = ruta_stub

        # 1. Generar ruta → obtener session_id
        response_gen = self.client.post(
            reverse("creacion:generar_ruta_ia"),
            data=json.dumps(_PAYLOAD_FRONTEND),
            content_type="application/json",
        )
        self.assertEqual(response_gen.status_code, 202)
        session_id = response_gen.json()["sesion_generacion_id"]
        self.assertTrue(session_id)

        # 2. Obtener estado de la sesión
        response_get = self.client.get(
            reverse("creacion:obtener_sesion_generacion_ia", kwargs={"session_id": session_id})
        )
        self.assertEqual(response_get.status_code, 200)
        estado = response_get.json()["datos"]
        self.assertEqual(estado["checkpoint_actual"], "ruta_guardada")
        self.assertIsInstance(estado["paradas_propuestas"], list)
        self.assertIsInstance(estado["restricciones_usuario"], list)

        # 3. Actualizar checkpoint con feedback del guía
        response_update = self.client.post(
            reverse(
                "creacion:actualizar_checkpoint_sesion_generacion",
                kwargs={"session_id": session_id},
            ),
            data=json.dumps(
                {
                    "checkpoint": "feedback_guia",
                    "parada_rechazada": {
                        "nombre": "Catedral de Sevilla",
                        "coordenadas": [37.3861, -5.9927],
                    },
                    "motivo_rechazo": "Ya la conocen los turistas",
                    "restricciones": ["Evitar monumentos muy conocidos"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response_update.status_code, 200)
        datos_actualizados = response_update.json()["datos"]
        self.assertEqual(datos_actualizados["checkpoint_actual"], "feedback_guia")
        self.assertEqual(len(datos_actualizados["paradas_rechazadas"]), 1)
        self.assertIn("Evitar monumentos muy conocidos", datos_actualizados["restricciones_usuario"])

    @patch("creacion.tasks.consultar_langgraph")
    def test_sesion_no_encontrada_retorna_404(self, _mock_langgraph):
        response = self.client.get(
            reverse(
                "creacion:obtener_sesion_generacion_ia",
                kwargs={"session_id": "id_inexistente_abc123"},
            )
        )
        self.assertEqual(response.status_code, 404)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Modo selección: propuesta → confirmación parcial
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class ModoSeleccionE2ETest(TestCase):
    """Prueba el flujo modo_seleccion: el guía elige qué paradas guardar."""

    def setUp(self):
        self.client = Client()
        self.user, self.guia = _crear_guia("guia_seleccion_e2e")
        self.client.force_login(self.user)

    @patch("creacion.tasks.consultar_langgraph")
    def test_modo_seleccion_true_devuelve_propuesta_sin_guardar(self, mock_langgraph):
        mock_langgraph.return_value = _RUTA_GENERADA_COMPLETA

        payload = {**_PAYLOAD_FRONTEND, "modo_seleccion": True}
        response = self.client.post(
            reverse("creacion:generar_ruta_ia"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["checkpoint_actual"], "procesando_ia")
        self.assertIn("sesion_generacion_id", data)
        
        # Consultamos la sesión para disparar el sync y ver la propuesta
        session_id = data["sesion_generacion_id"]
        response_poll = self.client.get(
            reverse("creacion:obtener_sesion_generacion_ia", kwargs={"session_id": session_id})
        )
        data_poll = response_poll.json()["datos"]
        self.assertEqual(data_poll["checkpoint_actual"], "ruta_generada")
        paradas = data_poll["paradas_propuestas"]
        self.assertEqual(len(paradas), 5)

    @patch("creacion.services.guardar_ruta_ia")
    @patch("creacion.views._obtener_guia_para_usuario")
    @patch("creacion.tasks.consultar_langgraph")
    def test_confirmar_seleccion_parcial_guarda_solo_paradas_elegidas(
        self, mock_langgraph, mock_get_guia, mock_guardar
    ):
        mock_langgraph.return_value = _RUTA_GENERADA_COMPLETA
        mock_get_guia.return_value = self.guia
        ruta_stub = Mock()
        ruta_stub.id = 77
        mock_guardar.return_value = ruta_stub

        # 1. Generar en modo selección
        payload_seleccion = {**_PAYLOAD_FRONTEND, "modo_seleccion": True}
        response_gen = self.client.post(
            reverse("creacion:generar_ruta_ia"),
            data=json.dumps(payload_seleccion),
            content_type="application/json",
        )
        self.assertEqual(response_gen.status_code, 202)
        session_id = response_gen.json()["sesion_generacion_id"]

        # 2. Polling para sincronizar el resultado (necesario incluso en ALWAYS_EAGER para disparar el lazy sync)
        self.client.get(
            reverse("creacion:obtener_sesion_generacion_ia", kwargs={"session_id": session_id})
        )

        # 3. Confirmar solo las paradas 0, 2, 4 (índices pares)
        response_confirm = self.client.post(
            reverse("creacion:confirmar_ruta_ia"),
            data=json.dumps(
                {
                    "sesion_generacion_id": session_id,
                    "seleccion_indices": [0, 2, 4],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response_confirm.status_code, 200)
        data = response_confirm.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["ruta_id"], 77)
        self.assertEqual(data["checkpoint_actual"], "ruta_guardada")

        # Verificar que guardar_ruta fue llamado con 3 paradas seleccionadas
        args, kwargs = mock_guardar.call_args
        paradas_guardadas = kwargs.get("ruta_generada", {}).get("paradas", [])
        self.assertEqual(len(paradas_guardadas), 3)

        # Las paradas rechazadas deben quedar en el contexto del checkpoint
        checkpoint_contexto = data["datos_ruta"].get("checkpoint_contexto", {})
        self.assertEqual(len(checkpoint_contexto.get("paradas_rechazadas", [])), 2)

    @patch("creacion.tasks.consultar_langgraph")
    def test_confirmar_sin_seleccion_retorna_400(self, mock_langgraph):
        mock_langgraph.return_value = _RUTA_GENERADA_COMPLETA

        payload_seleccion = {**_PAYLOAD_FRONTEND, "modo_seleccion": True}
        response_gen = self.client.post(
            reverse("creacion:generar_ruta_ia"),
            data=json.dumps(payload_seleccion),
            content_type="application/json",
        )
        session_id = response_gen.json()["sesion_generacion_id"]

        response_confirm = self.client.post(
            reverse("creacion:confirmar_ruta_ia"),
            data=json.dumps(
                {
                    "sesion_generacion_id": session_id,
                    "seleccion_indices": [],  # Ninguna seleccionada
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response_confirm.status_code, 400)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Serialización JSON para el mapa interactivo
# ─────────────────────────────────────────────────────────────────────────────

class SerializacionMapaE2ETest(TestCase):
    """Verifica que los datos enviados al frontend para el mapa son correctos."""

    def setUp(self):
        _, self.guia = _crear_guia("guia_mapa")
        self.ruta = Ruta.objects.create(
            titulo="Ruta Mapa E2E",
            duracion_horas=3.0,
            num_personas=8,
            nivel_exigencia=Ruta.Exigencia.MEDIA,
            mood=[Ruta.Mood.HISTORIA],
            es_generada_ia=True,
            guia=self.guia,
            geometria_ruta=LineString(
                [(-5.9927, 37.3861), (-5.9902, 37.3836), (-5.9963, 37.3824)],
                srid=4326,
            ),
            distancia_total_m=2850.0,
            duracion_total_s=2040,
        )
        coords = [
            ("Catedral de Sevilla", 37.3861, -5.9927, 1500.0, 1080),
            ("Real Alcázar", 37.3836, -5.9902, 1350.0, 960),
            ("Torre del Oro", 37.3824, -5.9963, None, None),
        ]
        for i, (nombre, lat, lon, dist, dur) in enumerate(coords, start=1):
            Parada.objects.create(
                ruta=self.ruta,
                orden=i,
                nombre=nombre,
                coordenadas=Point(lon, lat, srid=4326),
                distancia_siguiente_m=dist,
                duracion_siguiente_s=dur,
            )

    def test_geometria_ruta_coords_convierte_a_formato_leaflet(self):
        """GEOS almacena (lon, lat); Leaflet espera (lat, lon)."""
        coords = self.ruta.geometria_ruta_coords
        self.assertIsNotNone(coords)
        self.assertIsInstance(coords, list)
        # Primer punto: lat debe ser ~37.x (Sevilla) → debe ser el primer elemento
        primer_punto = coords[0]
        self.assertAlmostEqual(primer_punto[0], 37.3861, places=3)  # lat
        self.assertAlmostEqual(primer_punto[1], -5.9927, places=3)  # lon

    def test_propiedades_distancia_y_duracion_calculadas_correctamente(self):
        self.assertEqual(self.ruta.distancia_total_km, "2.9")
        self.assertEqual(self.ruta.duracion_total_min, 34)

    def test_paradas_json_para_frontend_incluye_coordenadas_y_metricas(self):
        paradas = list(self.ruta.paradas.order_by("orden"))
        datos_json = obtener_paradas_json(paradas)

        self.assertEqual(len(datos_json), 3)
        primera = datos_json[0]
        # Coordenadas en formato Leaflet [lat, lon]
        self.assertEqual(first := primera["coordenadas"], [37.3861, -5.9927])
        self.assertEqual(primera["nombre"], "Catedral de Sevilla")
        self.assertEqual(primera["distancia_siguiente_m"], 1500.0)
        self.assertEqual(primera["duracion_siguiente_min"], 18)  # 1080s / 60 = 18

    def test_ultima_parada_no_tiene_metricas_de_segmento(self):
        paradas = list(self.ruta.paradas.order_by("orden"))
        datos_json = obtener_paradas_json(paradas)

        ultima = datos_json[-1]
        self.assertIsNone(ultima["distancia_siguiente_m"])
        self.assertIsNone(ultima["duracion_siguiente_min"])

    def test_paradas_json_serializable_como_json(self):
        """Los datos deben ser 100% serializables por json.dumps."""
        paradas = list(self.ruta.paradas.order_by("orden"))
        datos_json = obtener_paradas_json(paradas)

        try:
            serializado = json.dumps(datos_json)
            self.assertIsInstance(serializado, str)
        except (TypeError, ValueError) as exc:
            self.fail(f"obtener_paradas_json devolvió datos no serializables: {exc}")

    def test_ruta_sin_geometria_devuelve_none_en_geometria_coords(self):
        """Si la ruta aún no tiene geometría calculada, debe devolver None."""
        ruta_sin_geo = Ruta.objects.create(
            titulo="Sin Geometría",
            duracion_horas=2.0,
            num_personas=5,
            guia=self.guia,
        )
        self.assertIsNone(ruta_sin_geo.geometria_ruta_coords)

    def test_vista_detalle_incluye_geometria_en_contexto(self):
        """La vista de detalle debe pasar geometria_ruta_json al template."""
        self.client = Client()
        self.client.force_login(
            User.objects.get(auth_profile=self.ruta.guia.user)
        )
        url = reverse("ruta-detalle", args=[self.ruta.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # La geometría debe estar disponible en el contexto
        self.assertIn("geometria_ruta_json", response.context)
        geometria = response.context["geometria_ruta_json"]
        self.assertIsNotNone(geometria)
        self.assertIsInstance(geometria, list)
        self.assertGreater(len(geometria), 0)


# ─────────────────────────────────────────────────────────────────────────────
# 11. Prueba de integración: consultar_langgraph con múltiples alternativas
# ─────────────────────────────────────────────────────────────────────────────

class ConsultarLangGraphE2ETest(TestCase):
    """Prueba que consultar_langgraph selecciona la mejor alternativa."""

    @patch("creacion.services._ejecutar_grafo_para_alternativa")
    def test_selecciona_alternativa_con_menor_distancia_y_mayor_coherencia(self, mock_ejecutar):
        alternativa_corta = {
            "ruta": {
                **_RUTA_GENERADA_COMPLETA,
                "titulo": "Alternativa Compacta",
            },
            "metricas": {
                "distancia_total_km": 2.5,
                "diversidad": 0.9,
                "coherencia_tematica": 0.95,
            },
            "paradas_rechazadas_validacion": [],
        }
        alternativa_larga = {
            "ruta": {
                **_RUTA_GENERADA_COMPLETA,
                "titulo": "Alternativa Extensa",
            },
            "metricas": {
                "distancia_total_km": 15.0,
                "diversidad": 0.6,
                "coherencia_tematica": 0.5,
            },
            "paradas_rechazadas_validacion": [],
        }
        mock_ejecutar.side_effect = [alternativa_corta, alternativa_larga]

        payload = {**_PAYLOAD_FRONTEND, "num_alternativas": 2}
        resultado = consultar_langgraph(payload)

        self.assertEqual(resultado["titulo"], "Alternativa Compacta")
        self.assertEqual(len(resultado["alternativas_evaluadas"]), 2)
        self.assertIn("metricas_seleccion", resultado)

    @patch("creacion.services._ejecutar_grafo_para_alternativa")
    def test_descarta_alternativas_fallidas_y_usa_las_validas(self, mock_ejecutar):
        """Si una de las N alternativas falla, se ignora y se selecciona entre las válidas."""
        alternativa_valida = {
            "ruta": {**_RUTA_GENERADA_COMPLETA, "titulo": "La Única"},
            "metricas": {"distancia_total_km": 3.0, "diversidad": 0.8, "coherencia_tematica": 0.9},
            "paradas_rechazadas_validacion": [],
        }
        mock_ejecutar.side_effect = [ErrorIntegracionIA("Fallo simulado"), alternativa_valida]

        resultado = consultar_langgraph({**_PAYLOAD_FRONTEND, "num_alternativas": 2})

        self.assertEqual(resultado["titulo"], "La Única")
        self.assertEqual(len(resultado["alternativas_evaluadas"]), 1)

    @patch("creacion.services._ejecutar_grafo_para_alternativa")
    def test_lanza_error_si_todas_las_alternativas_fallan(self, mock_ejecutar):
        mock_ejecutar.side_effect = ErrorIntegracionIA("Todo falla")

        with self.assertRaises(ErrorIntegracionIA):
            consultar_langgraph({**_PAYLOAD_FRONTEND, "num_alternativas": 2})


# ─────────────────────────────────────────────────────────────────────────────
# 12. Pruebas de métricas de scoring (unitarias, sin BD)
# ─────────────────────────────────────────────────────────────────────────────

class MetricasScoringE2ETest(TestCase):
    """Prueba las funciones de cálculo de métricas de forma directa."""

    def _paradas_historicas(self):
        return [
            {"nombre": "Catedral de Sevilla", "coordenadas": [37.3861, -5.9927], "descripcion": "catedral", "categoria": "historia"},
            {"nombre": "Real Alcázar", "coordenadas": [37.3836, -5.9902], "descripcion": "palacio", "categoria": "historia"},
            {"nombre": "Archivo de Indias", "coordenadas": [37.3851, -5.9927], "descripcion": "archivo historico", "categoria": "historia"},
            {"nombre": "Plaza de España", "coordenadas": [37.3771, -5.9863], "descripcion": "monumento", "categoria": "arquitectura"},
            {"nombre": "Torre del Oro", "coordenadas": [37.3824, -5.9963], "descripcion": "torre medieval", "categoria": "historia"},
        ]

    def test_distancia_total_con_paradas_reales_de_sevilla(self):
        paradas = self._paradas_historicas()
        distancia = calcular_distancia_total_km(paradas)
        # Las paradas están dentro de 5 km del centro
        self.assertGreater(distancia, 0.5)
        self.assertLess(distancia, 10.0)

    def test_diversidad_alta_con_nombres_unicos(self):
        paradas = self._paradas_historicas()
        diversidad = calcular_diversidad_paradas(paradas)
        # 5 nombres únicos de 5 → ratio alto
        self.assertGreater(diversidad, 0.5)

    def test_diversidad_baja_con_nombres_duplicados(self):
        paradas = [
            {"nombre": "Igual", "coordenadas": [37.38, -5.99], "descripcion": "", "categoria": "historia"},
            {"nombre": "Igual", "coordenadas": [37.39, -5.98], "descripcion": "", "categoria": "historia"},
            {"nombre": "Igual", "coordenadas": [37.40, -5.97], "descripcion": "", "categoria": "historia"},
        ]
        diversidad = calcular_diversidad_paradas(paradas)
        self.assertLess(diversidad, 0.5)

    def test_coherencia_alta_con_moods_que_coinciden(self):
        paradas = self._paradas_historicas()
        coherencia = calcular_coherencia_tematica(paradas, ["historia"])
        self.assertGreater(coherencia, 0.5)

    def test_coherencia_baja_con_moods_sin_coincidencias(self):
        paradas = self._paradas_historicas()
        # El mood "naturaleza" no coincide con paradas históricas
        coherencia = calcular_coherencia_tematica(paradas, ["naturaleza"])
        self.assertLess(coherencia, 0.5)

    def test_distancia_cero_con_una_sola_parada(self):
        paradas = [self._paradas_historicas()[0]]
        distancia = calcular_distancia_total_km(paradas)
        self.assertEqual(distancia, 0.0)