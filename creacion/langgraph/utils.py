"""
creacion/langgraph/utils.py

Utilidades puras compartidas por los nodos del pipeline LangGraph.

Este módulo NO importa nada de creacion.services para evitar importaciones
circulares: services.py → graph.py → nodos → utils.py (sin vuelta atrás).

Contiene únicamente funciones sin estado y sin dependencias de Django ORM
que los nodos necesitan directamente.
"""

import json
import logging
import math
import os

import requests
from config.gemini_keys import iter_gemini_api_keys, is_quota_or_rate_limit_error

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Excepción de integración IA
# services.py es la fuente canónica; esta es un alias de importación segura.
# ─────────────────────────────────────────────────────────────────────────────

from creacion.exceptions import ErrorIntegracionIA


# ─────────────────────────────────────────────────────────────────────────────
# Constantes compartidas
# ─────────────────────────────────────────────────────────────────────────────

MIN_PARADAS_IA = 5
MAX_PARADAS_IA = 8

_KEYWORDS_MOOD = {
    'historia': ['historia', 'historico', 'museo', 'monumento', 'patrimonio'],
    'gastronomia': ['gastronomia', 'mercado', 'tapas', 'cocina', 'comida'],
    'naturaleza': ['parque', 'jardin', 'naturaleza', 'rio', 'mirador'],
    'misterio y leyendas': ['leyenda', 'misterio', 'enigmatico', 'tradicion'],
    'local': ['barrio', 'local', 'plaza', 'cotidiano', 'artesania'],
    'cine y series': ['cine', 'rodaje', 'escena', 'serie'],
    'religioso y espiritual': ['iglesia', 'catedral', 'templo', 'espiritual'],
    'arquitectura y diseño': ['arquitectura', 'diseño', 'fachada', 'edificio'],
    'ocio/cultural': ['teatro', 'galeria', 'cultural', 'ocio', 'espectaculo'],
}


# ─────────────────────────────────────────────────────────────────────────────
# Gemini
# ─────────────────────────────────────────────────────────────────────────────

class _GeminiQuotaError(Exception):
    """Internal marker for quota/rate-limit responses on a concrete API key."""

def _leer_int_env(nombre: str, default: int) -> int:
    try:
        return int(os.getenv(nombre, str(default)))
    except (TypeError, ValueError):
        return default


def _llamar_gemini_con_clave(prompt: str, api_key: str) -> list | dict:
    if not api_key:
        raise ErrorIntegracionIA('No hay API key de Gemini configurada.')

    # USAMOS 2.5-FLASH ESTABLE PARA EVITAR 404/503
    model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}'
    headers = {'Content-Type': 'application/json'}
    data = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generation_config': {'response_mime_type': 'application/json'},
    }
    timeout_s = max(10, _leer_int_env('GEMINI_TIMEOUT_SECONDS', 30))
    max_reintentos = max(0, _leer_int_env('GEMINI_MAX_RETRIES', 2))
    # 429 is handled as quota fallback to the next key, not retried in-place.
    http_reintentable = {408, 409, 425, 500, 502, 503, 504}

    ultimo_error: Exception | None = None
    for intento in range(max_reintentos + 1):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=timeout_s)
            if is_quota_or_rate_limit_error(
                status_code=response.status_code,
                detail=getattr(response, 'text', ''),
            ):
                raise _GeminiQuotaError(f'Gemini devolvió status={response.status_code}.')

            if response.status_code in http_reintentable and intento < max_reintentos:
                logger.warning('Gemini status=%s (reintento %s/%s).', response.status_code, intento + 1, max_reintentos)
                continue
            response.raise_for_status()
            resultado = response.json()
            texto_json = resultado['candidates'][0]['content']['parts'][0]['text']
            return json.loads(texto_json)
        except _GeminiQuotaError:
            raise
        except requests.Timeout as exc:
            ultimo_error = exc
            if intento < max_reintentos:
                continue
            raise ErrorIntegracionIA(f'Timeout tras {max_reintentos + 1} intentos.') from exc
        except requests.HTTPError as exc:
            ultimo_error = exc
            status = exc.response.status_code if exc.response is not None else 'desconocido'
            detalle = getattr(exc.response, 'text', '') if exc.response is not None else ''
            if is_quota_or_rate_limit_error(
                status_code=status if isinstance(status, int) else None,
                detail=detalle,
                exception=exc,
            ):
                raise _GeminiQuotaError(f'Gemini devolvió status={status}.') from exc

            if status in http_reintentable and intento < max_reintentos:
                continue
            raise ErrorIntegracionIA(f'Error HTTP de Gemini (status={status}).') from exc
        except requests.RequestException as exc:
            ultimo_error = exc
            if intento < max_reintentos:
                continue
            raise ErrorIntegracionIA('Error de red al conectar con Gemini.') from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ErrorIntegracionIA('Respuesta no válida de Gemini.') from exc
        except Exception as exc:
            raise ErrorIntegracionIA('Error inesperado al invocar Gemini.') from exc

    raise ErrorIntegracionIA('No se pudo obtener respuesta válida de Gemini.') from ultimo_error


def llamar_gemini(prompt: str) -> list | dict:
    """
    Llama a Gemini y devuelve la respuesta parseada como JSON.
    Lanza ErrorIntegracionIA ante cualquier fallo.
    """
    claves = list(iter_gemini_api_keys())
    if not claves:
        raise ErrorIntegracionIA('No hay API key de Gemini configurada.')
    ultimo_error_cuota: Exception | None = None
    for indice, clave in enumerate(claves, start=1):
        try:
            return _llamar_gemini_con_clave(prompt, clave)
        except _GeminiQuotaError as exc:
            ultimo_error_cuota = exc
            logger.warning(
                'Gemini devolvió cuota/429 en clave %s/%s; se intenta fallback.',
                indice,
                len(claves),
            )
            continue

    if ultimo_error_cuota is not None:
        raise ErrorIntegracionIA('Todas las API keys de Gemini agotaron cuota o devolvieron 429.') from ultimo_error_cuota

    raise ErrorIntegracionIA('No se pudo obtener respuesta válida de Gemini.')


# ─────────────────────────────────────────────────────────────────────────────
# Normalización de coordenadas y POIs
# ─────────────────────────────────────────────────────────────────────────────

def normalizar_coordenadas(raw_coordenadas, lat=None, lon=None):
    if isinstance(raw_coordenadas, dict):
        lat = raw_coordenadas.get('lat')
        lon = raw_coordenadas.get('lon') if raw_coordenadas.get('lon') is not None else raw_coordenadas.get('lng')
    elif isinstance(raw_coordenadas, (list, tuple)) and len(raw_coordenadas) >= 2:
        lat, lon = raw_coordenadas[0], raw_coordenadas[1]
    if lat is None or lon is None:
        return None
    return [float(lat), float(lon)]


def normalizar_poi_para_optimizacion(poi_validado: dict) -> dict:
    return {
        'nombre': poi_validado['nombre'],
        'coords': poi_validado['coordenadas'],
        'desc': (
            poi_validado.get('descripcion')
            or poi_validado.get('justificacion')
            or poi_validado.get('desc')
            or ''
        ),
        'fuente_validacion': poi_validado.get('fuente_validacion'),
        'tipo_geometria': poi_validado.get('tipo_geometria'),
        'error_m': poi_validado.get('error_m'),
        'corregida': poi_validado.get('corregida'),
    }


def serializar_parada_ruta_final(poi: dict, orden: int) -> dict:
    descripcion = str(poi.get('desc') or poi.get('descripcion') or '').strip()
    payload = {
        'nombre': poi.get('nombre'),
        'coordenadas': poi.get('coords'),
        'orden': orden,
        'descripcion': descripcion,
        # Mantener 'desc' por compatibilidad con código existente
        'desc': descripcion,
    }
    for meta_key in ('fuente_validacion', 'tipo_geometria', 'error_m', 'corregida'):
        if meta_key in poi:
            payload[meta_key] = poi.get(meta_key)
    return payload


def normalizar_nombre_para_dedupe(nombre: str) -> str:
    return ' '.join(str(nombre or '').strip().lower().split())


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo de objetivo de paradas
# ─────────────────────────────────────────────────────────────────────────────

def calcular_objetivo_paradas_ia(datos: dict) -> int:
    try:
        duracion_horas = float(datos.get('duracion') or 2.0)
    except (TypeError, ValueError):
        duracion_horas = 2.0
    estimado = int(round(duracion_horas * 2))
    return max(MIN_PARADAS_IA, min(MAX_PARADAS_IA, estimado))


# ─────────────────────────────────────────────────────────────────────────────
# OR-Tools: matriz de distancias
# ─────────────────────────────────────────────────────────────────────────────

def crear_matriz_datos(pois: list) -> dict:
    cant_nodos = len(pois)
    dist_matrix = {}
    for from_node in range(cant_nodos):
        dist_matrix[from_node] = {}
        for to_node in range(cant_nodos):
            if from_node == to_node:
                dist_matrix[from_node][to_node] = 0
            else:
                d_km = distancia_haversine_km(pois[from_node]['coords'], pois[to_node]['coords'])
                dist_matrix[from_node][to_node] = int(d_km * 1000)
    return {'distance_matrix': dist_matrix, 'num_vehicles': 1, 'depot': 0}


# ─────────────────────────────────────────────────────────────────────────────
# Métricas de scoring
# ─────────────────────────────────────────────────────────────────────────────

def distancia_haversine_km(coord_a, coord_b) -> float:
    lat1, lon1 = coord_a
    lat2, lon2 = coord_b
    radio = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return radio * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calcular_distancia_total_km(paradas: list) -> float:
    if len(paradas) < 2:
        return 0.0
    total = 0.0
    for i in range(len(paradas) - 1):
        total += distancia_haversine_km(paradas[i]['coordenadas'], paradas[i + 1]['coordenadas'])
    return total


def calcular_diversidad_paradas(paradas: list) -> float:
    if not paradas:
        return 0.0
    nombres_unicos = {
        normalizar_nombre_para_dedupe(p.get('nombre'))
        for p in paradas if p.get('nombre')
    }
    ratio_nombres = len(nombres_unicos) / len(paradas)
    categorias_unicas = {
        str(p.get('categoria') or '').strip().lower()
        for p in paradas if p.get('categoria')
    }
    ratio_categorias = len(categorias_unicas) / max(1, len(paradas))
    return min(1.0, 0.7 * ratio_nombres + 0.3 * ratio_categorias)


def calcular_coherencia_tematica(paradas: list, moods: list) -> float:
    if not paradas:
        return 0.0
    keywords = []
    for mood in moods or []:
        keywords.extend(_KEYWORDS_MOOD.get(str(mood).strip().lower(), []))
    if not keywords:
        return 0.5
    matches = sum(
        1 for p in paradas
        if any(k in f"{p.get('nombre','')}{p.get('descripcion','')}{p.get('categoria','')}".lower()
               for k in keywords)
    )
    return matches / len(paradas)


# ─────────────────────────────────────────────────────────────────────────────
# Construcción de bloques de prompt
# ─────────────────────────────────────────────────────────────────────────────

def construir_bloque_metadata(metadata: dict) -> str:
    if not metadata:
        return ''
    lineas = ['\n## Contexto adicional del solicitante']
    ubicacion = metadata.get('ubicacion')
    if ubicacion:
        ciudad_origen = ubicacion.get('ciudad') or ubicacion.get('pais') or ''
        if ciudad_origen:
            lineas.append(f'- Ubicación actual del guía: {ciudad_origen}')
        coords = ubicacion.get('coords')
        if coords:
            lineas.append(f'  (coordenadas: {coords[0]:.4f}, {coords[1]:.4f})')
    if metadata.get('idioma'):
        lineas.append(f'- Idioma del navegador: {metadata["idioma"]}')
    if metadata.get('hora_local'):
        lineas.append(f'- Hora local del guía al generar: {metadata["hora_local"]}')
    if metadata.get('zona_horaria'):
        lineas.append(f'- Zona horaria: {metadata["zona_horaria"]}')
    if metadata.get('dispositivo'):
        lineas.append(f'- Tipo de dispositivo: {metadata["dispositivo"]}')
    return '\n'.join(lineas) if len(lineas) > 1 else ''


def construir_bloque_deseos(deseos: list) -> str:
    if not deseos:
        return ''
    items = '\n'.join(f'  - {d}' for d in deseos)
    return f'\n## Preferencias específicas del guía\n{items}'


def construir_bloque_allowlist(pois: list) -> str:
    if not pois:
        return ''
    lineas = [
        '\n## Puntos de Interés recomendados (allowlist curada)',
        'Los siguientes lugares han sido verificados y aprobados para esta ciudad.',
        'Inclúyelos en la ruta siempre que encajen con la temática solicitada:',
    ]
    for poi in pois:
        lat, lon = poi['coords']
        lineas.append(f'  - {poi["nombre"]} ({poi["categoria"]}) — coords: [{lat}, {lon}]')
    return '\n'.join(lineas)