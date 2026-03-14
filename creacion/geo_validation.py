import math
import re
from collections.abc import Callable
from typing import Any

from creacion.geo_clients import MapboxGeocodingClient, OSMGeocodingClient

MAX_REINTENTOS_POR_PARADA = 3
FACTOR_PRESUPUESTO_GLOBAL = 2

UMBRAL_POR_TIPO_GEOMETRIA_M = {
    'building': 15.0,
    'area': 15.0,
    'linear': 20.0,
    'point': 20.0,
    'unknown': 20.0,
}


class NoConvergenciaCoordenadasError(Exception):
    """No se pudo completar una lista de paradas válidas dentro del presupuesto."""


NormalizadorCandidato = Callable[[Any, int], dict[str, Any] | None]
ProveedorCandidatos = Callable[[int, set[str], set[tuple[float, float]]], list[Any]]


def _normalizar_nombre_para_dedupe(nombre: str) -> str:
    return ' '.join(str(nombre or '').strip().lower().split())


def _clave_coordenadas_para_dedupe(coordenadas: list[float]) -> tuple[float, float]:
    return (round(float(coordenadas[0]), 5), round(float(coordenadas[1]), 5))


def _distancia_haversine_m(coord_a: list[float], coord_b: list[float]) -> float:
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
    return radio_tierra_km * c * 1000.0


def _to_xy_m(coordenada: list[float], ref_lat: float) -> tuple[float, float]:
    lat, lon = coordenada
    x = lon * 111320.0 * math.cos(math.radians(ref_lat))
    y = lat * 110540.0
    return x, y


def _from_xy_m(x: float, y: float, ref_lat: float) -> list[float]:
    lat = y / 110540.0
    denom = 111320.0 * math.cos(math.radians(ref_lat))
    lon = x / denom if denom else 0.0
    return [lat, lon]


def _distancia_punto_segmento_m(
    punto: list[float],
    seg_a: list[float],
    seg_b: list[float],
) -> tuple[float, list[float]]:
    ref_lat = punto[0]
    px, py = _to_xy_m(punto, ref_lat)
    ax, ay = _to_xy_m(seg_a, ref_lat)
    bx, by = _to_xy_m(seg_b, ref_lat)

    abx = bx - ax
    aby = by - ay
    ab_norm2 = abx * abx + aby * aby
    if ab_norm2 == 0:
        dist = math.hypot(px - ax, py - ay)
        return dist, seg_a

    apx = px - ax
    apy = py - ay
    t = (apx * abx + apy * aby) / ab_norm2
    t = max(0.0, min(1.0, t))
    proj_x = ax + t * abx
    proj_y = ay + t * aby

    dist = math.hypot(px - proj_x, py - proj_y)
    proj = _from_xy_m(proj_x, proj_y, ref_lat)
    return dist, proj


def _punto_mas_cercano_en_linea(punto: list[float], linea: list[list[float]]) -> tuple[float, list[float]]:
    mejor_dist = float('inf')
    mejor_punto = linea[0]

    for idx in range(len(linea) - 1):
        dist, proy = _distancia_punto_segmento_m(punto, linea[idx], linea[idx + 1])
        if dist < mejor_dist:
            mejor_dist = dist
            mejor_punto = proy

    return mejor_dist, mejor_punto


def _punto_en_poligono(punto: list[float], poligono: list[list[float]]) -> bool:
    if len(poligono) < 3:
        return False

    x, y = punto[1], punto[0]
    dentro = False
    n = len(poligono)

    for i in range(n):
        x1, y1 = poligono[i][1], poligono[i][0]
        x2, y2 = poligono[(i + 1) % n][1], poligono[(i + 1) % n][0]
        cruza = ((y1 > y) != (y2 > y))
        if not cruza:
            continue

        den = (y2 - y1)
        if den == 0:
            continue
        x_intersect = ((x2 - x1) * (y - y1) / den) + x1
        if x < x_intersect:
            dentro = not dentro

    return dentro


def _punto_mas_cercano_en_borde_poligono(
    punto: list[float],
    poligono: list[list[float]],
) -> tuple[float, list[float]]:
    if len(poligono) < 2:
        return float('inf'), punto

    mejor_dist = float('inf')
    mejor_punto = poligono[0]

    total = len(poligono)
    for idx in range(total):
        a = poligono[idx]
        b = poligono[(idx + 1) % total]
        dist, proy = _distancia_punto_segmento_m(punto, a, b)
        if dist < mejor_dist:
            mejor_dist = dist
            mejor_punto = proy

    return mejor_dist, mejor_punto


def _es_lineal_por_contexto(nombre: str, categoria: str) -> bool:
    texto = f'{nombre} {categoria}'.lower()
    palabras_lineales = ('puente', 'bridge', 'pasarela', 'viaducto', 'muralla', 'camino')
    return any(palabra in texto for palabra in palabras_lineales)


def _esta_en_contexto_geografico(coordenadas: list[float], contexto_geo: dict[str, Any]) -> bool:
    centro = contexto_geo.get('centro')
    radio_km = contexto_geo.get('radio_km')
    if not isinstance(centro, list) or len(centro) < 2:
        return True
    if radio_km in (None, 0):
        return True

    dist_m = _distancia_haversine_m(coordenadas, centro)
    return dist_m <= float(radio_km) * 1000.0


def _variantes_nombre(nombre: str) -> list[str]:
    base = str(nombre or '').strip()
    if not base:
        return []

    variantes = [base]
    sin_parentesis = re.sub(r'\s*\([^)]*\)', '', base).strip()
    if sin_parentesis and sin_parentesis not in variantes:
        variantes.append(sin_parentesis)

    sin_guion = base.split('-', 1)[0].strip()
    if sin_guion and sin_guion not in variantes:
        variantes.append(sin_guion)

    return variantes[:MAX_REINTENTOS_POR_PARADA]


def _resolver_geometrias_autoridad(
    *,
    nombre: str,
    categoria: str,
    ciudad: str,
    centro: list[float] | None,
    mapbox_client: MapboxGeocodingClient,
    osm_client: OSMGeocodingClient,
) -> list[dict[str, Any]]:
    candidatos: list[dict[str, Any]] = []

    candidatos.extend(
        osm_client.buscar_lugares(
            nombre=nombre,
            ciudad=ciudad,
            centro=centro,
            limit=6,
        )
    )
    candidatos.extend(
        mapbox_client.buscar_lugares(
            nombre=nombre,
            ciudad=ciudad,
            centro=centro,
            limit=5,
        )
    )

    if _es_lineal_por_contexto(nombre, categoria):
        candidatos.extend(
            osm_client.buscar_geometria_lineal_cercana(
                nombre=nombre,
                centro=centro or [0.0, 0.0],
                radio_m=280,
                limit=8,
            )
        )

    resultados = []
    vistas: set[tuple[str, tuple[float, float]]] = set()
    for cand in candidatos:
        coord = cand.get('coordenadas')
        if not isinstance(coord, list) or len(coord) < 2:
            continue
        clave = (
            str(cand.get('fuente_validacion') or ''),
            _clave_coordenadas_para_dedupe(coord),
        )
        if clave in vistas:
            continue
        vistas.add(clave)
        resultados.append(cand)

    resultados.sort(key=lambda item: float(item.get('score') or 0.0), reverse=True)
    return resultados


def _corregir_segun_geometria(
    *,
    coordenadas_originales: list[float],
    geometria_ref: dict[str, Any],
) -> tuple[list[float], float, str, bool]:
    tipo = str(geometria_ref.get('tipo_geometria') or 'unknown').lower()
    if tipo not in UMBRAL_POR_TIPO_GEOMETRIA_M:
        tipo = 'unknown'

    umbral_m = UMBRAL_POR_TIPO_GEOMETRIA_M[tipo]
    punto_ref = geometria_ref.get('coordenadas') or coordenadas_originales

    if tipo == 'linear' and isinstance(geometria_ref.get('linea'), list) and len(geometria_ref['linea']) >= 2:
        distancia_linea_m, punto_corregido = _punto_mas_cercano_en_linea(
            coordenadas_originales,
            geometria_ref['linea'],
        )
        corregida = distancia_linea_m > 1.0
        if distancia_linea_m > umbral_m:
            corregida = True
        return (punto_corregido if corregida else coordenadas_originales, distancia_linea_m, tipo, corregida)

    if tipo in {'building', 'area'} and isinstance(geometria_ref.get('poligono'), list) and len(geometria_ref['poligono']) >= 3:
        distancia_borde_m, borde_mas_cercano = _punto_mas_cercano_en_borde_poligono(
            coordenadas_originales,
            geometria_ref['poligono'],
        )
        esta_dentro = _punto_en_poligono(coordenadas_originales, geometria_ref['poligono'])
        corregida = esta_dentro or distancia_borde_m > umbral_m
        return (borde_mas_cercano if corregida else coordenadas_originales, distancia_borde_m, tipo, corregida)

    error_m = _distancia_haversine_m(coordenadas_originales, punto_ref)
    corregida = error_m > umbral_m
    return (punto_ref if corregida else coordenadas_originales, error_m, tipo, corregida)


def validar_y_corregir_parada(
    parada: dict[str, Any],
    *,
    ciudad: str,
    contexto_geo: dict[str, Any],
    mapbox_client: MapboxGeocodingClient,
    osm_client: OSMGeocodingClient,
    max_reintentos: int = MAX_REINTENTOS_POR_PARADA,
) -> dict[str, Any] | None:
    nombre = str(parada.get('nombre') or '').strip()
    if not nombre:
        return None

    coordenadas = parada.get('coordenadas')
    if not isinstance(coordenadas, list) or len(coordenadas) < 2:
        return None

    coordenadas_originales = [float(coordenadas[0]), float(coordenadas[1])]
    categoria = str(parada.get('categoria') or '').strip()
    centro = contexto_geo.get('centro') if isinstance(contexto_geo, dict) else None

    variantes = _variantes_nombre(nombre)
    if not variantes:
        return None

    for variante in variantes[:max_reintentos]:
        geometrias = _resolver_geometrias_autoridad(
            nombre=variante,
            categoria=categoria,
            ciudad=ciudad,
            centro=centro,
            mapbox_client=mapbox_client,
            osm_client=osm_client,
        )
        if not geometrias:
            continue

        for geometria in geometrias:
            coord_ref = geometria.get('coordenadas')
            if not isinstance(coord_ref, list) or len(coord_ref) < 2:
                continue
            if not _esta_en_contexto_geografico(coord_ref, contexto_geo):
                continue

            coordenadas_corregidas, error_m, tipo_geometria, corregida = _corregir_segun_geometria(
                coordenadas_originales=coordenadas_originales,
                geometria_ref=geometria,
            )
            if not _esta_en_contexto_geografico(coordenadas_corregidas, contexto_geo):
                continue

            parada_validada = dict(parada)
            parada_validada['coordenadas'] = [
                round(float(coordenadas_corregidas[0]), 6),
                round(float(coordenadas_corregidas[1]), 6),
            ]
            parada_validada['fuente_validacion'] = str(geometria.get('fuente_validacion') or 'desconocida')
            parada_validada['tipo_geometria'] = tipo_geometria
            parada_validada['error_m'] = round(float(error_m), 2)
            parada_validada['corregida'] = bool(corregida)
            return parada_validada

    return None


def completar_lista_paradas_validadas(
    *,
    cantidad_objetivo: int,
    candidatos_iniciales: list[Any],
    normalizador_candidato: NormalizadorCandidato,
    proveedor_candidatos: ProveedorCandidatos,
    paradas_existentes: list[dict[str, Any]],
    ciudad: str,
    contexto_geo: dict[str, Any],
    mapbox_client: MapboxGeocodingClient,
    osm_client: OSMGeocodingClient,
    max_reintentos_por_parada: int = MAX_REINTENTOS_POR_PARADA,
    factor_presupuesto_global: int = FACTOR_PRESUPUESTO_GLOBAL,
) -> list[dict[str, Any]]:
    if cantidad_objetivo <= 0:
        raise NoConvergenciaCoordenadasError('La cantidad objetivo debe ser mayor que 0.')

    presupuesto_global = max(cantidad_objetivo, cantidad_objetivo * max(1, int(factor_presupuesto_global)))

    nombres_bloqueados: set[str] = set()
    coords_bloqueadas: set[tuple[float, float]] = set()

    for parada in paradas_existentes or []:
        nombre = _normalizar_nombre_para_dedupe(parada.get('nombre'))
        coordenadas = parada.get('coordenadas')
        if nombre:
            nombres_bloqueados.add(nombre)
        if isinstance(coordenadas, list) and len(coordenadas) >= 2:
            coords_bloqueadas.add(_clave_coordenadas_para_dedupe(coordenadas))

    nombres_descartados: set[str] = set()
    coords_descartadas: set[tuple[float, float]] = set()

    cola = list(candidatos_iniciales or [])
    aceptadas: list[dict[str, Any]] = []

    evaluadas = 0
    idx_normalizacion = 1

    while len(aceptadas) < cantidad_objetivo and evaluadas < presupuesto_global:
        if not cola:
            restantes = cantidad_objetivo - len(aceptadas)
            capacidad_restante = presupuesto_global - evaluadas
            cantidad_a_pedir = min(capacidad_restante, max(1, restantes * 2))
            if cantidad_a_pedir <= 0:
                break

            nuevos = proveedor_candidatos(
                cantidad_a_pedir,
                nombres_bloqueados | nombres_descartados,
                coords_bloqueadas | coords_descartadas,
            )
            cola.extend(nuevos or [])
            if not nuevos:
                break

        raw = cola.pop(0)
        evaluadas += 1

        candidato = normalizador_candidato(raw, idx_normalizacion)
        idx_normalizacion += 1
        if not candidato:
            continue

        nombre_key = _normalizar_nombre_para_dedupe(candidato.get('nombre'))
        coords = candidato.get('coordenadas')
        if not isinstance(coords, list) or len(coords) < 2:
            if nombre_key:
                nombres_descartados.add(nombre_key)
            continue

        coords_key = _clave_coordenadas_para_dedupe(coords)
        if (
            nombre_key in nombres_bloqueados
            or nombre_key in nombres_descartados
            or coords_key in coords_bloqueadas
            or coords_key in coords_descartadas
        ):
            if nombre_key:
                nombres_descartados.add(nombre_key)
            coords_descartadas.add(coords_key)
            continue

        validada = validar_y_corregir_parada(
            candidato,
            ciudad=ciudad,
            contexto_geo=contexto_geo,
            mapbox_client=mapbox_client,
            osm_client=osm_client,
            max_reintentos=max_reintentos_por_parada,
        )

        if not validada:
            if nombre_key:
                nombres_descartados.add(nombre_key)
            coords_descartadas.add(coords_key)
            continue

        nombre_validada = _normalizar_nombre_para_dedupe(validada.get('nombre'))
        coords_validada = validada.get('coordenadas')
        if not isinstance(coords_validada, list) or len(coords_validada) < 2:
            if nombre_key:
                nombres_descartados.add(nombre_key)
            continue

        coords_validada_key = _clave_coordenadas_para_dedupe(coords_validada)
        if (
            nombre_validada in nombres_bloqueados
            or nombre_validada in nombres_descartados
            or coords_validada_key in coords_bloqueadas
            or coords_validada_key in coords_descartadas
        ):
            if nombre_validada:
                nombres_descartados.add(nombre_validada)
            coords_descartadas.add(coords_validada_key)
            continue

        validada['id_sugerencia'] = len(aceptadas) + 1
        aceptadas.append(validada)

        if nombre_validada:
            nombres_bloqueados.add(nombre_validada)
        coords_bloqueadas.add(coords_validada_key)

    if len(aceptadas) != cantidad_objetivo:
        raise NoConvergenciaCoordenadasError(
            f'No fue posible completar {cantidad_objetivo} paradas válidas '
            f'tras validar coordenadas (obtenidas {len(aceptadas)}/{cantidad_objetivo}, presupuesto={presupuesto_global}).'
        )

    return aceptadas
