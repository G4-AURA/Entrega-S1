## Antes
POST /generacion/generar_ruta_ia/
  └─ generar_ruta_ia() [views.py]
       └─ consultar_langgraph(payload) [services.py]  ← loops 1-5 variaciones
            └─ nodo_generacion [nodes/generacion.py]
                 ├─ _obtener_pois_allowlist(ciudad, moods)
                 │    └─ devuelve POIs → solo como CONTEXTO del prompt
                 ├─ construir_bloque_allowlist() → bloque de texto para Gemini
                 ├─ !! SIEMPRE llama llamar_gemini(prompt) !!
                 │    └─ Gemini devuelve lista cruda de POIs
                 │    └─ Si Gemini falla → fallback: _construir_pois_fallback_allowlist()
                 └─ pois_crudos
            ├─ nodo_validacion  (geocodifica coords via Mapbox/OSM)
            ├─ nodo_scoring     (distancia, diversidad, coherencia temática)
            └─ nodo_optimizacion (TSP con OR-Tools)
       └─ _guardar_ruta_ia_en_bd()

## Despues
POST /generacion/generar_ruta_ia/
  └─ generar_ruta_ia() [views.py]
       └─ consultar_langgraph(payload) [services.py]  ← loops 1-5 variaciones
            └─ nodo_generacion [nodes/generacion.py]
                 ├─ _obtener_pois_allowlist(ciudad, moods)
                 │
                 ├─ CASO 1: len(allowlist) >= objetivo_paradas
                 │    └─ Toma los objetivo_paradas POIs mejor priorizados por selector
                 │       (1-3 anclas top + variedad ponderada)
                 │    └─ *** OMITE Gemini completamente ***
                 │
                 ├─ CASO 2: 0 < len(allowlist) < objetivo_paradas  [MIXTO]
                 │    ├─ Toma TODOS los POIs disponibles de allowlist
                 │    └─ Llama Gemini solo para (objetivo - disponibles) stops restantes
                 │         └─ Prompt excluye por nombre los ya seleccionados
                 │
                 └─ CASO 3: len(allowlist) == 0
                      └─ Cancela antes de llamar a Gemini
                      └─ Devuelve: "Esta ciudad no está contemplada en esta version de la aplicacion"
                 │
                 └─ pois_crudos (mezcla o solo allowlist)
            ├─ nodo_validacion  (sin cambios; allowlist POIs pasan coordinadas fiables)
            ├─ nodo_scoring
            └─ nodo_optimizacion
       └─ _guardar_ruta_ia_en_bd()
