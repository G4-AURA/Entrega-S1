import logging
import math
import os
import re
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MAPBOX_GEOCODING_URL = 'https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json'
NOMINATIM_SEARCH_URL = 'https://nominatim.openstreetmap.org/search'
OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
DEFAULT_TIMEOUT_S = 8
USER_AGENT = 'AURA-RouteApp/1.0 (geo-validation)'


def _distancia_haversine_km(coord_a: list[float], coord_b: list[float]) -> float:
    lat1, lon1 = coord_a
    lat2, lon2 = coord_b
    radio_tierra_km = 6371.0

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radio_tierra_km * c


def _normalizar_texto(valor: str) -> str:
    return ' '.join(str(valor or '').strip().lower().split())


def _centroide_simple(coords: list[list[float]]) -> list[float] | None:
    if not coords:
        return None
    lat = sum(c[0] for c in coords) / len(coords)
    lon = sum(c[1] for c in coords) / len(coords)
    return [lat, lon]


def _tipo_mapbox_a_tipo_geometria(place_type: str) -> str:
    place_type = str(place_type or '').strip().lower()
    if place_type in {'address', 'poi', 'neighborhood'}:
        return 'point'
    if place_type in {'place', 'locality', 'district', 'region'}:
        return 'area'
    return 'unknown'


def _tipo_geojson_a_tipo_geometria(*, geojson_type: str, item_class: str, item_type: str) -> str:
    tipo_geojson = str(geojson_type or '').strip().lower()
    item_class = str(item_class or '').strip().lower()
    item_type = str(item_type or '').strip().lower()

    if tipo_geojson in {'linestring', 'multilinestring'}:
        return 'linear'
    if tipo_geojson in {'polygon', 'multipolygon'}:
        if item_class == 'building' or item_type in {
            'museum', 'cathedral', 'church', 'hotel', 'station', 'university', 'theatre'
        }:
            return 'building'
        return 'area'
    if tipo_geojson == 'point':
        if item_class == 'building':
            return 'building'
        return 'point'
    return 'unknown'


def _extraer_linea_desde_geojson(geojson: dict[str, Any]) -> list[list[float]] | None:
    tipo = str(geojson.get('type') or '').lower()
    coords = geojson.get('coordinates')
    if not isinstance(coords, list):
        return None

    if tipo == 'linestring':
        linea = [[float(pt[1]), float(pt[0])] for pt in coords if isinstance(pt, (list, tuple)) and len(pt) >= 2]
        return linea or None

    if tipo == 'multilinestring':
        mejor = None
        for linea in coords:
            actual = [[float(pt[1]), float(pt[0])] for pt in linea if isinstance(pt, (list, tuple)) and len(pt) >= 2]
            if actual and (mejor is None or len(actual) > len(mejor)):
                mejor = actual
        return mejor

    return None


def _extraer_poligono_desde_geojson(geojson: dict[str, Any]) -> list[list[float]] | None:
    tipo = str(geojson.get('type') or '').lower()
    coords = geojson.get('coordinates')
    if not isinstance(coords, list):
        return None

    if tipo == 'polygon' and coords:
        anillo = coords[0]
        poligono = [[float(pt[1]), float(pt[0])] for pt in anillo if isinstance(pt, (list, tuple)) and len(pt) >= 2]
        return poligono or None

    if tipo == 'multipolygon':
        mejor = None
        for pol in coords:
            if not pol:
                continue
            anillo = pol[0]
            actual = [[float(pt[1]), float(pt[0])] for pt in anillo if isinstance(pt, (list, tuple)) and len(pt) >= 2]
            if actual and (mejor is None or len(actual) > len(mejor)):
                mejor = actual
        return mejor

    return None


class MapboxGeocodingClient:
    """Cliente de infraestructura para geocodificación con Mapbox."""

    def __init__(self, *, access_token: str | None = None, timeout_s: int = DEFAULT_TIMEOUT_S):
        self.access_token = access_token or getattr(settings, 'MAPBOX_ACCESS_TOKEN', None) or os.getenv('MAPBOX_ACCESS_TOKEN')
        self.timeout_s = timeout_s

    def buscar_lugares(
        self,
        *,
        nombre: str,
        ciudad: str,
        centro: list[float] | None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not self.access_token:
            return []

        query = f"{nombre}, {ciudad}".strip(', ')
        url = MAPBOX_GEOCODING_URL.format(query=requests.utils.quote(query))
        params: dict[str, Any] = {
            'access_token': self.access_token,
            'autocomplete': 'false',
            'limit': max(1, min(int(limit), 10)),
            'language': 'es',
        }
        if centro and len(centro) >= 2:
            params['proximity'] = f'{centro[1]},{centro[0]}'

        try:
            respuesta = requests.get(url, params=params, timeout=self.timeout_s)
            respuesta.raise_for_status()
            data = respuesta.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Mapbox geocoding no disponible: %s', exc)
            return []

        ciudad_normalizada = _normalizar_texto(ciudad)
        resultados: list[dict[str, Any]] = []
        for feature in data.get('features', []) or []:
            center = feature.get('center')
            if not isinstance(center, list) or len(center) < 2:
                continue

            lat, lon = float(center[1]), float(center[0])
            place_type = ''
            place_types = feature.get('place_type') or []
            if isinstance(place_types, list) and place_types:
                place_type = str(place_types[0])

            place_name = str(feature.get('place_name') or feature.get('text') or '').strip()
            score = float(feature.get('relevance') or 0.0)

            if ciudad_normalizada and ciudad_normalizada in _normalizar_texto(place_name):
                score += 1.5
            if centro and len(centro) >= 2:
                dist_km = _distancia_haversine_km([lat, lon], centro)
                if dist_km <= 2:
                    score += 2.0
                elif dist_km <= 8:
                    score += 1.0

            resultados.append(
                {
                    'nombre': place_name,
                    'coordenadas': [lat, lon],
                    'tipo_geometria': _tipo_mapbox_a_tipo_geometria(place_type),
                    'linea': None,
                    'poligono': None,
                    'fuente_validacion': 'mapbox',
                    'score': score,
                }
            )

        resultados.sort(key=lambda item: item.get('score', 0.0), reverse=True)
        return resultados


class OSMGeocodingClient:
    """Cliente de infraestructura para Nominatim/Overpass (OSM)."""

    def __init__(self, *, timeout_s: int = DEFAULT_TIMEOUT_S):
        self.timeout_s = timeout_s

    def buscar_lugares(
        self,
        *,
        nombre: str,
        ciudad: str,
        centro: list[float] | None,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        query = f"{nombre}, {ciudad}".strip(', ')
        params = {
            'q': query,
            'format': 'jsonv2',
            'limit': max(1, min(int(limit), 15)),
            'addressdetails': 1,
            'polygon_geojson': 1,
        }
        headers = {'User-Agent': USER_AGENT}

        try:
            respuesta = requests.get(NOMINATIM_SEARCH_URL, params=params, headers=headers, timeout=self.timeout_s)
            respuesta.raise_for_status()
            elementos = respuesta.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Nominatim no disponible: %s', exc)
            return []

        ciudad_normalizada = _normalizar_texto(ciudad)
        resultados: list[dict[str, Any]] = []

        for item in elementos or []:
            try:
                lat = float(item.get('lat'))
                lon = float(item.get('lon'))
            except (TypeError, ValueError):
                continue

            geojson = item.get('geojson') if isinstance(item.get('geojson'), dict) else {}
            tipo_geojson = str(geojson.get('type') or 'Point')
            tipo_geometria = _tipo_geojson_a_tipo_geometria(
                geojson_type=tipo_geojson,
                item_class=str(item.get('class') or ''),
                item_type=str(item.get('type') or ''),
            )

            linea = _extraer_linea_desde_geojson(geojson)
            poligono = _extraer_poligono_desde_geojson(geojson)
            nombre_mostrado = str(item.get('display_name') or nombre).strip()

            score = 0.0
            importance = item.get('importance')
            if importance is not None:
                try:
                    score += float(importance)
                except (TypeError, ValueError):
                    pass
            if ciudad_normalizada and ciudad_normalizada in _normalizar_texto(nombre_mostrado):
                score += 1.5
            if centro and len(centro) >= 2:
                dist_km = _distancia_haversine_km([lat, lon], centro)
                if dist_km <= 2:
                    score += 2.0
                elif dist_km <= 8:
                    score += 1.0

            resultados.append(
                {
                    'nombre': nombre_mostrado,
                    'coordenadas': [lat, lon],
                    'tipo_geometria': tipo_geometria,
                    'linea': linea,
                    'poligono': poligono,
                    'fuente_validacion': 'osm_nominatim',
                    'score': score,
                }
            )

        resultados.sort(key=lambda item: item.get('score', 0.0), reverse=True)
        return resultados

    def buscar_geometria_lineal_cercana(
        self,
        *,
        nombre: str,
        centro: list[float],
        radio_m: int = 250,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if not centro or len(centro) < 2:
            return []

        lat, lon = float(centro[0]), float(centro[1])
        nombre_seguro = re.sub(r'"', '', str(nombre or '').strip())
        if not nombre_seguro:
            return []

        query = f"""
        [out:json][timeout:20];
        (
          way(around:{int(radio_m)},{lat},{lon})["name"="{nombre_seguro}"];
          relation(around:{int(radio_m)},{lat},{lon})["name"="{nombre_seguro}"];
          node(around:{int(radio_m)},{lat},{lon})["name"="{nombre_seguro}"];
        );
        out center geom {max(1, min(int(limit), 25))};
        """

        try:
            respuesta = requests.post(
                OVERPASS_URL,
                data={'data': query},
                timeout=self.timeout_s + 6,
                headers={'User-Agent': USER_AGENT},
            )
            respuesta.raise_for_status()
            data = respuesta.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Overpass no disponible: %s', exc)
            return []

        resultados: list[dict[str, Any]] = []
        for elem in data.get('elements', []) or []:
            tags = elem.get('tags', {}) if isinstance(elem.get('tags'), dict) else {}
            nombre_elem = str(tags.get('name') or nombre_seguro).strip()

            punto = None
            if elem.get('type') == 'node' and elem.get('lat') is not None and elem.get('lon') is not None:
                punto = [float(elem['lat']), float(elem['lon'])]
            elif isinstance(elem.get('center'), dict) and elem['center'].get('lat') is not None and elem['center'].get('lon') is not None:
                punto = [float(elem['center']['lat']), float(elem['center']['lon'])]

            geometria = elem.get('geometry') if isinstance(elem.get('geometry'), list) else []
            coords = [
                [float(p.get('lat')), float(p.get('lon'))]
                for p in geometria
                if isinstance(p, dict) and p.get('lat') is not None and p.get('lon') is not None
            ]

            is_polygon = len(coords) >= 4 and coords[0] == coords[-1]
            if tags.get('bridge') == 'yes' or tags.get('man_made') == 'bridge':
                tipo_geometria = 'linear'
            elif is_polygon and tags.get('building'):
                tipo_geometria = 'building'
            elif is_polygon:
                tipo_geometria = 'area'
            elif len(coords) >= 2:
                tipo_geometria = 'linear'
            else:
                tipo_geometria = 'point'

            poligono = coords if is_polygon else None
            linea = coords if (not is_polygon and len(coords) >= 2) else None
            if not punto:
                punto = _centroide_simple(poligono or linea or [])
            if not punto:
                continue

            score = 2.0
            dist_km = _distancia_haversine_km(punto, centro)
            if dist_km <= 1.0:
                score += 2.0
            elif dist_km <= 5.0:
                score += 1.0

            resultados.append(
                {
                    'nombre': nombre_elem,
                    'coordenadas': punto,
                    'tipo_geometria': tipo_geometria,
                    'linea': linea,
                    'poligono': poligono,
                    'fuente_validacion': 'osm_overpass',
                    'score': score,
                }
            )

        resultados.sort(key=lambda item: item.get('score', 0.0), reverse=True)
        return resultados
