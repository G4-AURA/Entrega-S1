"""
creacion/langgraph/nodes/optimizacion.py

Nodo 4 del pipeline: ordena las paradas validadas usando OR-Tools (TSP).

Importa únicamente de creacion.langgraph.utils para evitar
importación circular con services.py.
"""

import logging

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from creacion.langgraph.state import State
from creacion.langgraph.utils import (
    crear_matriz_datos,
    serializar_parada_ruta_final,
    medir_tiempo_nodo,
)

logger = logging.getLogger(__name__)


def _formatear_titulo_mood(mood) -> str:
    """Convierte la lista de moods a un string legible para el título."""
    if isinstance(mood, (list, tuple)):
        partes = [str(m).strip().capitalize() for m in mood if m]
        return ", ".join(partes) if partes else "Turística"
    return str(mood).strip().capitalize() if mood else "Turística"


@medir_tiempo_nodo
def nodo_optimizacion(state: State) -> dict:
    """
    Ordena los POIs validados con el algoritmo TSP de OR-Tools.

    Lee *pois_validados* y escribe *ruta_final*.
    """
    logger.debug("--- NODO 4: OPTIMIZACIÓN DE LA RUTA CON OR-TOOLS ---")

    pois = state.get("pois_validados") or []
    datos = state.get("usuario_input") or {}

    if not pois or len(pois) < 2:
        paradas_directas = [
            serializar_parada_ruta_final(poi, orden=idx)
            for idx, poi in enumerate(pois, start=1)
        ]
        return {
            "ruta_final": {
                "titulo": f"Ruta {_formatear_titulo_mood(datos.get('mood'))}",
                "descripcion": "Ruta generada sin optimización necesaria.",
                "duracion_estimada": datos.get("duracion"),
                "nivel_exigencia": datos.get("exigencia"),
                "mood": datos.get("mood"),
                "paradas": paradas_directas,
            }
        }

    data = crear_matriz_datos(pois)
    manager = pywrapcp.RoutingIndexManager(
        len(data["distance_matrix"]), data["num_vehicles"], data["depot"]
    )
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        return data["distance_matrix"][manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        pois_ordenados = []
        index = routing.Start(0)
        orden = 1
        while not routing.IsEnd(index):
            pois_ordenados.append(
                serializar_parada_ruta_final(pois[manager.IndexToNode(index)], orden=orden)
            )
            index = solution.Value(routing.NextVar(index))
            orden += 1
    else:
        logger.warning("OR-Tools no encontró solución óptima; se devuelve el orden original.")
        pois_ordenados = [
            serializar_parada_ruta_final(poi, orden=idx)
            for idx, poi in enumerate(pois, start=1)
        ]

    return {
        "ruta_final": {
            "titulo": f"Ruta {_formatear_titulo_mood(datos.get('mood'))} Inteligente",
            "descripcion": "Ruta optimizada con algoritmo TSP (Traveling Salesperson Problem).",
            "duracion_estimada": datos.get("duracion"),
            "nivel_exigencia": datos.get("exigencia"),
            "mood": datos.get("mood"),
            "paradas": pois_ordenados,
        }
    }