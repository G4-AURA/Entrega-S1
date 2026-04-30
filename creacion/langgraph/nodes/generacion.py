"""
creacion/langgraph/nodes/generacion.py

Nodo 1 del pipeline: genera la lista cruda de POIs a partir del input del
usuario.

Prioridad de fuentes:
  1. AllowList (POIs curados en BD) — se usa directamente si hay suficientes.
  2. Gemini — solo se invoca cuando la allowlist no tiene POIs suficientes para
     la ciudad y temáticas pedidas (caso mixto: completa los que faltan;
     caso vacío: genera todos).

Responsabilidad única: obtener candidatos de paradas.
No valida coordenadas ni filtra duplicados; eso es tarea del nodo de
validación.

Importa de creacion.langgraph.utils (no de services) para evitar
importación circular.
"""

import logging
import random

from django.db import DatabaseError

from creacion.exceptions import ErrorIntegracionIA
from creacion.langgraph.state import State
from creacion.langgraph.utils import (
    calcular_objetivo_paradas_ia,
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
    except (ImportError, AttributeError, DatabaseError) as exc:
        logger.warning('No se pudo obtener allowlist: %s', exc)
        return []


def _construir_pois_fallback_allowlist(ciudad: str, moods: list, cantidad_objetivo: int) -> list:
    """Importación diferida para evitar dependencias circulares con services."""
    try:
        from creacion.services import _construir_pois_fallback_allowlist as _svc
        return _svc(ciudad=ciudad, moods=moods, cantidad_objetivo=cantidad_objetivo)
    except (ImportError, AttributeError, DatabaseError) as exc:
        logger.warning('No se pudo construir fallback allowlist: %s', exc)
        return []


def _normalizar_pois_allowlist_para_pipeline(pois: list) -> list:
    """Convierte POIs de allowlist al formato estándar esperado por nodo_validacion."""
    resultado = []
    for poi in pois:
        coords = poi.get('coords')
        if not isinstance(coords, list) or len(coords) < 2:
            continue
        nombre = str(poi.get('nombre') or '').strip()
        if not nombre:
            continue
        categoria = str(poi.get('categoria') or 'general')
        resultado.append({
            'nombre': nombre,
            'coords': [float(coords[0]), float(coords[1])],
            'desc': f'POI curado ({categoria})',
            'categoria': categoria,
        })
    return resultado


def _llamar_gemini_para_complemento(
    datos: dict,
    n_faltan: int,
    nombres_excluidos: set,
) -> list:
    """
    Llama a Gemini para generar exactamente n_faltan POIs adicionales,
    excluyendo los nombres ya seleccionados de la allowlist.
    """
    lista_excluidos = ', '.join(f'"{n}"' for n in sorted(nombres_excluidos))
    bloque_metadata = construir_bloque_metadata(datos.get('metadata') or {})
    bloque_deseos = construir_bloque_deseos(datos.get('deseos') or [])

    prompt = f"""
        Eres un guía turístico experto. Tu tarea es seleccionar Puntos de Interés (POIs) para
        completar una ruta en {datos.get('ciudad')}.

        ## Parámetros de la ruta
        - Duración total: {datos.get('duracion')} horas
        - Número de personas: {datos.get('personas')}
        - Nivel de exigencia física: {datos.get('exigencia')}
        - Temática(s): {', '.join(datos.get('mood') or [])}
        {bloque_metadata}
        {bloque_deseos}

        ## Instrucción
        La ruta ya incluye estos lugares (NO los repitas): {lista_excluidos or 'ninguno'}.
        Genera EXACTAMENTE {n_faltan} POIs adicionales y distintos para complementar la ruta.

        Responde ÚNICAMENTE con un JSON válido (sin texto extra) con esta estructura:
        [
            {{"nombre": "Nombre del sitio", "coords": [lat, lon], "desc": "Breve descripción del lugar", "categoria": "Categoría"}}
        ]
    """

    return llamar_gemini(prompt)


def nodo_generacion(state: State) -> dict:
    """
    Genera POIs crudos y los almacena en *pois_crudos*.

    Fuentes en orden de prioridad:
      1. AllowList ≥ objetivo → solo allowlist, sin llamar a Gemini.
      2. 0 < allowlist < objetivo → allowlist + Gemini completa los que faltan.
      3. AllowList vacía → Gemini genera todos (comportamiento original).
    """
    logger.debug("--- NODO 1: GENERACIÓN DE POIs ---")

    datos = state["usuario_input"]
    objetivo_paradas = calcular_objetivo_paradas_ia(datos)
    ciudad = str(datos.get("ciudad") or "")
    moods = datos.get("mood") or []

    pois_allowlist = _obtener_pois_allowlist(ciudad=ciudad, moods=moods)
    n_disponibles = len(pois_allowlist)

    logger.info(
        "AllowList: %d POIs disponibles para ciudad='%s', objetivo=%d",
        n_disponibles, ciudad, objetivo_paradas,
    )

    # ── CASO 1: allowlist tiene suficientes POIs ──────────────────────────────
    if n_disponibles >= objetivo_paradas:
        seleccionados = random.sample(pois_allowlist, objetivo_paradas)
        pois_crudos = _normalizar_pois_allowlist_para_pipeline(seleccionados)
        logger.info(
            "Ruta generada desde allowlist (%d POIs, Gemini omitido), ciudad='%s'",
            len(pois_crudos), ciudad,
        )
        return {"pois_crudos": pois_crudos}

    # ── CASO 2: allowlist parcial → mezcla con Gemini ────────────────────────
    if n_disponibles > 0:
        pois_base = _normalizar_pois_allowlist_para_pipeline(pois_allowlist)
        nombres_excluidos = {p['nombre'] for p in pois_base}
        faltan = objetivo_paradas - len(pois_base)
        logger.info(
            "Allowlist parcial (%d/%d): Gemini generará %d POIs adicionales, ciudad='%s'",
            len(pois_base), objetivo_paradas, faltan, ciudad,
        )
        try:
            pois_gemini = _llamar_gemini_para_complemento(datos, faltan, nombres_excluidos)
            if not isinstance(pois_gemini, list):
                raise ErrorIntegracionIA("Gemini devolvió un formato inválido.")
        except ErrorIntegracionIA as exc:
            logger.warning(
                "Gemini no disponible para complementar; usando solo los %d POIs de allowlist. Detalle: %s",
                len(pois_base), exc,
            )
            pois_gemini = []

        pois_crudos = pois_base + pois_gemini
        return {"pois_crudos": pois_crudos}

    # ── CASO 3: allowlist vacía → Gemini genera todos ────────────────────────
    bloque_metadata = construir_bloque_metadata(datos.get("metadata") or {})
    bloque_deseos = construir_bloque_deseos(datos.get("deseos") or [])

    prompt = f"""
        Eres un guía turístico experto. Tu tarea es seleccionar los mejores Puntos de Interés (POIs) para
        una ruta en {datos.get('ciudad')}.

        ## Parámetros de la ruta
        - Duración total: {datos.get('duracion')} horas
        - Número de personas: {datos.get('personas')}
        - Nivel de exigencia física: {datos.get('exigencia')}
        - Temática(s): {', '.join(moods)}
        {bloque_metadata}
        {bloque_deseos}

        ## Instrucción
        Genera una lista de EXACTAMENTE {objetivo_paradas} POIs adecuados para estos parámetros basándote en tu conocimiento experto de la ciudad.
        Ten en cuenta el contexto del solicitante y sus preferencias específicas si las hay.

        Responde ÚNICAMENTE con un JSON válido (sin texto extra) con esta estructura:
        [
            {{"nombre": "Nombre del sitio", "coords": [lat, lon], "desc": "Breve descripción del lugar", "categoria": "Categoría"}}
        ]
    """

    logger.info("AllowList vacía para ciudad='%s'; delegando generación completa a Gemini.", ciudad)

    try:
        pois_crudos = llamar_gemini(prompt)
        if not isinstance(pois_crudos, list):
            raise ErrorIntegracionIA("Gemini devolvió un formato inválido.")
    except ErrorIntegracionIA as exc:
        logger.warning("Gemini no disponible; usando fallback de allowlist. Detalle: %s", exc)
        pois_crudos = _construir_pois_fallback_allowlist(
            ciudad=ciudad,
            moods=moods,
            cantidad_objetivo=objetivo_paradas,
        )
        if len(pois_crudos) < objetivo_paradas:
            raise ErrorIntegracionIA(
                "Gemini no respondió y no hay suficientes POIs en la allowlist para completar la ruta."
            ) from exc

    return {"pois_crudos": pois_crudos}
