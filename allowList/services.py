"""
allowlist/services.py

Lógica de negocio del sistema de gestión de la Allowlist de POIs.

Módulos:
  1. Curación asistida (OpenStreetMap): traduce filtros a Overpass QL y procesa resultados.
  2. Creación manual: valida y persiste POIs individuales.
  3. Consulta: serialización y filtrado para el motor de rutas.
"""
import math
import logging
from typing import Any

import requests
from django.contrib.gis.geos import Point
from django.db import DatabaseError, IntegrityError, transaction

from .models import CategoriaOSM, POI
from .paises import resolver_iso_pais

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Excepciones de dominio
# ─────────────────────────────────────────────────────────────────────────────

class ErrorAllowlistBase(Exception):
    """Clase base para errores del módulo allowlist."""


class ErrorValidacionPOI(ErrorAllowlistBase):
    """Datos de entrada inválidos."""


class ErrorIntegracionOSM(ErrorAllowlistBase):
    """Fallo al comunicarse con la Overpass API."""


class ErrorPersistenciaPOI(ErrorAllowlistBase):
    """Error al guardar en base de datos."""


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
OVERPASS_TIMEOUT = 30          # segundos
MAX_RESULTADOS_OSM = 100       # límite de elementos por búsqueda

# Mapa de CategoriaOSM.value → (clave_osm, valor_osm) para construir la query
_CATEGORIA_A_TAG: dict[str, tuple[str, str]] = {}
for _choice_value, _ in CategoriaOSM.choices:
    if '=' in _choice_value:
        _k, _v = _choice_value.split('=', 1)
        _CATEGORIA_A_TAG[_choice_value] = (_k, _v)


# ─────────────────────────────────────────────────────────────────────────────
# Módulo 1 – Curación asistida OSM
# ─────────────────────────────────────────────────────────────────────────────

def _normalizar_nombre_lugar(nombre: str) -> str:
    """
    Normaliza el nombre de una ciudad o área.

    Aplica capitalización tipo título respetando partículas cortas habituales
    en topónimos españoles/latinos (de, del, la, el, los, las, y) que se
    mantienen en minúsculas salvo que sean la primera palabra.

    Ejemplos:
        "sevilla"                 → "Sevilla"
        "CÓRDOBA"                 → "Córdoba"
        "santiago de compostela"  → "Santiago de Compostela"
        "la coruña"               → "La Coruña"
    """
    particulas = {'de', 'del', 'la', 'el', 'los', 'las', 'y', 'i', 'of', 'the'}
    palabras = nombre.strip().split()
    resultado = []
    for i, palabra in enumerate(palabras):
        if i == 0 or palabra.lower() not in particulas:
            resultado.append(palabra.capitalize())
        else:
            resultado.append(palabra.lower())
    return ' '.join(resultado)


def _construir_overpass_query(area_nombre: str, categorias: list[str], pais: str = '') -> str:
    """
    Genera una query Overpass QL a partir de los filtros del administrador.

    Estrategia:
      - Busca el área geográfica por nombre con geocodeArea.
      - Para cada categoría seleccionada añade un bloque node/way/relation.
      - Usa `out center` para obtener siempre una coordenada central aunque
        el elemento sea un polígono (way/relation).

    Args:
        area_nombre:  Nombre de ciudad o área (ej. "Sevilla").
        categorias:   Lista de valores de CategoriaOSM (ej. ["tourism=museum"]).
        pais:         País o región para desambiguar (ej. "España"). Opcional.
    Returns:
        String con la query Overpass QL lista para enviar.
    """

    iso = resolver_iso_pais(pais) if pais else None

    if iso:
        cabecera = (
            f'area["ISO3166-1"="{iso}"]["admin_level"="2"]->.countryArea;\n'
            f'area[name="{area_nombre}"]->.searchArea;\n'
        )
        filtro_area = '(area.searchArea)(area.countryArea)'
    else:
        if pais:
            logger.warning('País "%s" no reconocido; se buscará sin filtro de país.', pais)
        cabecera = f'area[name="{area_nombre}"]->.searchArea;\n'
        filtro_area = '(area.searchArea)'

    bloques = []
    for cat in categorias:
        tag = _CATEGORIA_A_TAG.get(cat)
        if not tag:
            continue
        k, v = tag
        filtro = f'["{k}"="{v}"]'
        
        bloques.append(f'  node{filtro}{filtro_area};')
        bloques.append(f'  way{filtro}{filtro_area};')
        bloques.append(f'  relation{filtro}{filtro_area};')

    if not bloques:
        raise ErrorValidacionPOI('Debes seleccionar al menos una categoría válida.')

    cuerpo = '\n'.join(bloques)

    query = (
        f'[out:json][timeout:{OVERPASS_TIMEOUT}];\n'
        f'{cabecera}'
        f'(\n'
        f'{cuerpo}\n'
        f');\n'
        f'out center {MAX_RESULTADOS_OSM};'
    )
    print(query)
    return query


def _extraer_coordenadas_elemento(elemento: dict) -> tuple[float, float] | None:
    """
    Extrae (lat, lon) de un elemento Overpass, soportando nodes y ways/relations
    (estos últimos devuelven las coordenadas en el campo 'center').
    """
    tipo = elemento.get('type')
    if tipo == 'node':
        lat = elemento.get('lat')
        lon = elemento.get('lon')
    else:
        centro = elemento.get('center', {})
        lat = centro.get('lat')
        lon = centro.get('lon')

    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _normalizar_categoria_desde_tags(tags: dict) -> str:
    """
    Determina la CategoriaOSM más específica a partir de los tags OSM del elemento.
    Recorre los tags y devuelve el primer match conocido; si no hay, 'other'.
    """
    for choice_value in _CATEGORIA_A_TAG:
        k, v = _CATEGORIA_A_TAG[choice_value]
        if tags.get(k) == v:
            return choice_value
    return CategoriaOSM.OTRO


def buscar_pois_osm(ciudad: str, categorias: list[str], pais: str = '') -> list[dict]:
    """
    Ejecuta una búsqueda en la Overpass API y devuelve los resultados normalizados.

    Args:
        ciudad:     Nombre de la ciudad o área geográfica.
        categorias: Lista de valores CategoriaOSM seleccionados.
    Returns:
        Lista de dicts con estructura homogénea para renderizado en el panel.
    Raises:
        ErrorValidacionPOI:  Parámetros de entrada incorrectos.
        ErrorIntegracionOSM: Fallo HTTP o de red con la Overpass API.
    """
    ciudad = _normalizar_nombre_lugar(str(ciudad or '').strip())
    if not ciudad:
        raise ErrorValidacionPOI('Debes indicar una ciudad o área geográfica.')

    query = _construir_overpass_query(ciudad, categorias, pais=pais)

    try:
        respuesta = requests.post(
            OVERPASS_URL,
            data={'data': query},
            timeout=OVERPASS_TIMEOUT + 5,
            headers={'User-Agent': 'AURA-RouteApp/1.0'},
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.Timeout:
        raise ErrorIntegracionOSM('La búsqueda en OpenStreetMap tardó demasiado. Intenta reducir el área o las categorías.')
    except requests.HTTPError as exc:
        raise ErrorIntegracionOSM(f'Error HTTP al consultar OpenStreetMap ({exc.response.status_code}).')
    except requests.RequestException as exc:
        raise ErrorIntegracionOSM(f'Error de red al conectar con OpenStreetMap: {exc}')
    except (ValueError, KeyError) as exc:
        raise ErrorIntegracionOSM(f'Respuesta inesperada de OpenStreetMap: {exc}')

    elementos = datos.get('elements', [])
    resultados: list[dict] = []

    # IDs de POIs ya en la allowlist para marcarlos como importados
    osm_ids_existentes = set(
        POI.objects.filter(osm_id__isnull=False).values_list('osm_id', flat=True)
    )

    for elem in elementos:
        coords = _extraer_coordenadas_elemento(elem)
        if not coords:
            continue

        lat, lon = coords
        tags = elem.get('tags', {})
        nombre = tags.get('name', '').strip()
        if not nombre:
            continue

        osm_id = elem.get('id')
        categoria = _normalizar_categoria_desde_tags(tags)

        resultados.append({
            'osm_id':   osm_id,
            'osm_type': elem.get('type', 'node'),
            'nombre':   nombre,
            'lat':      lat,
            'lon':      lon,
            'categoria':    categoria,
            'categoria_label': dict(CategoriaOSM.choices).get(categoria, 'Otro'),
            'direccion':    tags.get('addr:street', ''),
            'ya_importado': osm_id in osm_ids_existentes,
        })

    return resultados


def importar_pois_desde_osm(
    elementos_seleccionados: list[dict],
    ciudad: str,
) -> dict[str, int]:
    """
    Persiste en la Allowlist los POIs seleccionados por el administrador.

    Utiliza `get_or_create` sobre `osm_id` para ser idempotente:
    re-importar el mismo POI no crea duplicados.

    Args:
        elementos_seleccionados: Lista de dicts con campos osm_id, osm_type,
                                 nombre, lat, lon, categoria.
        ciudad:  Nombre de la ciudad para rellenar el campo ciudad del POI.
    Returns:
        Dict con contadores: {'creados': N, 'ya_existian': M, 'errores': K}
    """
    if not elementos_seleccionados:
        raise ErrorValidacionPOI('No se proporcionaron elementos para importar.')

    creados = ya_existian = errores = 0

    for elem in elementos_seleccionados:
        try:
            osm_id   = int(elem['osm_id'])
            nombre   = str(elem.get('nombre') or '').strip()
            lat      = float(elem['lat'])
            lon      = float(elem['lon'])
            categoria = str(elem.get('categoria') or CategoriaOSM.OTRO)
            osm_type = str(elem.get('osm_type') or 'node')

            if not nombre:
                errores += 1
                continue

            with transaction.atomic():
                _, fue_creado = POI.objects.get_or_create(
                    osm_id=osm_id,
                    defaults={
                        'nombre':      nombre,
                        'categoria':   categoria,
                        'coordenadas': Point(lon, lat, srid=4326),
                        'ciudad':      str(ciudad or '').strip(),
                        'fuente':      POI.Fuente.OSM,
                        'osm_type':    osm_type,
                    },
                )
            if fue_creado:
                creados += 1
            else:
                ya_existian += 1

        except (KeyError, TypeError, ValueError) as exc:
            logger.warning('Error procesando elemento OSM para importación: %s | %s', elem, exc)
            errores += 1
        except (DatabaseError, IntegrityError) as exc:
            logger.error('Error de BD al importar POI OSM id=%s: %s', elem.get('osm_id'), exc)
            errores += 1

    return {'creados': creados, 'ya_existian': ya_existian, 'errores': errores}


# ─────────────────────────────────────────────────────────────────────────────
# Módulo 2 – Creación manual
# ─────────────────────────────────────────────────────────────────────────────

def crear_poi_manual(
    nombre: str,
    lat: Any,
    lon: Any,
    categoria: str,
    ciudad: str = '',
    direccion: str = '',
) -> POI:
    """
    Crea un POI de origen manual y lo persiste en la Allowlist.

    Args:
        nombre:    Nombre del lugar (obligatorio).
        lat:       Latitud (float o string convertible).
        lon:       Longitud (float o string convertible).
        categoria: Valor de CategoriaOSM (obligatorio).
        ciudad:    Nombre de la ciudad (opcional).
        direccion: Dirección textual (opcional).
    Returns:
        Instancia POI recién creada.
    Raises:
        ErrorValidacionPOI:   Datos incompletos o inválidos.
        ErrorPersistenciaPOI: Fallo al guardar en BD.
    """
    nombre = str(nombre or '').strip()
    if not nombre:
        raise ErrorValidacionPOI('El nombre del lugar es obligatorio.')
    if len(nombre) > 255:
        raise ErrorValidacionPOI('El nombre no puede superar los 255 caracteres.')

    categorias_validas = {v for v, _ in CategoriaOSM.choices}
    if categoria not in categorias_validas:
        raise ErrorValidacionPOI(f'Categoría no válida: "{categoria}".')

    try:
        lat_f = float(str(lat).strip())
        lon_f = float(str(lon).strip())
    except (TypeError, ValueError):
        raise ErrorValidacionPOI('Las coordenadas deben ser números válidos.')

    if not (-90 <= lat_f <= 90):
        raise ErrorValidacionPOI('La latitud debe estar entre -90 y 90.')
    if not (-180 <= lon_f <= 180):
        raise ErrorValidacionPOI('La longitud debe estar entre -180 y 180.')

    try:
        poi = POI.objects.create(
            nombre      = nombre,
            categoria   = categoria,
            coordenadas = Point(lon_f, lat_f, srid=4326),
            ciudad      = str(ciudad or '').strip(),
            direccion   = str(direccion or '').strip(),
            fuente      = POI.Fuente.MANUAL,
        )
    except (DatabaseError, IntegrityError) as exc:
        raise ErrorPersistenciaPOI('No se pudo guardar el POI en la base de datos.') from exc

    return poi


# ─────────────────────────────────────────────────────────────────────────────
# Módulo 3 – Consulta y listado
# ─────────────────────────────────────────────────────────────────────────────

def listar_pois(
    ciudad: str = '',
    categoria: str = '',
    fuente: str = '',
    page: int = 1,
    limit: int = 20,
) -> dict:
    """
    Devuelve un listado paginado de POIs para el panel de administración.
    """
    qs = POI.objects.order_by('nombre')

    if ciudad:
        qs = qs.filter(ciudad__icontains=ciudad.strip())
    if categoria:
        qs = qs.filter(categoria=categoria)
    if fuente:
        qs = qs.filter(fuente=fuente)

    total = qs.count()
    offset = (page - 1) * limit
    pois_paginados = qs[offset: offset + limit]

    resultados = []
    for poi in pois_paginados:
        resultados.append({
            'id':        poi.id,
            'nombre':    poi.nombre,
            'categoria': poi.categoria,
            'categoria_label': poi.get_categoria_display(),
            'lat':       poi.lat,
            'lon':       poi.lon,
            'ciudad':    poi.ciudad,
            'direccion': poi.direccion,
            'fuente':    poi.fuente,
            'osm_id':    poi.osm_id,
        })

    return {
        'results':      resultados,
        'total':        total,
        'page':         page,
        'total_pages':  math.ceil(total / limit) if total else 1,
        'limit':        limit,
    }


def eliminar_poi(poi_id: int) -> None:
    """Elimina permanentemente un POI de la Allowlist."""
    try:
        poi = POI.objects.get(id=poi_id)
    except POI.DoesNotExist:
        raise ErrorValidacionPOI(f'No existe ningún POI con id={poi_id}.')
    poi.delete()


def serializar_pois_para_ruta(ciudad: str, categorias: list[str] | None = None) -> list[dict]:
    """
    Devuelve los POIs de una ciudad listos para ser inyectados
    en el motor de generación de rutas como alternativa curada a la IA.

    Args:
        ciudad:     Nombre de la ciudad (búsqueda insensible a mayúsculas).
        categorias: Lista opcional de valores CategoriaOSM para filtrar.
    Returns:
        Lista de dicts con 'nombre', 'coords' [lat, lon] y 'desc'.
    """
    qs = POI.objects.filter(ciudad__icontains=ciudad.strip())

    if categorias:
        qs = qs.filter(categoria__in=categorias)

    return [
        {
            'nombre': poi.nombre,
            'coords': [poi.lat, poi.lon],
            'desc':   poi.get_categoria_display(),
        }
        for poi in qs.order_by('nombre')
    ]