# Generación de rutas con IA (explicación intuitiva)

Este documento explica el flujo de generación de rutas IA en AURA como si siguiéramos una ruta real: primero entendemos el encargo del guía, luego proponemos paradas, las verificamos en mapa, medimos calidad y, por último, guardamos la ruta.

## Idea general en 20 segundos

La IA no "adivina una ruta final" en un solo paso. En realidad, AURA hace un pipeline:

1. Normaliza y valida el encargo del guía.
2. Genera candidatos (allowlist primero, Gemini cuando hace falta).
3. Valida coordenadas y elimina duplicados.
4. Puntúa calidad (distancia, diversidad, coherencia temática).
5. Ordena paradas con OR-Tools (TSP).
6. Repite ese pipeline para varias alternativas y se queda con la mejor.
7. Guarda la ruta y el contexto de decisión (checkpoints, restricciones, descartes).

## Dónde vive cada parte en código

- Entrada HTTP y flujo de producto: `creacion/views.py`
- Reglas de negocio y orquestación principal: `creacion/services.py`
- Pipeline por nodos (LangGraph): `creacion/langgraph/graph.py`
- Nodos del pipeline:
  - `creacion/langgraph/nodes/generacion.py`
  - `creacion/langgraph/nodes/validacion.py`
  - `creacion/langgraph/nodes/scoring.py`
  - `creacion/langgraph/nodes/optimizacion.py`
- Utilidades de métricas/prompt/Gemini: `creacion/langgraph/utils.py`

## Paso 1: el guía hace un encargo, no una ruta cerrada

Cuando el frontend llama a `POST /crear-ruta/api/generar/`, el backend:

1. Valida permisos (solo guías autenticados).
2. Aplica reglas de plan (tiers).
3. Normaliza payload (`normalizar_payload_ia`):
   - Ciudad obligatoria y válida.
   - Duración en incrementos de 0.5h.
   - Mood válido (al menos uno).
   - Restricciones/deseos/metadata normalizados.

Resultado mental: pasamos de "texto suelto del usuario" a "encargo estructurado y seguro".

## Paso 2: se abre una sesión IA con memoria de trabajo

Antes de generar, se crea una sesión de generación con TTL renovable (`crear_estado_sesion_generacion`):

- `checkpoint_actual`
- `contexto_generacion` (ciudad, duración, personas, exigencia, mood)
- `restricciones_usuario`
- `paradas_propuestas`
- `paradas_rechazadas`

Esto permite:

- Reanudar flujo sin perder contexto.
- Modo selección del guía.
- Pedir paradas adicionales después.
- Trazar por qué se guardó una ruta.

## Paso 3: generación de candidatos (nodo `generacion`)

Prioridad real:

1. Allowlist curada suficiente: se usa directamente.
2. Allowlist parcial: se usa base curada + Gemini completa faltantes.
3. Allowlist vacía: Gemini genera todo.

Además, el número objetivo de paradas no es fijo:

- Aproximación: `duracion_horas * 2`
- Límite: mínimo 5, máximo 8

Intuición: para 2h suelen salir ~5 paradas; para 4h no se dispara indefinidamente porque se acota en 8.

## Paso 4: validación geográfica estricta (nodo `validacion`)

Aquí AURA convierte ideas en puntos realmente usables:

1. Normaliza formato de cada parada.
2. Valida coordenadas y coherencia geográfica.
3. Deduplica por nombre y coordenada.
4. Intenta completar faltantes con nuevas sugerencias.
5. Usa Mapbox/OSM para corregir y verificar geometrías.

Si no se puede converger al tamaño objetivo de paradas válidas, se considera fallo de integración para ese intento de alternativa.

## Paso 5: scoring de calidad (nodo `scoring`)

Con paradas ya válidas, calcula tres métricas:

1. `distancia_total_km`
2. `diversidad`
3. `coherencia_tematica`

La coherencia se estima buscando señales de mood en nombre/descripcion/categoria. Si no hay moods, parte de una neutralidad razonable.

## Paso 6: optimización de orden (nodo `optimizacion`)

Con OR-Tools (TSP) se busca un orden de visita más eficiente:

1. Crea matriz de distancias entre paradas.
2. Ejecuta solver.
3. Devuelve ruta final ordenada.

Si OR-Tools no encuentra solución, devuelve el orden original para no bloquear la experiencia.

## Paso 7: no se genera una sola ruta, se comparan alternativas

`consultar_langgraph` ejecuta varias alternativas (hasta un máximo configurable, por defecto 3).  
Cada alternativa corre el pipeline completo de 4 nodos.

Después se elige la mejor con score ponderado:

- Distancia (normalizada): 45%
- Diversidad: 30%
- Coherencia temática: 25%

También se adjuntan métricas de alternativas evaluadas para trazabilidad.

## Paso 8: guardar (o dejar seleccionar al guía)

En `generar_ruta_ia` hay dos modos:

1. `modo_seleccion = false`:
   - Se guarda directamente la ruta IA en BD (`guardar_ruta_ia`).
   - Se registra checkpoint `ruta_guardada`.
2. `modo_seleccion = true`:
   - Se devuelve propuesta sin guardar.
   - El guía elige paradas y confirma después en `POST /crear-ruta/api/generar/confirmar/`.

En confirmación:

- Solo se guardan paradas seleccionadas.
- Las no seleccionadas se registran como rechazadas por guía.
- Se conserva `checkpoint_contexto` (restricciones + descartes).

## Paso 9: paradas adicionales y reemplazos IA

Con la misma sesión abierta, el guía puede:

1. Pedir paradas adicionales (`POST /crear-ruta/api/generar/adicionales/`).
2. Pedir sugerencias IA para una ruta ya generada (`POST /crear-ruta/api/rutas/<ruta_id>/paradas-ia/`).

Estas acciones usan:

- Contexto de ciudad/mood/paradas existentes.
- Restricciones acumuladas.
- Dedupe y control geográfico para evitar repetir o salirse del área.

## Checkpoints típicos del flujo

Ejemplos que verás en sesión:

- `payload_normalizado`
- `ruta_generada`
- `validacion_paradas`
- `paradas_adicionales_generadas`
- `seleccion_paradas_guia`
- `sugerencias_generadas`
- `ruta_guardada`

Piensa en ellos como "hitos de conversación" entre guía e IA.

## Qué pasa cuando algo falla

El sistema intenta degradar con elegancia:

1. Si una alternativa IA falla, se prueban otras.
2. Si Gemini no responde en algunos flujos, se intenta fallback con allowlist.
3. Si faltan permisos o reglas de plan, devuelve error de negocio claro.
4. Si falla persistencia, devuelve error controlado.
5. Si expira la sesión, pide reiniciar generación.

Objetivo práctico: no perder trabajo del guía y mantener trazabilidad.

## Resumen mental final

La generación IA en AURA es un proceso por capas:

1. Entender el encargo.
2. Proponer candidatos.
3. Convertirlos en lugares geográficamente fiables.
4. Medir calidad de ruta.
5. Ordenar de forma eficiente.
6. Dar control al guía para decidir y ajustar.

Por eso el resultado suele sentirse "asistido y verificable", no "mágico pero opaco".
