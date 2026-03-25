"""
rutas/graphhopper.py

Cliente HTTP para la API de enrutamiento GraphHopper.

ESTRATEGIA DE LLAMADAS (plan gratuito, límite 5 waypoints):
  Se agrupan las paradas en lotes de hasta 5 waypoints con solapamiento
  de 1 punto en el extremo, lo que da 4 segmentos por lote.

  Comparativa de llamadas (N = número de paradas):
    N=5  → 4 llamadas (pares) vs  1 lote  ← ×4 más eficiente
    N=7  → 6 llamadas (pares) vs  2 lotes ← ×3 más eficiente
    N=10 → 9 llamadas (pares) vs  3 lotes ← ×3 más eficiente

  Las métricas por segmento (parada→siguiente) se extraen del campo
  `instructions` de la respuesta, que contiene marcadores sign=5
  ("via alcanzada") para cada waypoint intermedio. Esto permite obtener
  geometría + métricas de todos los tramos de un lote en una sola llamada,
  sin necesitar llamadas adicionales.
"""
import logging
from dataclasses import dataclass, field

import requests
from django.conf import settings
from django.contrib.gis.geos import LineString

logger = logging.getLogger(__name__)

# Señales de GraphHopper en el campo instructions.sign
_SIGN_VIA_ALCANZADA = 5   # waypoint intermedio alcanzado
_SIGN_DESTINO_FINAL = 4   # destino final alcanzado

# Máximo de waypoints por llamada del plan gratuito
_MAX_WP_POR_LLAMADA = 5


# ─────────────────────────────────────────────────────────────────────────────
# Excepción de dominio
# ─────────────────────────────────────────────────────────────────────────────

class GraphHopperError(Exception):
    """Cualquier fallo irrecuperable al comunicarse con GraphHopper."""


# ─────────────────────────────────────────────────────────────────────────────
# Tipos de retorno
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SegmentoMetricas:
    """Métricas del tramo entre una parada y la siguiente."""
    parada_origen_id: int
    distancia_m: float
    duracion_s: int


@dataclass
class ResultadoRuta:
    """Resultado completo del cálculo de una ruta GraphHopper."""
    geometria: LineString           # Trazado completo sobre la red viaria (SRID 4326)
    distancia_total_m: float        # Suma de distancias de todos los segmentos
    duracion_total_s: int           # Suma de duraciones de todos los segmentos
    segmentos: list[SegmentoMetricas] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privados — configuración y HTTP
# ─────────────────────────────────────────────────────────────────────────────

def _config() -> tuple[str, str, str]:
    """Extrae y valida la configuración de GraphHopper desde settings."""
    base_url = getattr(settings, "GRAPHHOPPER_BASE_URL", "https://graphhopper.com/api/1").rstrip("/")
    api_key  = getattr(settings, "GRAPHHOPPER_API_KEY", "") or ""
    vehicle  = getattr(settings, "GRAPHHOPPER_VEHICLE", "foot")

    if not api_key:
        raise GraphHopperError(
            "GraphHopper no configurado: falta GRAPHHOPPER_API_KEY en settings/env."
        )
    return base_url, api_key, vehicle


def _post_route(base_url: str, api_key: str, points: list[list[float]], vehicle: str) -> dict:
    """
    Llama a POST /route con hasta _MAX_WP_POR_LLAMADA waypoints.

    Args:
        points: Lista de [lon, lat] (GeoJSON, x primero). Máximo 5 elementos.
    Returns:
        El primer elemento de la lista `paths` del JSON de respuesta.
    Raises:
        GraphHopperError: timeout, error HTTP o respuesta sin paths.
    """
    timeout = getattr(settings, "GRAPHHOPPER_TIMEOUT", 10)

    payload = {
        "points": points,
        "vehicle": vehicle,
        "locale": "es",
        "points_encoded": False,   # GeoJSON directo, sin decodificar polyline
        # instructions=True es el valor por defecto de GraphHopper, pero lo hacemos
        # explícito porque son necesarias para extraer métricas por segmento.
        "instructions": True,
    }

    try:
        resp = requests.post(
            f"{base_url}/route",
            params={"key": api_key},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.Timeout:
        raise GraphHopperError(f"Timeout ({timeout}s) al conectar con GraphHopper.")
    except requests.HTTPError as exc:
        try:
            msg = exc.response.json().get("message", str(exc))
        except Exception:
            msg = str(exc)
        raise GraphHopperError(f"Error HTTP GraphHopper ({exc.response.status_code}): {msg}")
    except requests.RequestException as exc:
        raise GraphHopperError(f"Error de red con GraphHopper: {exc}")

    paths = data.get("paths")
    if not paths:
        raise GraphHopperError(
            f"Respuesta inesperada de GraphHopper (sin paths): {data.get('message', data)}"
        )
    return paths[0]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privados — chunking y métricas
# ─────────────────────────────────────────────────────────────────────────────

def _paradas_con_coords(paradas: list) -> list[tuple]:
    """
    Filtra paradas sin coordenadas y devuelve lista de (parada, [lon, lat]).
    """
    return [
        (p, [p.coordenadas.x, p.coordenadas.y])
        for p in paradas
        if p.coordenadas is not None
    ]


def _crear_lotes(paradas_validas: list, max_wp: int = _MAX_WP_POR_LLAMADA) -> list[list]:
    """
    Divide la lista de paradas en lotes de máximo `max_wp` waypoints con
    solapamiento de 1 punto entre lotes consecutivos.

    Cada lote de K waypoints cubre K-1 segmentos.
    El último punto de un lote es el primero del siguiente (punto de unión).

    Ejemplo con 7 paradas y max_wp=5:
      Lote 1: [p1, p2, p3, p4, p5]  →  4 segmentos  →  1 llamada API
      Lote 2: [p5, p6, p7]           →  2 segmentos  →  1 llamada API
      Total: 2 llamadas (vs 6 con pares)

    Args:
        paradas_validas: Lista de (parada, [lon, lat]).
        max_wp: Máximo waypoints por llamada (5 para el plan gratuito).
    Returns:
        Lista de lotes, donde cada lote es una sublista de paradas_validas.
    """
    lotes = []
    i = 0
    n = len(paradas_validas)

    while i < n - 1:
        fin = min(i + max_wp, n)
        lotes.append(paradas_validas[i:fin])
        if fin == n:
            break
        # El último punto del lote es el primero del siguiente (overlap de 1)
        i = fin - 1

    return lotes


def _segmentos_desde_instrucciones(
    instrucciones: list,
    paradas_lote: list,
) -> list[SegmentoMetricas]:
    """
    Extrae métricas por segmento (distancia y duración) a partir de `instructions`.

    GraphHopper incluye en cada instrucción:
      - sign=5 (_SIGN_VIA_ALCANZADA): se ha llegado a un waypoint intermedio
      - sign=4 (_SIGN_DESTINO_FINAL): se ha llegado al destino final del lote

    Estos marcadores dividen las instrucciones exactamente en los segmentos
    que queremos (parada_i → parada_i+1). Las instrucciones de marcador
    tienen distance=0 y time=0; el recorrido real está en las previas.

    Args:
        instrucciones: Lista del campo path["instructions"].
        paradas_lote:  Lista de (parada, waypoint) del lote actual.
    Returns:
        Lista de SegmentoMetricas, uno por par de paradas consecutivas del lote.
    """
    segmentos: list[SegmentoMetricas] = []
    dist_acumulada = 0.0
    dur_acumulada  = 0       # en milisegundos
    seg_idx        = 0       # índice del segmento que estamos completando
    num_segmentos  = len(paradas_lote) - 1

    for inst in instrucciones:
        sign = inst.get("sign", 0)
        dist_acumulada += inst.get("distance", 0.0)
        dur_acumulada  += inst.get("time", 0)       # ms

        if sign in (_SIGN_VIA_ALCANZADA, _SIGN_DESTINO_FINAL):
            if seg_idx < num_segmentos:
                parada_origen = paradas_lote[seg_idx][0]
                segmentos.append(SegmentoMetricas(
                    parada_origen_id=parada_origen.id,
                    distancia_m=dist_acumulada,
                    duracion_s=dur_acumulada // 1000,  # ms → s
                ))
                seg_idx        += 1
                dist_acumulada  = 0.0
                dur_acumulada   = 0

    return segmentos


def _concatenar_geometrias(lista_coords: list[list[list[float]]]) -> LineString:
    """
    Une las geometrías de los N lotes en una única LineString continua.

    GraphHopper repite el punto de llegada de un lote como punto de salida del
    siguiente. Se eliminan esos duplicados (coords_lote[1:] para lotes 2, 3…)
    para obtener una polilínea limpia sin saltos ni puntos dobles.

    Args:
        lista_coords: Lista de listas de [lon, lat] (una por lote).
    Returns:
        LineString GEOS con SRID 4326.
    Raises:
        GraphHopperError: si la geometría resultante tiene menos de 2 puntos.
    """
    coords_totales: list[list[float]] = []

    for i, coords_lote in enumerate(lista_coords):
        if not coords_lote:
            continue
        # El primer punto de los lotes 2, 3… duplica el último del lote anterior
        coords_totales.extend(coords_lote if i == 0 else coords_lote[1:])

    if len(coords_totales) < 2:
        raise GraphHopperError(
            "Geometría insuficiente tras concatenar lotes: se necesitan ≥2 puntos."
        )

    return LineString(coords_totales, srid=4326)


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def calcular_ruta(paradas: list) -> ResultadoRuta:
    """
    Calcula la ruta real sobre la red viaria para la lista de paradas ordenadas.

    Estrategia de llamadas (optimizada para el plan gratuito de 5 waypoints):
      - Se forman lotes de hasta 5 waypoints con solapamiento de 1 punto.
      - Cada lote = 1 llamada API → cubre 4 segmentos.
      - Métricas por segmento: extraídas de `instructions`, sin llamadas extra.
      - Total de llamadas: ceil((N-1) / 4) para N paradas.

    Si un lote falla, los demás continúan (degradación parcial): la geometría
    tendrá un hueco en ese tramo pero el resto se renderiza correctamente.

    Args:
        paradas: Lista de objetos Parada, ya ordenada por campo `orden`.
    Returns:
        ResultadoRuta con geometría completa, totales y segmentos individuales.
    Raises:
        GraphHopperError: si hay < 2 paradas válidas o todos los lotes fallan.
    """
    if len(paradas) < 2:
        raise GraphHopperError("Se necesitan al menos 2 paradas para calcular la ruta.")

    base_url, api_key, vehicle = _config()

    paradas_validas = _paradas_con_coords(paradas)
    if len(paradas_validas) < 2:
        raise GraphHopperError("Insuficientes paradas con coordenadas válidas.")

    lotes = _crear_lotes(paradas_validas, max_wp=_MAX_WP_POR_LLAMADA)

    logger.info(
        "GraphHopper: %d paradas → %d lote(s) de hasta %d waypoints.",
        len(paradas_validas), len(lotes), _MAX_WP_POR_LLAMADA,
    )

    lista_coords_lotes: list[list[list[float]]] = []
    todos_segmentos:    list[SegmentoMetricas]  = []
    distancia_total = 0.0
    duracion_total  = 0

    for idx_lote, lote in enumerate(lotes):
        waypoints = [wp for _, wp in lote]

        try:
            path = _post_route(base_url, api_key, waypoints, vehicle)
        except GraphHopperError as exc:
            logger.warning(
                "Lote %d/%d fallido (%d waypoints): %s",
                idx_lote + 1, len(lotes), len(waypoints), exc,
            )
            continue

        # ── Geometría del lote ────────────────────────────────────────────────
        coords_lote = path["points"]["coordinates"]
        lista_coords_lotes.append(coords_lote)

        # ── Totales del lote ──────────────────────────────────────────────────
        distancia_total += float(path["distance"])
        duracion_total  += int(path["time"]) // 1000   # ms → s

        # ── Métricas por segmento desde instructions (sin llamadas extra) ─────
        instrucciones = path.get("instructions", [])
        if instrucciones:
            segmentos_lote = _segmentos_desde_instrucciones(instrucciones, lote)
            todos_segmentos.extend(segmentos_lote)
        else:
            logger.warning(
                "Lote %d/%d sin instructions; métricas por segmento omitidas.",
                idx_lote + 1, len(lotes),
            )

    if not lista_coords_lotes:
        raise GraphHopperError(
            "Todos los lotes fallaron. No se pudo calcular ningún tramo de la ruta."
        )

    geometria = _concatenar_geometrias(lista_coords_lotes)

    logger.info(
        "GraphHopper: ruta calculada — %.0fm, %ds, %d segmentos, %d lotes.",
        distancia_total, duracion_total, len(todos_segmentos), len(lista_coords_lotes),
    )

    return ResultadoRuta(
        geometria=geometria,
        distancia_total_m=distancia_total,
        duracion_total_s=duracion_total,
        segmentos=todos_segmentos,
    )