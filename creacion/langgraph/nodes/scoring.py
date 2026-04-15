"""
creacion/langgraph/nodes/scoring.py

Nodo 3 del pipeline: calcula métricas de calidad sobre los POIs validados.

Importa únicamente de creacion.langgraph.utils para evitar
importación circular con services.py.
"""

import logging

from creacion.langgraph.state import State
from creacion.langgraph.utils import (
    calcular_coherencia_tematica,
    calcular_distancia_total_km,
    calcular_diversidad_paradas,
)

from creacion.langgraph.utils import medir_tiempo_nodo

logger = logging.getLogger(__name__)

@medir_tiempo_nodo
def nodo_scoring(state: State) -> dict:
    """
    Calcula métricas de calidad de los POIs validados.

    Lee *pois_validados* y escribe *metricas_scoring*.
    """
    logger.debug("--- NODO 3: SCORING DE POIs ---")

    pois = state.get("pois_validados") or []
    moods = (state.get("usuario_input") or {}).get("mood") or []

    # Adaptar formato de optimización al que esperan los helpers de métricas
    paradas_para_metricas = [
        {
            "nombre": poi.get("nombre"),
            "descripcion": poi.get("desc") or "",
            "categoria": poi.get("categoria") or "general",
            "coordenadas": poi.get("coords") or [],
        }
        for poi in pois
    ]

    metricas = {
        "distancia_total_km": round(calcular_distancia_total_km(paradas_para_metricas), 3),
        "diversidad": round(calcular_diversidad_paradas(paradas_para_metricas), 3),
        "coherencia_tematica": round(calcular_coherencia_tematica(paradas_para_metricas, moods), 3),
    }

    logger.debug("Métricas calculadas: %s", metricas)

    return {"metricas_scoring": metricas}