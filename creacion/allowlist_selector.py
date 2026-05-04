"""
Selector desacoplado de POIs para rutas IA.

Objetivos:
1) Priorizar el ranking nativo de Google SearchText (rankPreference=RELEVANCE).
2) Respetar coherencia mood -> categoría allowlist.
3) Filtrar por polígono oficial de ciudad cuando exista.
4) Introducir aleatoriedad controlada para evitar rutas clónicas.
"""

from __future__ import annotations

import random
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
    rng: random.Random,
) -> list[int]:
    pool = list(scored_items)
    selected_ids: list[int] = []
    remaining = min(sample_size, len(pool))

    for _ in range(remaining):
        total = sum(max(item.final_score, 1e-6) for item in pool)
        threshold = rng.random() * total
        acumulado = 0.0

        for idx, item in enumerate(pool):
            acumulado += max(item.final_score, 1e-6)
            if acumulado >= threshold:
                selected_ids.append(item.poi_id)
                pool.pop(idx)
                break

    return selected_ids


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
    category_weights = _build_category_weights(moods)
    categorias_filtrables = set(category_weights.keys())

    def _serializar(poi) -> dict:
        return {
            'nombre': poi.nombre,
            'coords': [poi.lat, poi.lon],
            'categoria': poi.get_categoria_display(),
        }

    base_qs = POI.objects.all()
    if categorias_filtrables:
        base_qs = base_qs.filter(categoria__in=categorias_filtrables)

    boundary = _resolve_city_boundary(ciudad_limpia)
    city_qs = base_qs
    if ciudad_limpia:
        city_qs = city_qs.filter(ciudad__icontains=ciudad_limpia)

    if boundary is not None:
        strict_qs = city_qs.filter(coordenadas__intersects=boundary.polygon)
    else:
        strict_qs = city_qs

    # Fallbacks progresivos manteniendo preferencia por ciudad.
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
            city_qs.only(
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
        candidates = list(
            base_qs.only(
                'id',
                'nombre',
                'categoria',
                'ciudad',
                'coordenadas',
                'google_rank_position',
            )
        )
        source = 'global_relaxed'

    if not candidates:
        return []

    weights = ALLOWLIST_SCORE_WEIGHTS
    rng = random.Random(seed)

    scored: list[_CandidateScore] = []
    ciudad_norm = _normalizar_texto(ciudad_limpia)
    for poi in candidates:
        google_score = _google_relevance_score(poi.google_rank_position)
        mood_score = category_weights.get(poi.categoria, 0.1 if category_weights else 0.5)

        if source == 'strict':
            city_score = 1.0
        elif source == 'city_relaxed':
            city_score = 0.8
        else:
            poi_city_norm = _normalizar_texto(poi.ciudad)
            city_score = 0.4 if ciudad_norm and poi_city_norm == ciudad_norm else 0.2

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
    chosen_ids = _weighted_sample_without_replacement(selection_pool, limite, rng)

    by_id = {poi.id: poi for poi in candidates}
    selected = [by_id[poi_id] for poi_id in chosen_ids if poi_id in by_id]
    return [_serializar(poi) for poi in selected]
