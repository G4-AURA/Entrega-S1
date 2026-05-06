"""
Configuración desacoplada de afinidad mood -> categorías de allowlist.

Cada mood tiene pesos [0.0, 1.0] por categoría OSM.
"""

from __future__ import annotations


MOOD_CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
    'historia': {
        'historic=monument': 1.0,
        'historic=castle': 0.95,
        'historic=ruins': 0.9,
        'tourism=museum': 0.85,
        'amenity=place_of_worship': 0.8,
        'place=square': 0.6,
    },
    'gastronomia': {
        'amenity=restaurant': 1.0,
        'amenity=cafe': 0.9,
        'amenity=bar': 0.85,
        'amenity=marketplace': 0.8,
        'place=square': 0.45,
    },
    'naturaleza': {
        'leisure=park': 1.0,
        'tourism=viewpoint': 0.85,
        'place=square': 0.35,
    },
    'misterio y leyendas': {
        'historic=ruins': 1.0,
        'historic=castle': 0.95,
        'historic=monument': 0.9,
        'amenity=place_of_worship': 0.8,
    },
    'local': {
        'place=square': 1.0,
        'amenity=marketplace': 0.95,
        'amenity=cafe': 0.7,
        'amenity=restaurant': 0.7,
        'tourism=museum': 0.45,
    },
    'cine y series': {
        'amenity=cinema': 1.0,
        'tourism=museum': 0.65,
        'historic=monument': 0.55,
    },
    'religioso y espiritual': {
        'amenity=place_of_worship': 1.0,
        'historic=monument': 0.75,
        'historic=castle': 0.4,
    },
    'arquitectura y diseño': {
        'historic=monument': 1.0,
        'tourism=museum': 0.8,
        'tourism=gallery': 0.75,
        'historic=castle': 0.7,
        'amenity=theatre': 0.35,
    },
    'ocio/cultural': {
        'amenity=theatre': 1.0,
        'tourism=gallery': 0.9,
        'tourism=museum': 0.8,
        'amenity=cinema': 0.7,
        'amenity=library': 0.6,
    },
}

MOOD_ALIASES: dict[str, str] = {
    'misterio-leyendas': 'misterio y leyendas',
    'cine-series': 'cine y series',
    'religioso-espiritual': 'religioso y espiritual',
    'arquitectura-diseno': 'arquitectura y diseño',
    'ocio-cultural': 'ocio/cultural',
}


# Pesos del score final del selector allowlist.
ALLOWLIST_SCORE_WEIGHTS: dict[str, float] = {
    'google_relevance': 0.7,
    'mood_affinity': 0.2,
    'city_match': 0.1,
}

