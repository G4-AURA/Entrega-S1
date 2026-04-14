"""
creacion/langgraph/nodes/validacion.py

Nodo 2 del pipeline: valida y completa los POIs crudos.

Importa de creacion.langgraph.utils para utilidades puras y de
creacion.services con importación diferida (en tiempo de ejecución)
para las funciones que sí necesitan Django, evitando así la
importación circular en tiempo de carga del módulo.
"""

import logging

from creacion.geo_clients import MapboxGeocodingClient, OSMGeocodingClient
from creacion.geo_validation import (
    NoConvergenciaCoordenadasError,
    completar_lista_paradas_validadas,
)
from creacion.exceptions import ErrorIntegracionIA
from creacion.langgraph.state import State
from creacion.langgraph.utils import (
    calcular_objetivo_paradas_ia,
    normalizar_poi_para_optimizacion,
)

logger = logging.getLogger(__name__)


def nodo_validacion(state: State) -> dict:
    """
    Valida coordenadas, deduplica y completa la lista de POIs.

    Lee *pois_crudos* y escribe *pois_validados* + *razones_descarte*.
    """
    logger.debug("--- NODO 2: VALIDACIÓN DE POIs ---")

    # Importaciones diferidas para evitar circular import en carga de módulo
    from creacion.services import (
        _calcular_contexto_regeneracion_pois,
        _normalizar_lista_pois,
        _normalizar_poi_generado_para_validacion,
        _solicitar_pois_adicionales_para_ruta_ia,
    )

    datos = state["usuario_input"]
    pois_crudos = state.get("pois_crudos") or []
    objetivo_paradas = calcular_objetivo_paradas_ia(datos)

    if not isinstance(pois_crudos, list):
        raise ErrorIntegracionIA("La lista de POIs crudos tiene un formato inválido.")

    pois_normalizados = _normalizar_lista_pois(pois_crudos)
    contexto_geo = _calcular_contexto_regeneracion_pois(datos, pois_normalizados)
    ciudad = str(datos.get("ciudad") or "").strip() or "Sin ciudad"

    mapbox_client = MapboxGeocodingClient()
    osm_client = OSMGeocodingClient()

    def _proveedor(cantidad_solicitada, nombres_excluidos, coords_excluidas):
        return _solicitar_pois_adicionales_para_ruta_ia(
            datos=datos,
            cantidad=cantidad_solicitada,
            contexto_geo=contexto_geo,
            nombres_excluidos=nombres_excluidos,
            coords_excluidas=coords_excluidas,
        )

    try:
        validadas = completar_lista_paradas_validadas(
            cantidad_objetivo=objetivo_paradas,
            candidatos_iniciales=pois_crudos,
            normalizador_candidato=_normalizar_poi_generado_para_validacion,
            proveedor_candidatos=_proveedor,
            paradas_existentes=[],
            ciudad=ciudad,
            contexto_geo=contexto_geo,
            mapbox_client=mapbox_client,
            osm_client=osm_client,
        )
    except NoConvergenciaCoordenadasError as exc:
        raise ErrorIntegracionIA(
            "No fue posible completar el tamaño objetivo de paradas con coordenadas precisas."
        ) from exc

    nombres_aceptados = {str(v.get("nombre") or "").strip().lower() for v in validadas}
    razones_descarte = [
        {
            "nombre": str(poi.get("nombre") or "").strip(),
            "coordenadas": poi.get("coordenadas") or [],
            "motivo_rechazo": "No superó validación geográfica o fue duplicado.",
        }
        for poi in pois_normalizados
        if str(poi.get("nombre") or "").strip().lower() not in nombres_aceptados
    ]

    pois_validados = [normalizar_poi_para_optimizacion(v) for v in validadas]

    logger.debug(
        "Validación completada: %d aceptados, %d descartados.",
        len(pois_validados),
        len(razones_descarte),
    )

    return {
        "pois_validados": pois_validados,
        "razones_descarte": razones_descarte,
    }