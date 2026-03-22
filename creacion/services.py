import os
import json
import math
import logging
import requests
import uuid
from django.contrib.gis.geos import Point
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from creacion.geo_clients import MapboxGeocodingClient, OSMGeocodingClient
from creacion.geo_validation import (
    NoConvergenciaCoordenadasError,
    completar_lista_paradas_validadas,
)
from creacion.langgraph.graph import construir_grafo
from creacion.models import Historial_ia
from rutas.models import AuthUser, Guia, Parada, Ruta

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Excepciones de dominio
# ─────────────────────────────────────────────────────────────────────────────

class ErrorRutaBase(Exception):
    """Clase base para errores de dominio en creación de rutas."""


class ErrorValidacionRuta(ErrorRutaBase):
    """Errores de validación de payload y datos de ruta."""
    def __init__(self, errores):
        if isinstance(errores, str):
            self.errores = {'general': errores}
        elif isinstance(errores, dict):
            self.errores = errores
        else:
            self.errores = {'general': str(errores)}
        super().__init__(str(self.errores))


class ErrorPermisosRuta(ErrorRutaBase):
    """Errores de permisos para crear/guardar rutas."""


class ErrorPersistenciaRuta(ErrorRutaBase):
    """Errores al persistir rutas o su historial en base de datos."""


class ErrorIntegracionIA(ErrorRutaBase):
    """Errores al comunicarse o normalizar respuestas del proveedor de IA."""


class ErrorSesionGeneracionRuta(ErrorRutaBase):
    """Errores de estado/checkpoints de sesión de generación IA."""


class ErrorSesionGeneracionExpirada(ErrorSesionGeneracionRuta):
    """La sesión de generación ya no está disponible por expiración."""


class ErrorSesionGeneracionNoEncontrada(ErrorSesionGeneracionRuta):
    """No existe una sesión de generación para el identificador indicado."""


# ─────────────────────────────────────────────────────────────────────────────
# Constantes y mapas
# ─────────────────────────────────────────────────────────────────────────────

MAPA_MOOD_RUTA = {
    'historia': Ruta.Mood.HISTORIA,
    'gastronomia': Ruta.Mood.GASTRONOMIA,
    'naturaleza': Ruta.Mood.NATURALEZA,
    'misterio-leyendas': Ruta.Mood.MISTERIO_Y_LEYENDAS,
    'misterio y leyendas': Ruta.Mood.MISTERIO_Y_LEYENDAS,
    'local': Ruta.Mood.LOCAL,
    'cine-series': Ruta.Mood.CINE_Y_SERIES,
    'cine y series': Ruta.Mood.CINE_Y_SERIES,
    'religioso-espiritual': Ruta.Mood.RELIGIOSO_Y_ESPIRITUAL,
    'religioso y espiritual': Ruta.Mood.RELIGIOSO_Y_ESPIRITUAL,
    'arquitectura-diseno': Ruta.Mood.ARQUITECTURA_Y_DISEÑO,
    'arquitectura y diseño': Ruta.Mood.ARQUITECTURA_Y_DISEÑO,
    'ocio-cultural': Ruta.Mood.OCIO_CULTURAL,
    'ocio/cultural': Ruta.Mood.OCIO_CULTURAL,
}

MAPA_EXIGENCIA_RUTA = {
    'baja': Ruta.Exigencia.BAJA,
    'media': Ruta.Exigencia.MEDIA,
    'medio': Ruta.Exigencia.MEDIA,
    'alta': Ruta.Exigencia.ALTA,
}

MOOD_MAP = {
    'historia': 'historia',
    'gastronomia': 'gastronomia',
    'naturaleza': 'naturaleza',
    'misterio-leyendas': 'misterio y leyendas',
    'misterio y leyendas': 'misterio y leyendas',
    'local': 'local',
    'cine-series': 'cine y series',
    'cine y series': 'cine y series',
    'religioso-espiritual': 'religioso y espiritual',
    'religioso y espiritual': 'religioso y espiritual',
    'arquitectura-diseno': 'arquitectura y diseño',
    'arquitectura y diseño': 'arquitectura y diseño',
    'ocio-cultural': 'ocio/cultural',
    'ocio/cultural': 'ocio/cultural',
}

EXIGENCIA_MAP = {
    'baja': 'baja',
    'media': 'media',
    'medio': 'media',
    'alta': 'alta',
}

MAX_POIS_ALLOWLIST_EN_PROMPT = 15
SESION_GENERACION_STORE_KEY = 'creacion_ruta_ia_sesiones'
SESION_GENERACION_TTL_SECONDS = 60 * 60 * 6
MIN_PARADAS_IA = 5
MAX_PARADAS_IA = 8
MIN_DURACION_HORAS_MANUAL = 0.5
MAX_DURACION_HORAS_MANUAL = 24.0
MIN_PERSONAS_MANUAL = 1
MAX_PERSONAS_MANUAL = 50
MIN_PARADAS_MANUAL = 2
MAX_REINTENTOS_PARADA_INVALIDA = 3
MAX_ALTERNATIVAS_RUTA = 5
UMBRAL_DISTANCIA_MAXIMA_PARADA_KM = 35.0

_MOOD_A_CATEGORIAS_OSM: dict[str, list[str]] = {
    'historia': [
        'historic=monument', 'historic=castle', 'historic=ruins',
        'tourism=museum', 'amenity=place_of_worship',
    ],
    'gastronomia': [
        'amenity=restaurant', 'amenity=cafe', 'amenity=bar', 'amenity=marketplace',
    ],
    'naturaleza': [
        'leisure=park', 'tourism=viewpoint',
    ],
    'misterio-leyendas': [
        'historic=monument', 'historic=ruins', 'historic=castle',
        'amenity=place_of_worship',
    ],
    'misterio y leyendas': [
        'historic=monument', 'historic=ruins', 'historic=castle',
        'amenity=place_of_worship',
    ],
    'local': [
        'amenity=marketplace', 'place=square', 'amenity=restaurant',
        'amenity=cafe', 'amenity=bar',
    ],
    'cine-series': [
        'amenity=cinema', 'tourism=museum', 'historic=monument',
    ],
    'cine y series': [
        'amenity=cinema', 'tourism=museum', 'historic=monument',
    ],
    'religioso-espiritual': [
        'amenity=place_of_worship', 'historic=monument', 'historic=castle',
    ],
    'religioso y espiritual': [
        'amenity=place_of_worship', 'historic=monument', 'historic=castle',
    ],
    'arquitectura-diseno': [
        'tourism=museum', 'historic=monument', 'historic=castle',
        'tourism=gallery', 'amenity=theatre',
    ],
    'arquitectura y diseño': [
        'tourism=museum', 'historic=monument', 'historic=castle',
        'tourism=gallery', 'amenity=theatre',
    ],
    'ocio-cultural': [
        'amenity=theatre', 'amenity=cinema', 'amenity=library',
        'tourism=gallery', 'tourism=museum', 'leisure=stadium',
    ],
    'ocio/cultural': [
        'amenity=theatre', 'amenity=cinema', 'amenity=library',
        'tourism=gallery', 'tourism=museum', 'leisure=stadium',
    ],
}

_VARIACIONES_ALTERNATIVA = [
    'enfoque historico y monumental',
    'enfoque local y experiencial',
    'enfoque cultural y panoramico',
    'enfoque gastronomico y vida urbana',
    'enfoque naturaleza y espacios abiertos',
]



# ─────────────────────────────────────────────────────────────────────────────
# Funciones auxiliares puras
# ─────────────────────────────────────────────────────────────────────────────

def _leer_int_env(nombre: str, default: int) -> int:
    try:
        return int(os.getenv(nombre, str(default)))
    except (TypeError, ValueError):
        return default


def _normalizar_coordenadas(raw_coordenadas, lat=None, lon=None):
    if isinstance(raw_coordenadas, dict):
        lat = raw_coordenadas.get('lat')
        lon = raw_coordenadas.get('lon') if raw_coordenadas.get('lon') is not None else raw_coordenadas.get('lng')
    elif isinstance(raw_coordenadas, (list, tuple)) and len(raw_coordenadas) >= 2:
        lat, lon = raw_coordenadas[0], raw_coordenadas[1]
    if lat is None or lon is None:
        return None
    return [float(lat), float(lon)]


def _normalizar_nombre_para_dedupe(nombre) -> str:
    return ' '.join(str(nombre or '').strip().lower().split())


def _clave_coordenadas_para_dedupe(coordenadas):
    return (round(float(coordenadas[0]), 5), round(float(coordenadas[1]), 5))


def _distancia_haversine_km(coord_a, coord_b) -> float:
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


def _calcular_contexto_geografico(paradas_existentes) -> dict:
    coords = [p['coordenadas'] for p in paradas_existentes if isinstance(p.get('coordenadas'), list)]
    if not coords:
        return {'centro': [0.0, 0.0], 'radio_km': 8.0}
    centro_lat = sum(c[0] for c in coords) / len(coords)
    centro_lon = sum(c[1] for c in coords) / len(coords)
    centro = [centro_lat, centro_lon]
    radio_actual_km = max(_distancia_haversine_km(centro, c) for c in coords)
    radio_permitido_km = min(30.0, max(8.0, radio_actual_km + 10.0))
    return {'centro': centro, 'radio_km': radio_permitido_km}


def _esta_en_contexto_geografico(coordenadas, contexto_geo) -> bool:
    return _distancia_haversine_km(coordenadas, contexto_geo['centro']) <= contexto_geo['radio_km']


def _calcular_objetivo_paradas_ia(datos: dict) -> int:
    try:
        duracion_horas = float(datos.get('duracion') or 2.0)
    except (TypeError, ValueError):
        duracion_horas = 2.0
    estimado = int(round(duracion_horas * 2))
    return max(MIN_PARADAS_IA, min(MAX_PARADAS_IA, estimado))


def calcular_distancia(coord1, coord2) -> float:
    """Distancia euclidiana entre dos puntos [lat, lon]. Usada por OR-Tools."""
    return math.sqrt((coord1[0] - coord2[0]) ** 2 + (coord1[1] - coord2[1]) ** 2)


def crear_matriz_datos(pois) -> dict:
    """Genera la matriz de distancias para OR-Tools."""
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
    return {'distance_matrix': dist_matrix, 'num_vehicles': 1, 'depot': 0}



def _formatear_exclusiones_para_prompt(
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> str:
    nombres = sorted([n for n in nombres_excluidos if n])[:40]
    coords = [[lat, lon] for lat, lon in sorted(coords_excluidas)[:40]]
    return json.dumps({'nombres': nombres, 'coordenadas': coords}, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Gemini
# ─────────────────────────────────────────────────────────────────────────────

def llamar_gemini_bypass(prompt, api_key):
    if not api_key:
        raise ErrorIntegracionIA('No hay API key de Gemini configurada.')

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    data = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'response_mime_type': 'application/json'},
    }
    timeout_s = max(10, _leer_int_env('GEMINI_TIMEOUT_SECONDS', 30))
    max_reintentos = max(0, _leer_int_env('GEMINI_MAX_RETRIES', 2))
    http_reintentable = {408, 409, 425, 429, 500, 502, 503, 504}

    ultimo_error: Exception | None = None
    for intento in range(max_reintentos + 1):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=timeout_s)
            if response.status_code in http_reintentable and intento < max_reintentos:
                logger.warning(
                    'Gemini devolvió status=%s (reintento %s/%s).',
                    response.status_code, intento + 1, max_reintentos,
                )
                continue
            response.raise_for_status()
            resultado = response.json()
            texto_json = resultado['candidates'][0]['content']['parts'][0]['text']
            return json.loads(texto_json)
        except requests.Timeout as exc:
            ultimo_error = exc
            if intento < max_reintentos:
                logger.warning('Timeout Gemini (reintento %s/%s).', intento + 1, max_reintentos)
                continue
            raise ErrorIntegracionIA(
                f'Gemini agotó el tiempo de espera tras {max_reintentos + 1} intentos.'
            ) from exc
        except requests.HTTPError as exc:
            ultimo_error = exc
            status = exc.response.status_code if exc.response is not None else 'desconocido'
            if status in http_reintentable and intento < max_reintentos:
                logger.warning('Error HTTP Gemini status=%s (reintento %s/%s).', status, intento + 1, max_reintentos)
                continue
            raise ErrorIntegracionIA(f'Error HTTP al llamar a Gemini (status={status}).') from exc
        except requests.RequestException as exc:
            ultimo_error = exc
            if intento < max_reintentos:
                logger.warning('Error de red Gemini (reintento %s/%s): %s', intento + 1, max_reintentos, exc)
                continue
            raise ErrorIntegracionIA('Error de red al conectar con Gemini.') from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ErrorIntegracionIA('Respuesta no válida de Gemini.') from exc
        except Exception as exc:
            raise ErrorIntegracionIA('Error inesperado al invocar Gemini.') from exc

    raise ErrorIntegracionIA('No se pudo obtener respuesta válida de Gemini.') from ultimo_error


# ─────────────────────────────────────────────────────────────────────────────
# Normalización de modos y niveles
# ─────────────────────────────────────────────────────────────────────────────

def normalizar_mood(raw_moods):
    if isinstance(raw_moods, str):
        raw_moods = [raw_moods]
    normalizados = []
    for mood in raw_moods or []:
        key = str(mood).strip().lower()
        if key:
            normalizados.append(MOOD_MAP.get(key, key))
    return normalizados


def normalizar_nivel_exigencia(raw_value, default='media'):
    return EXIGENCIA_MAP.get(str(raw_value or '').strip().lower(), default)


def normalizar_moods(moods_sin_normalizar):
    if isinstance(moods_sin_normalizar, str):
        moods_sin_normalizar = [moods_sin_normalizar]
    moods_normalizados = []
    for mood in moods_sin_normalizar or []:
        clave_mood = str(mood).strip().lower()
        if clave_mood:
            moods_normalizados.append(MAPA_MOOD_RUTA.get(clave_mood, mood))
    return [m for m in moods_normalizados if m in dict(Ruta.Mood.choices)]


# ─────────────────────────────────────────────────────────────────────────────
# Validación de ciudad
# ─────────────────────────────────────────────────────────────────────────────

def validar_ciudad_existe(ciudad: str) -> bool:
    """Consulta Nominatim para verificar que la ciudad existe."""
    url = 'https://nominatim.openstreetmap.org/search'
    params = {'q': ciudad, 'format': 'json', 'limit': 1}
    headers = {'User-Agent': 'AURA-RouteApp/1.0'}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            return len(response.json()) > 0
        return True
    except requests.RequestException:
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Allowlist
# ─────────────────────────────────────────────────────────────────────────────

def _obtener_pois_allowlist(ciudad: str, moods: list[str]) -> list[dict]:
    """
    Devuelve hasta MAX_POIS_ALLOWLIST_EN_PROMPT POIs de la allowlist
    filtrados por ciudad y categorías OSM relevantes para los moods dados.
    Importación diferida del modelo POI para evitar dependencias circulares.
    """
    try:
        from allowList.models import POI  # importación diferida intencionada
    except ImportError:
        logger.warning('No se pudo importar el modelo POI de allowList; se omiten recomendaciones.')
        return []

    categorias_relevantes: set[str] = set()
    for mood in moods:
        categorias_relevantes.update(_MOOD_A_CATEGORIAS_OSM.get(str(mood).strip().lower(), []))

    try:
        qs = POI.objects.filter(ciudad__icontains=ciudad.strip())
        if categorias_relevantes:
            qs = qs.filter(categoria__in=categorias_relevantes)
        qs = qs.order_by('nombre')[:MAX_POIS_ALLOWLIST_EN_PROMPT]
        return [
            {
                'nombre': poi.nombre,
                'coords': [poi.lat, poi.lon],
                'categoria': poi.get_categoria_display(),
            }
            for poi in qs
        ]
    except Exception as exc:
        logger.warning('Error al consultar la allowlist de POIs: %s', exc)
        return []



def _construir_pois_fallback_allowlist(
    *,
    ciudad: str,
    moods: list[str],
    cantidad_objetivo: int,
    nombres_excluidos: set[str] | None = None,
    coords_excluidas: set[tuple[float, float]] | None = None,
) -> list[dict]:
    nombres_excluidos = nombres_excluidos or set()
    coords_excluidas = coords_excluidas or set()
    pois_allowlist = _obtener_pois_allowlist(ciudad=ciudad, moods=moods)
    candidatos = []
    for poi in pois_allowlist:
        coords = poi.get('coords')
        if not isinstance(coords, list) or len(coords) < 2:
            continue
        nombre = str(poi.get('nombre') or '').strip()
        if not nombre:
            continue
        nombre_key = _normalizar_nombre_para_dedupe(nombre)
        coord_key = _clave_coordenadas_para_dedupe(coords)
        if nombre_key in nombres_excluidos or coord_key in coords_excluidas:
            continue
        candidatos.append({
            'nombre': nombre,
            'coords': [float(coords[0]), float(coords[1])],
            'desc': f'POI curado en allowlist ({poi.get("categoria", "general")}).',
            'categoria': str(poi.get('categoria') or 'general'),
        })
        nombres_excluidos.add(nombre_key)
        coords_excluidas.add(coord_key)
        if len(candidatos) >= cantidad_objetivo:
            break
    return candidatos


def guardar_ruta_manual(guia, payload):
    if not isinstance(payload, dict):
        raise ErrorValidacionRuta('El cuerpo de la petición debe ser un JSON válido.')

    titulo = str(payload.get('titulo') or '').strip()
    descripcion = str(payload.get('descripcion') or '').strip()
    paradas_data = payload.get('paradas', [])

    if not titulo:
        raise ErrorValidacionRuta('El título de la ruta es obligatorio.')
    if not descripcion:
        raise ErrorValidacionRuta('La descripción de la ruta es obligatoria.')
    if not isinstance(paradas_data, list):
        raise ErrorValidacionRuta('El formato de paradas no es válido.')
    if len(paradas_data) < MIN_PARADAS_MANUAL:
        raise ErrorValidacionRuta('Debes indicar al menos 2 paradas para guardar la ruta.')

    try:
        duracion_horas = float(payload.get('duracion_horas'))
        num_personas = int(payload.get('num_personas'))
    except (TypeError, ValueError) as exc:
        raise ErrorValidacionRuta('Duración y número de personas deben tener un formato válido.') from exc

    if not math.isfinite(duracion_horas):
        raise ErrorValidacionRuta('La duración debe ser un número finito válido.')
    if duracion_horas < MIN_DURACION_HORAS_MANUAL or duracion_horas > MAX_DURACION_HORAS_MANUAL:
        raise ErrorValidacionRuta('La duración debe estar entre 0.5 y 24 horas.')
    if num_personas < MIN_PERSONAS_MANUAL or num_personas > MAX_PERSONAS_MANUAL:
        raise ErrorValidacionRuta('El número de personas debe estar entre 1 y 50.')

    exigencia_raw = str(payload.get('nivel_exigencia', Ruta.Exigencia.MEDIA)).strip().lower()
    nivel_exigencia = MAPA_EXIGENCIA_RUTA.get(exigencia_raw, payload.get('nivel_exigencia', Ruta.Exigencia.MEDIA))
    exigencias_validas = {value for value, _ in Ruta.Exigencia.choices}
    if nivel_exigencia not in exigencias_validas:
        raise ErrorValidacionRuta('El nivel de exigencia indicado no es válido.')

    moods = normalizar_moods(payload.get('mood', []))

    try:
        with transaction.atomic():
            ruta = Ruta.objects.create(
                titulo=titulo,
                descripcion=descripcion,
                duracion_horas=duracion_horas,
                num_personas=num_personas,
                nivel_exigencia=nivel_exigencia,
                mood=moods,
                es_generada_ia=False,
                guia=guia,
            )

            for idx, parada_data in enumerate(paradas_data, start=1):
                if not isinstance(parada_data, dict):
                    raise ErrorValidacionRuta('Cada parada debe ser un objeto válido.')

                nombre_parada = str(parada_data.get('nombre') or '').strip()
                if not nombre_parada:
                    raise ErrorValidacionRuta(f'El nombre de la parada {idx} es obligatorio.')

                lat_raw = parada_data.get('lat')
                lon_raw = parada_data.get('lon')
                if lat_raw is None or lon_raw is None:
                    raise ErrorValidacionRuta(
                        f'Debes indicar la ubicación de la parada {idx} desde el mapa.'
                    )

                try:
                    lat = float(lat_raw)
                    lon = float(lon_raw)
                except (TypeError, ValueError) as exc:
                    raise ErrorValidacionRuta(
                        f'La ubicación de la parada {idx} tiene coordenadas inválidas.'
                    ) from exc

                if not math.isfinite(lat) or not math.isfinite(lon):
                    raise ErrorValidacionRuta(
                        f'La ubicación de la parada {idx} contiene valores fuera de rango.'
                    )
                if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                    raise ErrorValidacionRuta(
                        f'La ubicación de la parada {idx} está fuera de rango válido.'
                    )

                Parada.objects.create(
                    ruta=ruta,
                    orden=idx,
                    nombre=nombre_parada,
                    coordenadas=Point(float(lon), float(lat), srid=4326),
                )
    except ErrorValidacionRuta:
        raise
    except (DatabaseError, IntegrityError, TypeError, ValueError) as exc:
        raise ErrorPersistenciaRuta('No se pudo guardar la ruta manual en la base de datos.') from exc

    return ruta


def _normalizar_candidato_parada(candidato, idx):
    if not isinstance(candidato, dict):
        return None
    nombre = str(candidato.get('nombre') or '').strip()
    if not nombre:
        return None
    coordenadas = _normalizar_coordenadas(
        candidato.get('coordenadas') or candidato.get('coords'),
        lat=candidato.get('lat'),
        lon=candidato.get('lon'),
    )
    if not coordenadas:
        return None
    descripcion = str(candidato.get('desc') or candidato.get('descripcion') or '').strip()
    return {
        'id_sugerencia': idx,
        'nombre': nombre,
        'coordenadas': coordenadas,
        'categoria': str(candidato.get('categoria') or 'general').strip()[:60],
        'nivel_confianza': 1.0,
        'justificacion': descripcion[:500],
        'descripcion': descripcion[:500],
    } 
# ─────────────────────────────────────────────────────────────────────────────
# Normalización de POIs
# ─────────────────────────────────────────────────────────────────────────────

def _normalizar_poi_generado_para_validacion(candidato, idx):
    if not isinstance(candidato, dict):
        return None
    nombre = str(candidato.get('nombre') or '').strip()
    if not nombre:
        return None
    coordenadas = _normalizar_coordenadas(
        candidato.get('coordenadas') or candidato.get('coords'),
        lat=candidato.get('lat'),
        lon=candidato.get('lon'),
    )
    if not coordenadas:
        return None
    descripcion = str(candidato.get('desc') or candidato.get('descripcion') or '').strip()
    return {
        'id_sugerencia': idx,
        'nombre': nombre,
        'coordenadas': coordenadas,
        'categoria': str(candidato.get('categoria') or 'general').strip()[:60],
        'nivel_confianza': 1.0,
        'justificacion': descripcion[:500],
        'descripcion': descripcion[:500],
    }


def _normalizar_lista_pois(pois) -> list:
    normalizados = []
    for idx, candidato in enumerate(pois or [], start=1):
        item = _normalizar_poi_generado_para_validacion(candidato, idx)
        if item:
            normalizados.append(item)
    return normalizados


def _normalizar_poi_para_optimizacion(poi_validado: dict) -> dict:
    return {
        'nombre': poi_validado['nombre'],
        'coords': poi_validado['coordenadas'],
        'desc': poi_validado.get('descripcion') or poi_validado.get('justificacion') or '',
        'fuente_validacion': poi_validado.get('fuente_validacion'),
        'tipo_geometria': poi_validado.get('tipo_geometria'),
        'error_m': poi_validado.get('error_m'),
        'corregida': poi_validado.get('corregida'),
    }



def _normalizar_candidato_parada(candidato, idx):
    if not isinstance(candidato, dict):
        return None
    nombre = str(candidato.get('nombre') or '').strip()
    if not nombre:
        return None
    coordenadas = _normalizar_coordenadas(
        candidato.get('coordenadas') or candidato.get('coords'),
        lat=candidato.get('lat'),
        lon=candidato.get('lon'),
    )
    if not coordenadas:
        return None
    confianza_raw = candidato.get('nivel_confianza', candidato.get('confianza', 0.0))
    try:
        nivel_confianza = max(0.0, min(1.0, float(confianza_raw)))
    except (TypeError, ValueError):
        nivel_confianza = 0.0
    return {
        'id_sugerencia': idx,
        'nombre': nombre,
        'coordenadas': coordenadas,
        'categoria': str(candidato.get('categoria') or 'general').strip()[:60],
        'nivel_confianza': round(nivel_confianza, 2),
        'justificacion': str(candidato.get('justificacion') or '').strip()[:500],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Contexto geográfico para regeneración de POIs
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_contexto_regeneracion_pois(datos: dict, pois_normalizados: list[dict]) -> dict:
    """
    Calcula contexto geográfico robusto para regeneración de POIs.
    Prioridad: coords iniciales → allowlist → sin restricción.
    """
    if pois_normalizados:
        return _calcular_contexto_geografico(pois_normalizados)
    pois_allowlist = _obtener_pois_allowlist(
        ciudad=str(datos.get('ciudad') or ''),
        moods=datos.get('mood') or [],
    )
    contexto_desde_allowlist = [
        {'coordenadas': [float(poi['coords'][0]), float(poi['coords'][1])]}
        for poi in pois_allowlist
        if isinstance(poi.get('coords'), list) and len(poi['coords']) >= 2
    ]
    if contexto_desde_allowlist:
        return _calcular_contexto_geografico(contexto_desde_allowlist)
    return {'centro': None, 'radio_km': None}


# ─────────────────────────────────────────────────────────────────────────────
# Prompts de regeneración y solicitudes a Gemini
# ─────────────────────────────────────────────────────────────────────────────

def _construir_prompt_regeneracion_pois(
    *,
    datos: dict,
    cantidad: int,
    contexto_geo: dict,
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> str:
    exclusiones = _formatear_exclusiones_para_prompt(nombres_excluidos, coords_excluidas)
    centro = contexto_geo.get('centro')
    radio_km = contexto_geo.get('radio_km')
    centro_prompt = (
        json.dumps(centro, ensure_ascii=False)
        if isinstance(centro, list)
        else '"No definido: usar ciudad solicitada"'
    )
    radio_prompt = (
        f'{round(float(radio_km), 2)} km'
        if isinstance(radio_km, (int, float))
        else 'No definido: priorizar ciudad solicitada'
    )
    return f"""
        Eres un guía turístico experto.

        Debes generar EXACTAMENTE {cantidad} POIs nuevos para una ruta en {datos.get('ciudad')}.

        ## Contexto estricto
        - Duración: {datos.get('duracion')} horas
        - Número de personas: {datos.get('personas')}
        - Nivel de exigencia: {datos.get('exigencia')}
        - Temática(s): {', '.join(datos.get('mood') or [])}
        - Centro geográfico de referencia: {centro_prompt}
        - Radio máximo permitido: {radio_prompt}
        - Exclusiones obligatorias (nombres/coordenadas): {exclusiones}

        ## Reglas obligatorias
        - No devuelvas duplicados ni dentro de la lista ni respecto a exclusiones.
        - No sugieras puntos fuera del área geográfica indicada.
        - Coordenadas reales y plausibles del lugar exacto.

        Responde ÚNICAMENTE JSON válido:
        [
            {{"nombre": "Nombre del sitio", "coords": [lat, lon], "desc": "Breve descripción del lugar"}}
        ]
    """


def _solicitar_pois_adicionales_para_ruta_ia(
    *,
    datos: dict,
    cantidad: int,
    contexto_geo: dict,
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> list[dict]:
    prompt = _construir_prompt_regeneracion_pois(
        datos=datos,
        cantidad=cantidad,
        contexto_geo=contexto_geo,
        nombres_excluidos=nombres_excluidos,
        coords_excluidas=coords_excluidas,
    )
    try:
        respuesta = llamar_gemini_bypass(prompt, os.getenv('GEMINI_API_KEY'))
    except ErrorIntegracionIA:
        respuesta = None

    if isinstance(respuesta, list):
        return respuesta

    fallback = _construir_pois_fallback_allowlist(
        ciudad=str(datos.get('ciudad') or ''),
        moods=datos.get('mood') or [],
        cantidad_objetivo=cantidad,
        nombres_excluidos=set(nombres_excluidos),
        coords_excluidas=set(coords_excluidas),
    )
    if fallback:
        logger.warning(
            'Se usa fallback de allowlist para regenerar %s paradas por indisponibilidad de Gemini.',
            len(fallback),
        )
        return fallback

    raise ErrorIntegracionIA('No se pudieron regenerar paradas válidas con IA ni con allowlist.')



# ─────────────────────────────────────────────────────────────────────────────
# Prompts de candidatos para rutas existentes
# ─────────────────────────────────────────────────────────────────────────────

def _construir_prompt_candidatos_paradas(
    *,
    cantidad: int,
    ciudad_contexto: str,
    ruta: Ruta,
    preferencias: dict,
    paradas_existentes: list[dict],
    contexto_geo: dict,
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> str:
    exclusiones = _formatear_exclusiones_para_prompt(nombres_excluidos, coords_excluidas)
    return f"""
        Eres un asistente experto en diseño de rutas turísticas.

        Debes proponer EXACTAMENTE {cantidad} nuevas paradas para complementar una ruta existente.

        ## Contexto de la ruta
        - Ciudad: {ciudad_contexto}
        - Temática(s): {', '.join(ruta.mood)}
        - Preferencias: {json.dumps(preferencias, ensure_ascii=False)}
        - Paradas existentes: {json.dumps(paradas_existentes, ensure_ascii=False)}
        - Centro geográfico aproximado de la ruta: {json.dumps(contexto_geo['centro'], ensure_ascii=False)}
        - Distancia máxima permitida desde el centro: {round(contexto_geo['radio_km'], 2)} km
        - Exclusiones obligatorias (NO repetir): {exclusiones}

        ## Criterios
        - Evita sugerir puntos duplicados respecto a las paradas existentes.
        - Evita también duplicados entre las propias sugerencias.
        - NO sugieras ningún nombre o coordenada de la lista de exclusiones.
        - Mantén coherencia temática con la ruta.
        - Propón coordenadas plausibles dentro de la ciudad indicada.
        - REGLA ESTRICTA: NO propongas paradas fuera del área geográfica de la ruta.

        Responde únicamente JSON válido (sin texto adicional) como lista de objetos con esta estructura:
        [
          {{
            "nombre": "Nombre de la parada",
            "coordenadas": [lat, lon],
            "categoria": "Categoría turística",
            "nivel_confianza": 0.0,
            "justificacion": "Motivo breve de por qué encaja en la ruta"
          }}
        ]
    """


def _solicitar_candidatos_paradas_ia(
    *,
    cantidad: int,
    ciudad_contexto: str,
    ruta: Ruta,
    preferencias: dict,
    paradas_existentes: list[dict],
    contexto_geo: dict,
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> list[dict]:
    prompt = _construir_prompt_candidatos_paradas(
        cantidad=cantidad,
        ciudad_contexto=ciudad_contexto,
        ruta=ruta,
        preferencias=preferencias,
        paradas_existentes=paradas_existentes,
        contexto_geo=contexto_geo,
        nombres_excluidos=nombres_excluidos,
        coords_excluidas=coords_excluidas,
    )
    try:
        respuesta = llamar_gemini_bypass(prompt, os.getenv('GEMINI_API_KEY'))
    except ErrorIntegracionIA:
        respuesta = None

    if isinstance(respuesta, list):
        return respuesta

    fallback_pois = _construir_pois_fallback_allowlist(
        ciudad=ciudad_contexto,
        moods=ruta.mood,
        cantidad_objetivo=cantidad,
        nombres_excluidos=set(nombres_excluidos),
        coords_excluidas=set(coords_excluidas),
    )
    if fallback_pois:
        logger.warning(
            'Se usan %s sugerencias fallback de allowlist por indisponibilidad de Gemini.',
            len(fallback_pois),
        )
        return [
            {
                'nombre': poi['nombre'],
                'coordenadas': poi['coords'],
                'categoria': poi.get('categoria', 'general'),
                'nivel_confianza': 0.95,
                'justificacion': poi.get('desc', 'Sugerencia de fallback allowlist.'),
            }
            for poi in fallback_pois
        ]

    raise ErrorIntegracionIA('No se pudieron generar nuevas paradas con IA ni con fallback de allowlist.')


# ─────────────────────────────────────────────────────────────────────────────
# Permisos y usuarios
# ─────────────────────────────────────────────────────────────────────────────

def validar_usuario_guia(usuario):
    if not usuario or not usuario.is_authenticated:
        raise ErrorPermisosRuta('Debes iniciar sesión para generar rutas.')
    if hasattr(usuario, 'turista'):
        raise ErrorPermisosRuta('Solo los guías pueden crear y guardar tours generados por IA.')


def obtener_guia_para_usuario(usuario):
    if hasattr(usuario, 'turista'):
        raise ErrorPermisosRuta('Solo los guías pueden crear rutas.')
    try:
        perfil_auth, _ = AuthUser.objects.get_or_create(user=usuario)
        guia, _ = Guia.objects.get_or_create(user=perfil_auth)
        return guia
    except (DatabaseError, IntegrityError) as exc:
        raise ErrorPersistenciaRuta(
            'No se pudo encontrar o crear un perfil de guía para este usuario.'
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Sesiones de generación
# ─────────────────────────────────────────────────────────────────────────────

def _firma_parada(checkpoint_parada):
    nombre = str(checkpoint_parada.get('nombre') or '').strip().lower()
    coords = checkpoint_parada.get('coordenadas') or [None, None]
    lat = lon = None
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        lat = round(float(coords[0]), 5)
        lon = round(float(coords[1]), 5)
    return f'{nombre}|{lat}|{lon}'


def _normalizar_restricciones(raw_restricciones, deseos=None):
    if raw_restricciones is None:
        raw_restricciones = deseos or []
    if isinstance(raw_restricciones, str):
        raw_restricciones = [raw_restricciones]
    if not isinstance(raw_restricciones, list):
        return []
    normalizadas = []
    vistas = set()
    for restriccion in raw_restricciones:
        texto = str(restriccion).strip()
        if not texto:
            continue
        clave = texto.lower()
        if clave in vistas:
            continue
        vistas.add(clave)
        normalizadas.append(texto[:200])
        if len(normalizadas) >= 20:
            break
    return normalizadas


def _normalizar_parada_checkpoint(parada):
    if not isinstance(parada, dict):
        return None
    nombre = str(parada.get('nombre') or '').strip()
    if not nombre:
        return None
    coordenadas = _normalizar_coordenadas(
        parada.get('coordenadas') or parada.get('coords'),
        lat=parada.get('lat'),
        lon=parada.get('lon'),
    )
    if not coordenadas:
        return None
    return {
        'nombre': nombre[:120],
        'coordenadas': coordenadas,
        'categoria': str(parada.get('categoria') or '').strip()[:80],
        'justificacion': str(parada.get('justificacion') or '').strip()[:500],
    }


def _obtener_store_sesiones_generacion(request):
    store = request.session.get(SESION_GENERACION_STORE_KEY)
    if not isinstance(store, dict):
        store = {}
        request.session[SESION_GENERACION_STORE_KEY] = store
    return store


def crear_estado_sesion_generacion(request, payload, checkpoint='payload_normalizado'):
    ahora_epoch = int(timezone.now().timestamp())
    estado = {
        'session_id': uuid.uuid4().hex,
        'checkpoint_actual': checkpoint,
        'creado_en': ahora_epoch,
        'actualizado_en': ahora_epoch,
        'expira_en': ahora_epoch + SESION_GENERACION_TTL_SECONDS,
        'contexto_generacion': {
            'ciudad': payload.get('ciudad'),
            'duracion': payload.get('duracion'),
            'personas': payload.get('personas'),
            'exigencia': payload.get('exigencia'),
            'mood': payload.get('mood') or [],
        },
        'restricciones_usuario': _normalizar_restricciones(
            payload.get('restricciones'),
            deseos=payload.get('deseos') or [],
        ),
        'paradas_propuestas': [],
        'paradas_rechazadas': [],
    }
    store = _obtener_store_sesiones_generacion(request)
    store[estado['session_id']] = estado
    request.session[SESION_GENERACION_STORE_KEY] = store
    request.session.modified = True
    return estado


def obtener_estado_sesion_generacion(request, session_id, refresh_ttl=True):
    store = _obtener_store_sesiones_generacion(request)
    estado = store.get(str(session_id))
    if not estado:
        raise ErrorSesionGeneracionNoEncontrada(
            'No existe la sesión de generación solicitada. Inicia una nueva generación de ruta.'
        )
    ahora_epoch = int(timezone.now().timestamp())
    if int(estado.get('expira_en') or 0) < ahora_epoch:
        del store[str(session_id)]
        request.session[SESION_GENERACION_STORE_KEY] = store
        request.session.modified = True
        raise ErrorSesionGeneracionExpirada(
            'La sesión de generación ha expirado. Vuelve a iniciar la generación de la ruta.'
        )
    if refresh_ttl:
        estado['actualizado_en'] = ahora_epoch
        estado['expira_en'] = ahora_epoch + SESION_GENERACION_TTL_SECONDS
        store[str(session_id)] = estado
        request.session[SESION_GENERACION_STORE_KEY] = store
        request.session.modified = True
    return estado


def avanzar_checkpoint_sesion_generacion(
    request,
    session_id,
    checkpoint,
    *,
    paradas_propuestas=None,
    parada_rechazada=None,
    motivo_rechazo='',
    restricciones=None,
    datos_extra=None,
):
    estado = obtener_estado_sesion_generacion(request, session_id=session_id, refresh_ttl=False)
    store = _obtener_store_sesiones_generacion(request)
    ahora_epoch = int(timezone.now().timestamp())

    propuestas_actuales = estado.get('paradas_propuestas') or []
    firmas_actuales = {_firma_parada(p) for p in propuestas_actuales if isinstance(p, dict)}
    propuestas_nuevas = []
    for parada in paradas_propuestas or []:
        parada_norm = _normalizar_parada_checkpoint(parada)
        if not parada_norm:
            continue
        firma = _firma_parada(parada_norm)
        if firma in firmas_actuales:
            continue
        firmas_actuales.add(firma)
        parada_norm['checkpoint'] = checkpoint
        parada_norm['registrada_en'] = ahora_epoch
        propuestas_nuevas.append(parada_norm)
    estado['paradas_propuestas'] = propuestas_actuales + propuestas_nuevas

    if parada_rechazada:
        parada_rechazada_norm = _normalizar_parada_checkpoint(parada_rechazada)
        if parada_rechazada_norm:
            parada_rechazada_norm['motivo_rechazo'] = str(motivo_rechazo or '').strip()[:300]
            parada_rechazada_norm['checkpoint'] = checkpoint
            parada_rechazada_norm['registrada_en'] = ahora_epoch
            rechazos_actuales = estado.get('paradas_rechazadas') or []
            firmas_rechazos = {_firma_parada(p) for p in rechazos_actuales if isinstance(p, dict)}
            if _firma_parada(parada_rechazada_norm) not in firmas_rechazos:
                rechazos_actuales.append(parada_rechazada_norm)
                estado['paradas_rechazadas'] = rechazos_actuales

    if restricciones is not None:
        restricciones_existentes = estado.get('restricciones_usuario') or []
        estado['restricciones_usuario'] = _normalizar_restricciones(
            restricciones_existentes + _normalizar_restricciones(restricciones)
        )

    if isinstance(datos_extra, dict) and datos_extra:
        contexto = estado.get('contexto_generacion') or {}
        contexto.update(datos_extra)
        estado['contexto_generacion'] = contexto

    estado['checkpoint_actual'] = checkpoint
    estado['actualizado_en'] = ahora_epoch
    estado['expira_en'] = ahora_epoch + SESION_GENERACION_TTL_SECONDS
    store[str(session_id)] = estado
    request.session[SESION_GENERACION_STORE_KEY] = store
    request.session.modified = True
    return estado


# ─────────────────────────────────────────────────────────────────────────────
# Normalización de payloads
# ─────────────────────────────────────────────────────────────────────────────

def normalizar_payload_ia(datos):
    if not isinstance(datos, dict):
        raise ErrorValidacionRuta('El cuerpo de la petición debe ser un JSON válido.')
    ciudad = str(datos.get('ciudad') or '').strip()
    if not ciudad:
        raise ErrorValidacionRuta('El nombre de la ciudad es obligatorio.')
    if not validar_ciudad_existe(ciudad):
        raise ErrorValidacionRuta('La ciudad ingresada no se encuentra en nuestros registros o no existe.')
    duracion = datos.get('duracion')
    personas = datos.get('personas')
    exigencia = str(datos.get('exigencia') or '').strip().lower()
    mood = datos.get('mood')
    if not all([ciudad, duracion, personas, exigencia, mood]):
        raise ErrorValidacionRuta('Faltan parámetros obligatorios en la petición.')
    exigencia_normalizada = MAPA_EXIGENCIA_RUTA.get(exigencia)
    if not exigencia_normalizada:
        raise ErrorValidacionRuta('El nivel de exigencia indicado no es válido.')
    moods_normalizados = normalizar_moods(mood)
    if not moods_normalizados:
        raise ErrorValidacionRuta('Debes indicar al menos una temática (mood) válida.')
    deseos_raw = datos.get('deseos') or []
    if not isinstance(deseos_raw, list):
        raise ErrorValidacionRuta('Los deseos personalizados deben ser una lista.')
    deseos = [str(d).strip()[:100] for d in deseos_raw if str(d).strip()][:5]
    restricciones = _normalizar_restricciones(datos.get('restricciones'), deseos=deseos)
    metadata = datos.get('metadata') or {}
    try:
        return {
            'ciudad': ciudad,
            'duracion': float(duracion),
            'personas': int(personas),
            'exigencia': exigencia_normalizada,
            'mood': moods_normalizados,
            'deseos': deseos,
            'restricciones': restricciones,
            'metadata': metadata,
        }
    except (TypeError, ValueError) as exc:
        raise ErrorValidacionRuta('Duración y personas deben tener un formato válido.') from exc


def mapear_payload_ia(payload):
    ciudad = str(payload.get('ciudad') or '').strip()
    duracion = payload.get('duracion')
    personas = payload.get('personas')
    if not ciudad or duracion in (None, '') or personas in (None, ''):
        raise ValueError('Faltan parámetros obligatorios en la petición.')
    mood = normalizar_mood(payload.get('mood') or [])
    if not mood:
        raise ValueError('Debes seleccionar al menos un mood para generar la ruta.')
    return {
        'ciudad': ciudad,
        'duracion': float(duracion),
        'personas': int(personas),
        'exigencia': normalizar_nivel_exigencia(payload.get('exigencia')),
        'mood': mood,
    }


def mapear_payload_manual(payload):
    paradas_normalizadas = []
    for idx, parada in enumerate(payload.get('paradas', []), start=1):
        coords = _normalizar_coordenadas(
            parada.get('coordenadas') or parada.get('coords'),
            lat=parada.get('lat'),
            lon=parada.get('lon'),
        )
        if not coords:
            continue
        paradas_normalizadas.append({
            'orden': int(parada.get('orden') or idx),
            'nombre': parada.get('nombre') or f'Parada {idx}',
            'descripcion': parada.get('descripcion') or parada.get('desc') or '',
            'coordenadas': coords,
        })
    if not paradas_normalizadas:
        raise ValueError('La ruta manual debe incluir al menos una parada con coordenadas válidas.')
    return {
        'titulo': str(payload.get('titulo') or '').strip() or 'Ruta manual',
        'descripcion': str(payload.get('descripcion') or '').strip(),
        'duracion_horas': float(payload.get('duracion_horas') or 2.0),
        'num_personas': int(payload.get('num_personas') or 10),
        'nivel_exigencia': normalizar_nivel_exigencia(payload.get('nivel_exigencia')),
        'mood': normalizar_mood(payload.get('mood') or []),
        'paradas': paradas_normalizadas,
    }


def serializar_ruta_creada(ruta, paradas):
    return {
        'id': ruta.id,
        'titulo': ruta.titulo,
        'descripcion': ruta.descripcion,
        'duracion_horas': float(ruta.duracion_horas),
        'num_personas': int(ruta.num_personas),
        'nivel_exigencia': ruta.nivel_exigencia,
        'mood': ruta.mood,
        'es_generada_ia': bool(ruta.es_generada_ia),
        'paradas': paradas,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Persistencia de rutas
# ─────────────────────────────────────────────────────────────────────────────

def generar_ruta_con_ia(payload):
    try:
        ruta_generada = consultar_langgraph(payload)
    except ErrorIntegracionIA:
        raise
    except Exception as exc:
        raise ErrorPersistenciaRuta('No se pudo generar la ruta con IA en este momento.') from exc
    if not isinstance(ruta_generada, dict):
        raise ErrorPersistenciaRuta('La IA devolvió un formato de ruta no válido.')
    return ruta_generada


def guardar_ruta_ia(guia, payload, ruta_generada):
    raw_paradas = ruta_generada.get('paradas')
    if not isinstance(raw_paradas, list) or not raw_paradas:
        raise ErrorValidacionRuta('La ruta generada no contiene paradas válidas para guardar.')
    objetivo_paradas = len(raw_paradas)
    exigencia_normalizada = MAPA_EXIGENCIA_RUTA.get(
        str(ruta_generada.get('nivel_exigencia') or payload.get('exigencia') or '').lower(),
        Ruta.Exigencia.MEDIA,
    )
    moods_normalizados = normalizar_moods(ruta_generada.get('mood') or payload.get('mood') or [])
    ciudad = str(payload.get('ciudad') or 'AURA').strip()
    fecha_creacion = timezone.localtime().strftime('%Y-%m-%d')
    try:
        with transaction.atomic():
            ruta = Ruta.objects.create(
                titulo=f'{ciudad} {fecha_creacion}',
                descripcion=ruta_generada.get('descripcion', ''),
                duracion_horas=float(ruta_generada.get('duracion_horas') or payload.get('duracion') or 1),
                num_personas=int(ruta_generada.get('num_personas') or payload.get('personas') or 1),
                nivel_exigencia=exigencia_normalizada,
                mood=moods_normalizados,
                es_generada_ia=True,
                guia=guia,
            )
            paradas_normalizadas = []
            for idx, parada in enumerate(raw_paradas, start=1):
                coordenadas = parada.get('coordenadas') or parada.get('coords')
                if isinstance(coordenadas, dict):
                    lat = coordenadas.get('lat')
                    lon = coordenadas.get('lon') if coordenadas.get('lon') is not None else coordenadas.get('lng')
                elif isinstance(coordenadas, (list, tuple)) and len(coordenadas) >= 2:
                    lat, lon = coordenadas[0], coordenadas[1]
                else:
                    raise ErrorValidacionRuta('La ruta generada contiene paradas sin coordenadas válidas.')
                if lat is None or lon is None:
                    raise ErrorValidacionRuta('La ruta generada contiene paradas sin coordenadas válidas.')
                Parada.objects.create(
                    ruta=ruta,
                    orden=parada.get('orden') or idx,
                    nombre=parada.get('nombre') or f'Parada {idx}',
                    coordenadas=Point(float(lon), float(lat), srid=4326),
                )
                parada_payload = {
                    'orden': parada.get('orden') or idx,
                    'nombre': parada.get('nombre') or f'Parada {idx}',
                    'coordenadas': [float(lat), float(lon)],
                }
                for meta_key in ('fuente_validacion', 'tipo_geometria', 'error_m', 'corregida'):
                    if parada.get(meta_key) is not None:
                        parada_payload[meta_key] = parada.get(meta_key)
                paradas_normalizadas.append(parada_payload)
            if not paradas_normalizadas:
                raise ErrorValidacionRuta('No se han podido guardar coordenadas válidas para las paradas.')
            if len(paradas_normalizadas) != objetivo_paradas:
                raise ErrorValidacionRuta(
                    'No se pudo preservar el tamaño objetivo de la ruta generada al guardar las paradas.'
                )
    except ErrorValidacionRuta:
        raise
    except (DatabaseError, IntegrityError, TypeError, ValueError) as exc:
        raise ErrorPersistenciaRuta('No se pudo guardar la ruta generada en la base de datos.') from exc
    ruta_generada['id'] = ruta.id
    ruta_generada['nivel_exigencia'] = exigencia_normalizada
    ruta_generada['mood'] = moods_normalizados
    ruta_generada['es_generada_ia'] = True
    ruta_generada['paradas'] = paradas_normalizadas
    return ruta


def guardar_historial_ruta_ia(payload, ruta_generada):
    try:
        Historial_ia.objects.create(prompt=json.dumps(payload), respuesta=ruta_generada)
    except DatabaseError:
        logger.exception('No se pudo guardar el historial de IA')
        return (
            'No se pudo guardar el historial de la ruta generada. '
            'Revisa y ejecuta las migraciones pendientes.'
        )
    return None


def obtener_contexto_checkpoint_por_ruta(ruta_id):
    contexto_vacio = {'restricciones_usuario': [], 'paradas_rechazadas': []}
    if not ruta_id:
        return contexto_vacio
    try:
        historiales = Historial_ia.objects.order_by('-momento')[:200]
    except DatabaseError:
        return contexto_vacio
    for historial in historiales:
        respuesta = historial.respuesta if isinstance(historial.respuesta, dict) else {}
        if int(respuesta.get('id') or 0) != int(ruta_id):
            continue
        checkpoint_contexto = respuesta.get('checkpoint_contexto')
        if not isinstance(checkpoint_contexto, dict):
            return contexto_vacio
        return {
            'restricciones_usuario': checkpoint_contexto.get('restricciones_usuario') or [],
            'paradas_rechazadas': checkpoint_contexto.get('paradas_rechazadas') or [],
        }
    return contexto_vacio


def guardar_ruta_manual(guia, payload):
    titulo = str(payload.get('titulo') or '').strip()
    descripcion = payload.get('descripcion') or ''
    paradas_data = payload.get('paradas', [])
    if not titulo:
        raise ErrorValidacionRuta({'titulo': 'El título de la ruta es obligatorio.'})
    if len(titulo) > 255:
        raise ErrorValidacionRuta({'titulo': 'El título no puede superar los 255 caracteres.'})
    if not isinstance(paradas_data, list):
        raise ErrorValidacionRuta({'paradas': 'El formato de paradas no es válido.'})

    for idx, parada_data in enumerate(paradas_data, start=1):
        nombre = parada_data.get('nombre', '')
        if len(str(nombre)) > 255:
            raise ErrorValidacionRuta({f'parada_{idx}': 'El nombre no puede superar los 255 caracteres.'})

    try:
        duracion_horas = float(payload.get('duracion_horas', 2.0))
    except (TypeError, ValueError):
        raise ErrorValidacionRuta({'duracion_horas': 'Duración debe tener un formato válido.'})

    try:
        num_personas = int(payload.get('num_personas', 10))
    except (TypeError, ValueError):
        raise ErrorValidacionRuta({'num_personas': 'Número de personas debe tener un formato válido.'})

    if duracion_horas <= 0.1 or duracion_horas > 24:
        raise ErrorValidacionRuta({'duracion_horas': 'El valor debe ser superior a 0,1'})
    if num_personas < 1 or num_personas > 50:
        raise ErrorValidacionRuta({'num_personas': 'El valor debe ser superior o igual a 1'})

    exigencia_raw = str(payload.get('nivel_exigencia', Ruta.Exigencia.MEDIA)).strip().lower()
    nivel_exigencia = MAPA_EXIGENCIA_RUTA.get(exigencia_raw, payload.get('nivel_exigencia', Ruta.Exigencia.MEDIA))
    moods = normalizar_moods(payload.get('mood', []))
    try:
        with transaction.atomic():
            ruta = Ruta.objects.create(
                titulo=titulo,
                descripcion=descripcion,
                duracion_horas=duracion_horas,
                num_personas=num_personas,
                nivel_exigencia=nivel_exigencia,
                mood=moods,
                es_generada_ia=False,
                guia=guia,
            )
            for idx, parada_data in enumerate(paradas_data, start=1):
                lat = parada_data.get('lat', 37.38)
                lon = parada_data.get('lon', -5.99)
                Parada.objects.create(
                    ruta=ruta,
                    orden=idx,
                    nombre=parada_data.get('nombre', f'Parada {idx}'),
                    coordenadas=Point(float(lon), float(lat), srid=4326),
                )
    except (DatabaseError, IntegrityError, TypeError, ValueError) as exc:
        raise ErrorPersistenciaRuta('No se pudo guardar la ruta manual en la base de datos.') from exc
    return ruta


# ─────────────────────────────────────────────────────────────────────────────
# Generación de candidatos para rutas existentes
# ─────────────────────────────────────────────────────────────────────────────

def generar_candidatos_paradas_ia(*, ruta: Ruta, cantidad: int = 3):
    if cantidad < 1 or cantidad > 10:
        raise ErrorValidacionRuta('La cantidad de sugerencias debe estar entre 1 y 10.')
    paradas_existentes = [
        {
            'orden': parada.orden,
            'nombre': parada.nombre,
            'coordenadas': [parada.coordenadas.y, parada.coordenadas.x],
        }
        for parada in ruta.paradas.order_by('orden')
    ]
    if not paradas_existentes:
        raise ErrorValidacionRuta('La ruta no tiene paradas actuales para aportar contexto a la IA.')
    contexto_geo = _calcular_contexto_geografico(paradas_existentes)
    ciudad_contexto = str(ruta.titulo or '').split(' ')[0] or 'Sin ciudad'
    preferencias = {
        'duracion_horas': float(ruta.duracion_horas),
        'num_personas': int(ruta.num_personas),
        'nivel_exigencia': ruta.nivel_exigencia,
        'mood': ruta.mood,
        'descripcion': ruta.descripcion or '',
    }
    mapbox_client = MapboxGeocodingClient()
    osm_client = OSMGeocodingClient()
    respuesta_ia = _solicitar_candidatos_paradas_ia(
        cantidad=cantidad,
        ciudad_contexto=ciudad_contexto,
        ruta=ruta,
        preferencias=preferencias,
        paradas_existentes=paradas_existentes,
        contexto_geo=contexto_geo,
        nombres_excluidos=set(),
        coords_excluidas=set(),
    )

    def _proveedor_candidatos_adicionales(cantidad_solicitada, nombres_excluidos, coords_excluidas):
        return _solicitar_candidatos_paradas_ia(
            cantidad=cantidad_solicitada,
            ciudad_contexto=ciudad_contexto,
            ruta=ruta,
            preferencias=preferencias,
            paradas_existentes=paradas_existentes,
            contexto_geo=contexto_geo,
            nombres_excluidos=nombres_excluidos,
            coords_excluidas=coords_excluidas,
        )

    try:
        candidatos = completar_lista_paradas_validadas(
            cantidad_objetivo=cantidad,
            candidatos_iniciales=respuesta_ia,
            normalizador_candidato=_normalizar_candidato_parada,
            proveedor_candidatos=_proveedor_candidatos_adicionales,
            paradas_existentes=paradas_existentes,
            ciudad=ciudad_contexto,
            contexto_geo=contexto_geo,
            mapbox_client=mapbox_client,
            osm_client=osm_client,
        )
    except NoConvergenciaCoordenadasError as exc:
        raise ErrorIntegracionIA(
            'No fue posible completar la cantidad solicitada de paradas válidas y no duplicadas para esta ruta.'
        ) from exc
    return {
        'ruta_id': ruta.id,
        'ciudad': ciudad_contexto,
        'tematicas': ruta.mood,
        'paradas_existentes': paradas_existentes,
        'candidatos': candidatos,
    }


def generar_paradas_adicionales_sesion(*, estado_sesion: dict, cantidad: int = 3, sugerencias_texto: str = ''):
    if cantidad < 1 or cantidad > 10:
        raise ErrorValidacionRuta('La cantidad de sugerencias debe estar entre 1 y 10.')
    contexto = estado_sesion.get('contexto_generacion') or {}
    ciudad = str(contexto.get('ciudad') or 'Sin ciudad').strip() or 'Sin ciudad'
    mood = contexto.get('mood') or []
    restricciones = estado_sesion.get('restricciones_usuario') or []
    paradas_existentes = []
    for idx, parada in enumerate(estado_sesion.get('paradas_propuestas') or [], start=1):
        coordenadas = _normalizar_coordenadas(
            parada.get('coordenadas') or parada.get('coords'),
            lat=parada.get('lat'),
            lon=parada.get('lon'),
        )
        if not coordenadas:
            continue
        nombre = str(parada.get('nombre') or '').strip()
        if not nombre:
            continue
        paradas_existentes.append({
            'orden': parada.get('orden') or idx,
            'nombre': nombre,
            'coordenadas': coordenadas,
        })
    if not paradas_existentes:
        raise ErrorValidacionRuta('No hay contexto de paradas propuestas para pedir alternativas adicionales.')
    contexto_geo = _calcular_contexto_geografico(paradas_existentes)
    sugerencias_texto = str(sugerencias_texto or '').strip()
    bloque_sugerencias = f'\nSugerencias adicionales del guía: {sugerencias_texto[:300]}' if sugerencias_texto else ''
    bloque_restricciones = (
        '\nRestricciones activas del guía: '
        + '; '.join(str(r).strip() for r in restricciones if str(r).strip())[:600]
    ) if restricciones else ''
    prompt = f"""
        Eres un asistente experto en diseño de rutas turísticas.

        Debes proponer {cantidad} NUEVAS paradas adicionales para complementar esta selección.

        ## Contexto
        - Ciudad: {ciudad}
        - Temática(s): {', '.join(mood) if mood else 'general'}
        - Paradas ya propuestas: {json.dumps(paradas_existentes, ensure_ascii=False)}
        - Centro geográfico aproximado: {json.dumps(contexto_geo['centro'], ensure_ascii=False)}
        - Distancia máxima permitida desde el centro: {round(contexto_geo['radio_km'], 2)} km
        {bloque_restricciones}
        {bloque_sugerencias}

        ## Criterios obligatorios
        - NO repitas paradas existentes.
        - NO repitas paradas dentro de la respuesta.
        - Mantén coherencia temática y con restricciones.
        - Devuelve coordenadas plausibles y dentro del área indicada.

        Responde únicamente JSON válido (sin texto extra) como lista de objetos:
        [
          {{
            "nombre": "Nombre de la parada",
            "coordenadas": [lat, lon],
            "categoria": "Categoría turística",
            "nivel_confianza": 0.0,
            "justificacion": "Motivo breve"
          }}
        ]
    """
    try:
        respuesta_ia = llamar_gemini_bypass(prompt, os.getenv('GEMINI_API_KEY'))
    except Exception as exc:
        raise ErrorIntegracionIA('No se pudieron generar paradas adicionales con IA en este momento.') from exc
    if not isinstance(respuesta_ia, list):
        raise ErrorIntegracionIA('La IA devolvió un formato inválido para las paradas adicionales.')
    nombres_vistos = {
        _normalizar_nombre_para_dedupe(p.get('nombre'))
        for p in paradas_existentes
        if _normalizar_nombre_para_dedupe(p.get('nombre'))
    }
    coords_vistas = {
        _clave_coordenadas_para_dedupe(p.get('coordenadas'))
        for p in paradas_existentes
        if isinstance(p.get('coordenadas'), list) and len(p.get('coordenadas')) >= 2
    }
    candidatos = []
    for idx, candidato in enumerate(respuesta_ia, start=1):
        normalizado = _normalizar_candidato_parada(candidato, idx)
        if not normalizado:
            continue
        if not _esta_en_contexto_geografico(normalizado['coordenadas'], contexto_geo):
            continue
        nombre_key = _normalizar_nombre_para_dedupe(normalizado.get('nombre'))
        coords_key = _clave_coordenadas_para_dedupe(normalizado.get('coordenadas'))
        if nombre_key in nombres_vistos or coords_key in coords_vistas:
            continue
        nombres_vistos.add(nombre_key)
        coords_vistas.add(coords_key)
        candidatos.append(normalizado)
    if not candidatos:
        raise ErrorIntegracionIA('La IA no devolvió paradas adicionales válidas y no duplicadas.')
    return candidatos


# ─────────────────────────────────────────────────────────────────────────────
# Selección de mejor alternativa
# ─────────────────────────────────────────────────────────────────────────────

def _seleccionar_mejor_alternativa(alternativas):
    if not alternativas:
        raise ErrorIntegracionIA('No se pudieron generar alternativas de ruta válidas.')
    distancias = [a['metricas']['distancia_total_km'] for a in alternativas]
    min_d, max_d = min(distancias), max(distancias)
    for alternativa in alternativas:
        dist = alternativa['metricas']['distancia_total_km']
        distancia_score = 1.0 if max_d == min_d else 1.0 - ((dist - min_d) / (max_d - min_d))
        diversidad = alternativa['metricas']['diversidad']
        coherencia = alternativa['metricas']['coherencia_tematica']
        alternativa['score_total'] = round(0.45 * distancia_score + 0.30 * diversidad + 0.25 * coherencia, 4)
    alternativas.sort(key=lambda a: a['score_total'], reverse=True)
    return alternativas[0], alternativas


# ─────────────────────────────────────────────────────────────────────────────
# Grafo y orquestación
# ─────────────────────────────────────────────────────────────────────────────

def _ejecutar_grafo_para_alternativa(payload: dict, variacion: str) -> dict:
    """
    Invoca el pipeline completo de 4 nodos (generacion → validacion →
    scoring → optimizacion) para una variación concreta del prompt.

    Devuelve un dict compatible con _seleccionar_mejor_alternativa:
        {
            'ruta':                          dict,
            'metricas':                      {distancia_total_km, diversidad, coherencia_tematica},
            'paradas_rechazadas_validacion': list[dict],
        }
    """
    payload_variacion = {**payload, '_variacion': variacion}
    grafo = construir_grafo()
    state_resultado = grafo.invoke({'usuario_input': payload_variacion})

    ruta = state_resultado.get('ruta_final') or {}
    metricas = state_resultado.get('metricas_scoring') or {
        'distancia_total_km': 0.0,
        'diversidad': 0.0,
        'coherencia_tematica': 0.5,
    }
    razones_descarte = state_resultado.get('razones_descarte') or []

    return {
        'ruta': ruta,
        'metricas': metricas,
        'paradas_rechazadas_validacion': razones_descarte,
    }


def consultar_langgraph(prompt_params: dict) -> dict:
    try:
        num_alternativas = int(prompt_params.get('num_alternativas', 3))
    except (TypeError, ValueError):
        num_alternativas = 3

    num_alternativas = max(1, min(MAX_ALTERNATIVAS_RUTA, num_alternativas))

    alternativas = []
    for idx in range(num_alternativas):
        variacion = _VARIACIONES_ALTERNATIVA[idx % len(_VARIACIONES_ALTERNATIVA)]
        try:
            alternativa = _ejecutar_grafo_para_alternativa(prompt_params, variacion)
        except ErrorIntegracionIA:
            continue
        alternativas.append(alternativa)

    mejor, evaluadas = _seleccionar_mejor_alternativa(alternativas)
    ruta_final = mejor['ruta']
    ruta_final['paradas_rechazadas_validacion'] = mejor.get('paradas_rechazadas_validacion') or []
    ruta_final['alternativas_evaluadas'] = [
        {'score_total': a.get('score_total'), 'metricas': a.get('metricas')}
        for a in evaluadas
    ]
    ruta_final['metricas_seleccion'] = mejor.get('metricas')
    return ruta_final