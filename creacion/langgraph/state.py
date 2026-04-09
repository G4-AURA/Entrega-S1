"""
creacion/langgraph/state.py
 
Define el contrato de estado que fluye entre los nodos del pipeline de
generación de rutas. Cada campo representa un artefacto intermedio de una
etapa concreta.
 
Campos por etapa:
  - usuario_input       → payload normalizado de entrada (inmutable durante el pipeline)
  - pois_crudos         → POIs tal como los devuelve Gemini (pre-validación)
  - razones_descarte    → motivos de rechazo de POIs durante validación
  - pois_validados      → POIs con coordenadas verificadas y deduplicados
  - metricas_scoring    → métricas calculadas sobre los POIs validados
  - ruta_final          → resultado ordenado por OR-Tools listo para persistir
"""
 
from typing import TypedDict
 
 
class State(TypedDict):
    # --- Identidad y Telemetría ---
    historial_id: int
    duraciones: dict[str, float]

    # --- Entrada ---
    usuario_input: dict
 
    # --- Generación (nodo 1) ---
    pois_crudos: list
 
    # --- Validación (nodo 2) ---
    razones_descarte: list   # lista de dicts {nombre, coordenadas, motivo_rechazo}
    pois_validados: list
 
    # --- Scoring (nodo 3) ---
    metricas_scoring: dict   # {distancia_total_km, diversidad, coherencia_tematica}
 
    # --- Optimización (nodo 4) ---
    ruta_final: dict