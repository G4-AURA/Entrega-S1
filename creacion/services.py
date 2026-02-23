import os
import json
import math
import requests
from typing import TypedDict
from langgraph.graph import StateGraph, END

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

class State(TypedDict):
    usuario_input: dict 
    pois_seleccionados: list
    ruta_final: dict


### --- FUNCIONES AUXILIARES --- ###
def llamar_gemini_bypass(prompt, api_key):

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        resultado = response.json()
        texto_json = resultado['candidates'][0]['content']['parts'][0]['text']
        return json.loads(texto_json)
    except Exception as e:
        print(f" ERROR al llamar a la API: {e}")
        """
        Datos de prueba por si la conexión a la IA falla.
        """
        return [
                {"nombre": f"Centro Histórico", "coords": [40.4167, -3.7037], "desc": "Punto de interés principal recomendado."},
                {"nombre": "Parque Principal", "coords": [40.4233, -3.6827], "desc": "Zona verde ideal para el descanso del grupo."},
                {"nombre": "Museo de Arte", "coords": [40.4137, -3.6921], "desc": "Parada cultural imprescindible."},
                {"nombre": "Mirador de la Ciudad", "coords": [40.4070, -3.7115], "desc": "Las mejores vistas para fotografías."},
                {"nombre": "Zona Gastronómica", "coords": [40.4150, -3.7070], "desc": "Lugar perfecto para degustar platos locales."}
            ]

def calcular_distancia(coord1, coord2):
    """Calcula distancia euclidiana entre dos puntos [lat, lon]"""
    return math.sqrt((coord1[0] - coord2[0])**2 + (coord1[1] - coord2[1])**2)

def crear_matriz_datos(pois):
    """Genera la matriz de distancias que necesita OR-Tools"""
    cant_nodos = len(pois)
    dist_matrix = {}
    
    for from_node in range(cant_nodos):
        dist_matrix[from_node] = {}
        for to_node in range(cant_nodos):
            if from_node == to_node:
                dist_matrix[from_node][to_node] = 0
            else:
                d = calcular_distancia(pois[from_node]['coords'], pois[to_node]['coords'])
                dist_matrix[from_node][to_node] = int(d * 10000)
                
    return {
        "distance_matrix": dist_matrix,
        "num_vehicles": 1,
        "depot": 0
    }


### --- NODOS --- ###
def nodo_seleccion_sitios(state: State):
    print("--- NODO 1: GENERACIÓN DE RUTA ---")
    datos = state['usuario_input']
    api_key = os.getenv("GOOGLE_API_KEY")

    prompt = f"""
    Eres un guía experto en {datos.get('ciudad')}. El usuario quiere una ruta de {datos.get('duracion')} horas.
    Temática: {datos.get('mood')}. Exigencia: {datos.get('exigencia')}.
    
    Genera una lista de 5 a 8 Puntos de Interés (POIs).
    Responde ÚNICAMENTE con un JSON válido con esta estructura:
    [
        {{"nombre": "Nombre sitio", "coords": [lat, lon], "desc": "Breve descripción"}}
    ]
    """

    pois = llamar_gemini_bypass(prompt, api_key)
    return {"pois_seleccionados": pois}
    

def nodo_optimizador_ortools(state: State):
    print("--- NODO 2: OPTIMIZACIÓN DE LA RUTA CON OR-TOOLS ---")
    pois = state['pois_seleccionados']
    
    if not pois or len(pois) < 2:
        json_final_simple = {
            "titulo": f"Ruta {state['usuario_input'].get('mood')}",
            "descripcion": "Ruta generada sin optimización necesaria.",
            "duracion_estimada": state['usuario_input'].get('duracion'),
            "nivel_exigencia": state['usuario_input'].get('exigencia'),
            "mood": state['usuario_input'].get('mood'),
            "paradas": pois
        }
        return {"ruta_final": json_final_simple}
    
    # 1. Preparar datos matemáticos
    data = crear_matriz_datos(pois)
    
    # 2. Crear el gestor de rutas y el modelo
    manager = pywrapcp.RoutingIndexManager(len(data['distance_matrix']),
                                           data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    # 3. Definir callback de distancia
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['distance_matrix'][from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    
    # 4. Definir coste (el objetivo es minimizar la distancia total)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # 5. Configurar estrategia de búsqueda
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

    # 6. Resolver
    solution = routing.SolveWithParameters(search_parameters)

    # 7. Construir la ruta ordenada
    pois_ordenados = []
    if solution:
        index = routing.Start(0)
        orden_contador = 1
        
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            poi_actual = pois[node_index]
            
            pois_ordenados.append({
                "nombre": poi_actual['nombre'],
                "coordenadas": poi_actual['coords'], 
                "orden": orden_contador,
                "descripcion": poi_actual.get('desc', '')
            })
            
            index = solution.Value(routing.NextVar(index))
            orden_contador += 1
    else:
        print("No se encontró solución óptima, devolviendo orden original.")
        pois_ordenados = pois

    json_final = {
        "titulo": f"Ruta {state['usuario_input'].get('mood')} Inteligente",
        "descripcion": "Ruta optimizada con algoritmo TSP (Traveling Salesperson Problem).",
        "duracion_estimada": state['usuario_input'].get('duracion'),
        "nivel_exigencia": state['usuario_input'].get('exigencia'),
        "mood": state['usuario_input'].get('mood'),
        "paradas": pois_ordenados
    }

    return {"ruta_final": json_final}


### --- GRAFO --- ###
def construir_grafo():
    workflow = StateGraph(State)
    
    workflow.add_node("agente_turistico", nodo_seleccion_sitios)
    workflow.add_node("matematico", nodo_optimizador_ortools)
    
    # Flujo: Entrada -> IA -> Matemáticas -> Fin
    workflow.set_entry_point("agente_turistico")
    workflow.add_edge("agente_turistico", "matematico")
    workflow.add_edge("matematico", END)
    
    return workflow.compile()

def consultar_langgraph(prompt_params):
    app = construir_grafo()
    resultado = app.invoke({"usuario_input": prompt_params})
    return resultado["ruta_final"]