"""
creacion/langgraph/nodes/generacion.py

Nodo 1 del pipeline: genera la lista cruda de POIs a partir del input del
usuario invocando Gemini.

Responsabilidad única: obtener candidatos de paradas.
No valida coordenadas ni filtra duplicados; eso es tarea del nodo de
validación.

Importa de creacion.langgraph.utils (no de services) para evitar
importación circular.
"""

import logging

from creacion.langgraph.state import State
from creacion.langgraph.utils import (
    ErrorIntegracionIA,
    calcular_objetivo_paradas_ia,
    construir_bloque_allowlist,
    construir_bloque_deseos,
    construir_bloque_metadata,
    llamar_gemini,
)

logger = logging.getLogger(__name__)


def _obtener_pois_allowlist(ciudad: str, moods: list) -> list:
    """Importación diferida para evitar dependencias circulares con services."""
    try:
        from creacion.services import _obtener_pois_allowlist as _svc
        return _svc(ciudad=ciudad, moods=moods)
    except Exception as exc:
        logger.warning('No se pudo obtener allowlist: %s', exc)
        return []


def _construir_pois_fallback_allowlist(ciudad: str, moods: list, cantidad_objetivo: int) -> list:
    """Importación diferida para evitar dependencias circulares con services."""
    try:
        from creacion.services import _construir_pois_fallback_allowlist as _svc
        return _svc(ciudad=ciudad, moods=moods, cantidad_objetivo=cantidad_objetivo)
    except Exception as exc:
        logger.warning('No se pudo construir fallback allowlist: %s', exc)
        return []


def nodo_generacion(state: State) -> dict:
    """Genera POIs crudos con Gemini y los almacena en *pois_crudos*."""
    logger.debug("--- NODO 1: GENERACIÓN DE POIs ---")

    datos = state["usuario_input"]
    objetivo_paradas = calcular_objetivo_paradas_ia(datos)

    bloque_metadata = construir_bloque_metadata(datos.get("metadata") or {})
    bloque_deseos = construir_bloque_deseos(datos.get("deseos") or [])
    pois_allowlist = _obtener_pois_allowlist(
        ciudad=datos.get("ciudad", ""),
        moods=datos.get("mood") or [],
    )
    bloque_allowlist = construir_bloque_allowlist(pois_allowlist)

    prompt = f"""
        Eres un guía turístico experto. Tu tarea es seleccionar los mejores Puntos de Interés (POIs) para
        una ruta en {datos.get('ciudad')}.

        ## Parámetros de la ruta
        - Duración total: {datos.get('duracion')} horas
        - Número de personas: {datos.get('personas')}
        - Nivel de exigencia física: {datos.get('exigencia')}
        - Temática(s): {', '.join(datos.get('mood') or [])}
        {bloque_metadata}
        {bloque_deseos}
        {bloque_allowlist}

        ## Instrucción
        Genera una lista de EXACTAMENTE {objetivo_paradas} POIs adecuados para estos parámetros.
        Ten en cuenta el contexto del solicitante y sus preferencias específicas si las hay.
        Si se han proporcionado POIs recomendados (allowlist), dales prioridad frente a otros lugares
        siempre que encajen con la temática. Puedes complementar con otros POIs si son necesarios.

        Responde ÚNICAMENTE con un JSON válido (sin texto extra) con esta estructura:
        [
            {{"nombre": "Nombre del sitio", "coords": [lat, lon], "desc": "Breve descripción del lugar", "categoria": "Categoría"}}
        ]
    """

    try:
        pois_crudos = llamar_gemini(prompt)
        if not isinstance(pois_crudos, list):
            raise ErrorIntegracionIA("Gemini devolvió un formato inválido.")
    except ErrorIntegracionIA as exc:
        logger.warning("Gemini no disponible; usando fallback de allowlist. Detalle: %s", exc)
        pois_crudos = _construir_pois_fallback_allowlist(
            ciudad=str(datos.get("ciudad") or ""),
            moods=datos.get("mood") or [],
            cantidad_objetivo=objetivo_paradas,
        )
        if len(pois_crudos) < objetivo_paradas:
            raise ErrorIntegracionIA(
                "Gemini no respondió y no hay suficientes POIs en la allowlist para completar la ruta."
            ) from exc

    return {"pois_crudos": pois_crudos}