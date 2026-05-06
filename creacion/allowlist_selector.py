"""
Selector desacoplado de POIs para rutas IA.

Objetivos:
1) Priorizar el ranking nativo de Google SearchText (rankPreference=RELEVANCE).
2) Respetar coherencia mood -> categoría allowlist.
3) Filtrar por polígono oficial de ciudad cuando exista.
4) No devolver POIs de otras ciudades como fallback.
5) Reservar POIs icónicos/top para que aparezcan con frecuencia.
6) Introducir aleatoriedad controlada para evitar rutas clónicas.
"""

from __future__ import annotations

import hashlib
import secrets
import unicodedata
from dataclasses import dataclass

from creacion.config.mood_allowlist_map import (
    ALLOWLIST_SCORE_WEIGHTS,
    MOOD_ALIASES,
    MOOD_CATEGORY_WEIGHTS,
)


@dataclass(frozen=True)
class _CandidateScore:
    poi_id: int
    final_score: float
    google_score: float
    mood_score: float
    city_score: float


def _normalizar_texto(valor: str) -> str:
    base = str(valor or '').strip().lower()
    if not base:
        return ''
    normalized = unicodedata.normalize('NFD', base)
    normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
    return ' '.join(normalized.split())


def _normalizar_moods(moods: list[str]) -> list[str]:
    resultado: list[str] = []
    vistos: set[str] = set()
    for raw in moods or []:
        mood = _normalizar_texto(raw)
        if not mood:
            continue
        mood = MOOD_ALIASES.get(mood, mood)
        if mood in vistos:
            continue
        vistos.add(mood)
        resultado.append(mood)
    return resultado


def _build_category_weights(moods: list[str]) -> dict[str, float]:
    pesos: dict[str, float] = {}
    for mood in _normalizar_moods(moods):
        for categoria, peso in (MOOD_CATEGORY_WEIGHTS.get(mood) or {}).items():
            if peso > pesos.get(categoria, 0.0):
                pesos[categoria] = float(peso)
    return pesos


def _google_relevance_score(rank_position: int | None) -> float:
    if rank_position is None:
        return 0.05
    try:
        pos = int(rank_position)
    except (TypeError, ValueError):
        return 0.05
    if pos <= 0:
        return 0.05
    return 1.0 / float(pos)


def _resolve_city_boundary(ciudad: str):
    """
    Devuelve CityBoundary activo para la ciudad solicitada o None.
    Matching tolerante a acentos/mayúsculas.
    """
    from allowList.models import CityBoundary

    ciudad_norm = _normalizar_texto(ciudad)
    if not ciudad_norm:
        return None

    for boundary in CityBoundary.objects.filter(active=True).only('id', 'city_name', 'polygon'):
        if _normalizar_texto(boundary.city_name) == ciudad_norm:
            return boundary
    return None


def _weighted_sample_without_replacement(
    scored_items: list[_CandidateScore],
    sample_size: int,
    seed: int | None = None,
) -> list[int]:
    pool = list(scored_items)
    selected_ids: list[int] = []
    remaining = min(sample_size, len(pool))

    for step in range(remaining):
        total = sum(max(item.final_score, 1e-6) for item in pool)
        threshold = _random_unit_interval(seed, step, pool) * total
        acumulado = 0.0

        for idx, item in enumerate(pool):
            acumulado += max(item.final_score, 1e-6)
            if acumulado >= threshold:
                selected_ids.append(item.poi_id)
                pool.pop(idx)
                break

    return selected_ids


def _random_unit_interval(seed: int | None, step: int, pool: list[_CandidateScore]) -> float:
    if seed is None:
        return secrets.randbelow(2**53) / float(2**53)

    pool_signature = ','.join(str(item.poi_id) for item in pool)
    payload = f'{seed}:{step}:{pool_signature}'.encode('utf-8')
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], 'big') / float(2**64)


def _calcular_num_anclas_top(limite: int, disponibles: int) -> int:
    if limite <= 0 or disponibles <= 0:
        return 0
    if limite >= 9:
        objetivo = 3
    elif limite >= 5:
        objetivo = 2
    else:
        objetivo = 1
    return min(objetivo, limite, disponibles)


def seleccionar_pois_allowlist(
    *,
    ciudad: str,
    moods: list[str],
    limite: int,
    top_k_factor: int = 4,
    seed: int | None = None,
) -> list[dict]:
    from allowList.models import POI

    limite = max(1, int(limite))
    top_k_factor = max(1, int(top_k_factor))
    ciudad_limpia = str(ciudad or '').strip()
    if not ciudad_limpia:
        return []

    category_weights = _build_category_weights(moods)
    categorias_filtrables = set(category_weights.keys())

    def _serializar(poi) -> dict:
        return {
            'nombre': poi.nombre,
            'coords': [poi.lat, poi.lon],
            'categoria': poi.get_categoria_display(),
        }

    ciudad_norm = _normalizar_texto(ciudad_limpia)
    city_ids = [
        poi.id
        for poi in POI.objects.only('id', 'ciudad')
        if _normalizar_texto(poi.ciudad) == ciudad_norm
    ]
    city_scope_qs = POI.objects.filter(id__in=city_ids)
    base_qs = city_scope_qs
    if categorias_filtrables:
        base_qs = base_qs.filter(categoria__in=categorias_filtrables)

    boundary = _resolve_city_boundary(ciudad_limpia)
    if boundary is not None:
        strict_qs = base_qs.filter(coordenadas__intersects=boundary.polygon)
        city_relaxed_qs = city_scope_qs.filter(coordenadas__intersects=boundary.polygon)
    else:
        strict_qs = base_qs
        city_relaxed_qs = city_scope_qs

    # Fallback progresivo dentro de la misma ciudad: primero mood/categoría,
    # después cualquier categoría local. Nunca cae a POIs globales.
    candidates = list(
        strict_qs.only(
            'id',
            'nombre',
            'categoria',
            'ciudad',
            'coordenadas',
            'google_rank_position',
        )
    )
    source = 'strict'
    if not candidates:
        candidates = list(
            city_relaxed_qs.only(
                'id',
                'nombre',
                'categoria',
                'ciudad',
                'coordenadas',
                'google_rank_position',
            )
        )
        source = 'city_relaxed'

    if not candidates:
        return []

    weights = ALLOWLIST_SCORE_WEIGHTS

    scored: list[_CandidateScore] = []
    for poi in candidates:
        google_score = _google_relevance_score(poi.google_rank_position)
        mood_score = category_weights.get(poi.categoria, 0.1 if category_weights else 0.5)

        if source == 'strict':
            city_score = 1.0
        else:
            city_score = 0.8

        final_score = (
            float(weights.get('google_relevance', 0.7)) * google_score
            + float(weights.get('mood_affinity', 0.2)) * mood_score
            + float(weights.get('city_match', 0.1)) * city_score
        )
        scored.append(
            _CandidateScore(
                poi_id=poi.id,
                final_score=final_score,
                google_score=google_score,
                mood_score=mood_score,
                city_score=city_score,
            )
        )

    scored.sort(key=lambda item: item.final_score, reverse=True)
    top_k = min(len(scored), max(limite, limite * top_k_factor))
    selection_pool = scored[:top_k]

    num_anclas = _calcular_num_anclas_top(limite, len(selection_pool))
    anchor_ids = [item.poi_id for item in selection_pool[:num_anclas]]
    anchor_id_set = set(anchor_ids)
    random_pool = [item for item in selection_pool if item.poi_id not in anchor_id_set]
    random_ids = _weighted_sample_without_replacement(
        random_pool,
        limite - len(anchor_ids),
        seed,
    )
    chosen_ids = anchor_ids + random_ids

    by_id = {poi.id: poi for poi in candidates}
    selected = [by_id[poi_id] for poi_id in chosen_ids if poi_id in by_id]
    return [_serializar(poi) for poi in selected]
