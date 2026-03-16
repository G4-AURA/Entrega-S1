"""
creacion/langgraph/graph.py

Construye y devuelve el grafo compilado de LangGraph para la generación
de rutas turísticas.

Flujo lineal (Fase 1):
    generacion → validacion → scoring → optimizacion → END

Cada nodo tiene una responsabilidad única; el state tipado en
creacion/langgraph/state.py define el contrato de datos entre ellos.

La función *construir_grafo* se llama una vez por invocación de
*consultar_langgraph* para obtener un grafo compilado fresco.
"""

from langgraph.graph import END, StateGraph

from creacion.langgraph.nodes.generacion import nodo_generacion
from creacion.langgraph.nodes.optimizacion import nodo_optimizacion
from creacion.langgraph.nodes.scoring import nodo_scoring
from creacion.langgraph.nodes.validacion import nodo_validacion
from creacion.langgraph.state import State


def construir_grafo():
    """Crea y compila el grafo de generación de rutas."""
    workflow = StateGraph(State)

    workflow.add_node("generacion", nodo_generacion)
    workflow.add_node("validacion", nodo_validacion)
    workflow.add_node("scoring", nodo_scoring)
    workflow.add_node("optimizacion", nodo_optimizacion)

    workflow.set_entry_point("generacion")
    workflow.add_edge("generacion", "validacion")
    workflow.add_edge("validacion", "scoring")
    workflow.add_edge("scoring", "optimizacion")
    workflow.add_edge("optimizacion", END)

    return workflow.compile()