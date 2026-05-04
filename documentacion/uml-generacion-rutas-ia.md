# UML - Generación de Rutas con IA (estado actual)

Este documento refleja el flujo **actual** de generación de rutas IA con sus condicionales principales, según `creacion/views.py`, `creacion/services.py`, `creacion/langgraph/*` y `creacion/allowlist_selector.py`.

## 1) Flujo end-to-end (`POST /generar_ruta_ia`)

```plantuml
@startuml
title Generar ruta IA - Flujo completo

start

if (Usuario autenticado?) then (No)
  :401 ERROR;
  stop
endif

if (Usuario es turista?) then (Si)
  :403 ERROR;
  stop
endif

if (Body JSON válido?) then (No)
  :400 ERROR;
  stop
endif

:Obtener/crear perfil guía;
if (Guía disponible?) then (No)
  :500 ERROR;
  stop
endif

:ensure_ai_generation_allowed();
if (Tier bloquea IA?) then (Si)
  :error tier;
  stop
endif

:apply_payload_tier_rules();
:normalizar_payload_ia();
if (Payload válido? ciudad, duracion, personas,\nexigencia, mood, deseos...) then (No)
  :400 ERROR;
  stop
endif

:ensure_route_people_count_allowed();
if (Tier bloquea personas?) then (Si)
  :error tier;
  stop
endif

:Crear sesión de generación;
:consultar_langgraph(payload);
if (Ruta dict válida?) then (No)
  :400/502/500 ERROR;
  stop
endif

:clamp_generated_stops_to_tier();
:ensure_people+moods de salida;
if (Tier invalida salida IA?) then (Si)
  :error tier;
  stop
endif

:Guardar checkpoint ruta_generada;
:Registrar paradas rechazadas de validación;

if (modo_seleccion = true?) then (Si)
  :record_ai_generation_usage();
  :200 OK\n(ruta propuesta sin guardar);
  stop
else (No)
  :ensure_stop_count/people/moods;
  if (Tier bloquea guardado?) then (Si)
    :error tier;
    stop
  endif

  :guardar_ruta_ia() en BD;
  if (Persistencia válida?) then (No)
    :500 ERROR;
    stop
  endif

  :checkpoint ruta_guardada;
  :guardar_historial_ruta_ia();
  :200 OK\n(ruta guardada);
  stop
endif

@enduml
```

## 2) Pipeline LangGraph (`consultar_langgraph`)

```plantuml
@startuml
title Pipeline LangGraph + selección de alternativa

start

:Leer num_alternativas;
if (num_alternativas válido?) then (No)
  :usar 3;
endif
:Clamp [1..MAX_ALTERNATIVAS_RUTA];

repeat
  :Ejecutar alternativa con variación prompt;
  if (ErrorIntegracionIA?) then (Si)
    :Descartar alternativa y continuar;
  else (No)
    :Guardar alternativa evaluable;
  endif
repeat while (quedan alternativas?) is (Si)

if (Hay alternativas evaluables?) then (No)
  :ErrorIntegracionIA;
  stop
endif

:Seleccionar mejor alternativa\n(score distancia/diversidad/coherencia);
:Enriquecer ruta_final con métricas\n+ rechazadas + alternativas;
stop

@enduml
```

### 2.1 Nodo `generacion`

```plantuml
@startuml
title Nodo generacion

start
:objetivo_paradas = f(duracion);
:pois_allowlist = _obtener_pois_allowlist(ciudad,moods);

if (n_disponibles >= objetivo?) then (Si)
  :sample allowlist;\nno Gemini;
  :return pois_crudos;
  stop
endif

if (n_disponibles > 0?) then (Si)
  :base allowlist + faltan;
  :Gemini complemento(faltan);
  if (Gemini falla/formato inválido?) then (Si)
    :usar solo allowlist parcial;
  endif
  :return mezcla;
  stop
endif

:Allowlist vacía -> Gemini completo;
if (Gemini devuelve lista válida?) then (Si)
  :return Gemini;
  stop
else (No)
  :fallback allowlist;
  if (fallback >= objetivo?) then (Si)
    :return fallback;
    stop
  else (No)
    :ErrorIntegracionIA;
    stop
  endif
endif

@enduml
```

### 2.2 Nodo `validacion`

```plantuml
@startuml
title Nodo validacion

start
:Leer pois_crudos;
if (pois_crudos es lista?) then (No)
  :ErrorIntegracionIA;
  stop
endif

:Normalizar POIs;
:Calcular contexto geográfico\n(POIs -> allowlist -> sin restricción);
:Completar lista validada\n(geocoding, dedupe, precisión);

if (NoConvergenciaCoordenadas?) then (Si)
  :ErrorIntegracionIA;
  stop
endif

:Construir razones_descarte;
:Mapear a pois_validados;
stop

@enduml
```

### 2.3 Nodo `optimizacion`

```plantuml
@startuml
title Nodo optimizacion

start
:Leer pois_validados;

if (len(pois) < 2?) then (Si)
  :Devolver ruta sin TSP\n(orden directo);
  stop
endif

:Construir matriz distancias;
:Resolver TSP con OR-Tools;

if (OR-Tools encontró solución?) then (Si)
  :Ordenar por solución;
else (No)
  :Usar orden original;
endif

:Devolver ruta_final;
stop

@enduml
```

## 3) Selector allowlist rankeado (`seleccionar_pois_allowlist`)

```plantuml
@startuml
title Selector allowlist (ranking + ciudad + aleatoriedad)

start

:Normalizar ciudad, moods, límite;
:Construir pesos mood->categoría;

if (hay categorías filtrables?) then (Si)
  :Filtrar POI por categoría;
endif

:Resolver CityBoundary activa por nombre normalizado;
:city_qs por ciudad__icontains;

if (Boundary existe?) then (Si)
  :strict_qs = city_qs intersecta polígono;
else (No)
  :strict_qs = city_qs;
endif

:candidates = strict_qs;
if (candidates vacíos?) then (Si)
  :candidates = city_qs;\nsource=city_relaxed;
else (No)
  :source=strict;
endif

if (siguen vacíos?) then (Si)
  :candidates = base_qs;\nsource=global_relaxed;
endif

if (sin candidatos?) then (Si)
  :return [];
  stop
endif

:Scoring por candidato:\n- google_score=1/rank_position (default bajo)\n- mood_score por categoría\n- city_score según source;
:final_score = w_google + w_mood + w_city;

:Ordenar desc por final_score;
:top_k = min(len, max(limite, limite*factor));
:Pool = top_k;
:Muestreo ponderado sin reemplazo\n(aleatoriedad controlada por seed);
:Serializar y return;
stop

@enduml
```

