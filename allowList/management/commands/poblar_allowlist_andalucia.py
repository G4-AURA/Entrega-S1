"""
allowList/management/commands/poblar_allowlist_andalucia.py

Pobla la allowlist de POIs con datos reales de las 8 capitales de provincia
andaluzas usando la Google Places API (New) v1.

Uso:
  python manage.py poblar_allowlist_andalucia
  python manage.py poblar_allowlist_andalucia --dry-run
  python manage.py poblar_allowlist_andalucia --ciudades "sevilla,granada" --limite 30

Requiere la variable de entorno GOOGLE_PLACES_API_KEY configurada.
"""

import logging
import time

import requests
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from allowList.models import CategoriaOSM, POI

logger = logging.getLogger(__name__)

PLACES_API_URL = 'https://places.googleapis.com/v1/places:searchText'
PLACES_FIELD_MASK = (
    'places.name,'
    'places.id,'
    'places.displayName,'
    'places.location,'
    'places.types,'
    'places.formattedAddress,'
    'places.primaryType'
)

CIUDADES_DEFAULT = [
    'Sevilla',
    'Málaga',
    'Granada',
    'Córdoba',
    'Cádiz',
    'Huelva',
    'Jaén',
    'Almería',
]

# (término de búsqueda en español, CategoriaOSM destino)
CONSULTAS_POR_CATEGORIA = [
    ('museos',                  CategoriaOSM.MUSEO),
    ('monumentos históricos',   CategoriaOSM.MONUMENTO),
    ('restaurantes',            CategoriaOSM.RESTAURANTE),
    ('cafeterías',              CategoriaOSM.CAFE),
    ('bares',                   CategoriaOSM.BAR),
    ('iglesias y catedrales',   CategoriaOSM.IGLESIA),
    ('parques',                 CategoriaOSM.PARQUE),
    ('teatros',                 CategoriaOSM.TEATRO),
    ('galerías de arte',        CategoriaOSM.GALERIA_ARTE),
    ('miradores',               CategoriaOSM.MIRADOR),
    ('castillos y fortalezas',  CategoriaOSM.CASTILLO),
    ('ruinas arqueológicas',    CategoriaOSM.RUINAS),
    ('mercados',                CategoriaOSM.MERCADO),
    ('plazas principales',      CategoriaOSM.PLAZA),
]

# Mapeo de primaryType de Google → CategoriaOSM (afinación fina si la API devuelve tipo)
GOOGLE_TYPE_TO_CATEGORIA: dict[str, str] = {
    'museum':                    CategoriaOSM.MUSEO,
    'art_gallery':               CategoriaOSM.GALERIA_ARTE,
    'tourist_attraction':        CategoriaOSM.MONUMENTO,
    'monument':                  CategoriaOSM.MONUMENTO,
    'historical_landmark':       CategoriaOSM.MONUMENTO,
    'restaurant':                CategoriaOSM.RESTAURANTE,
    'cafe':                      CategoriaOSM.CAFE,
    'coffee_shop':               CategoriaOSM.CAFE,
    'bar':                       CategoriaOSM.BAR,
    'church':                    CategoriaOSM.IGLESIA,
    'cathedral':                 CategoriaOSM.IGLESIA,
    'mosque':                    CategoriaOSM.IGLESIA,
    'place_of_worship':          CategoriaOSM.IGLESIA,
    'park':                      CategoriaOSM.PARQUE,
    'national_park':             CategoriaOSM.PARQUE,
    'garden':                    CategoriaOSM.PARQUE,
    'performing_arts_theater':   CategoriaOSM.TEATRO,
    'theater':                   CategoriaOSM.TEATRO,
    'library':                   CategoriaOSM.BIBLIOTECA,
    'hotel':                     CategoriaOSM.HOTEL,
    'observation_deck':          CategoriaOSM.MIRADOR,
    'viewpoint':                 CategoriaOSM.MIRADOR,
    'castle':                    CategoriaOSM.CASTILLO,
    'fort':                      CategoriaOSM.CASTILLO,
    'ruins':                     CategoriaOSM.RUINAS,
    'archaeological_site':       CategoriaOSM.RUINAS,
    'market':                    CategoriaOSM.MERCADO,
    'food_market':               CategoriaOSM.MERCADO,
    'plaza':                     CategoriaOSM.PLAZA,
    'town_square':               CategoriaOSM.PLAZA,
    'movie_theater':             CategoriaOSM.CINE,
    'stadium':                   CategoriaOSM.ESTADIO,
    'sports_complex':            CategoriaOSM.ESTADIO,
}


def _buscar_places(query: str, api_key: str, max_resultados: int) -> list[dict]:
    """
    Ejecuta una búsqueda de texto en la Places API v1 y devuelve la lista cruda.
    """
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': api_key,
        'X-Goog-FieldMask': PLACES_FIELD_MASK,
    }
    body = {
        'textQuery': query,
        'languageCode': 'es',
        'rankPreference': 'RELEVANCE',
        'maxResultCount': min(max_resultados, 20),  # Places API (New) máx 20 por llamada
    }
    try:
        response = requests.post(PLACES_API_URL, json=body, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json().get('places', [])
    except requests.Timeout:
        logger.warning('Timeout en búsqueda: "%s"', query)
        return []
    except requests.HTTPError as exc:
        logger.warning('Error HTTP %s en búsqueda: "%s" — %s', exc.response.status_code, query, exc.response.text[:200])
        return []
    except requests.RequestException as exc:
        logger.warning('Error de red en búsqueda: "%s" — %s', query, exc)
        return []


def _inferir_categoria(place: dict, categoria_consulta: str) -> str:
    """
    Determina la CategoriaOSM del POI a partir del primaryType de Google.
    Si no hay match conocido, usa la categoría de la consulta (más fiable).
    """
    primary_type = place.get('primaryType', '')
    return GOOGLE_TYPE_TO_CATEGORIA.get(primary_type, categoria_consulta)


def _procesar_place(place: dict, ciudad: str, categoria_consulta: str) -> dict | None:
    """
    Extrae y normaliza los campos necesarios de un resultado de Places API.
    Devuelve None si faltan datos esenciales.
    """
    display_name = place.get('displayName', {})
    nombre = display_name.get('text', '').strip()
    if not nombre:
        return None

    location = place.get('location', {})
    lat = location.get('latitude')
    lon = location.get('longitude')
    if lat is None or lon is None:
        return None

    direccion = place.get('formattedAddress', '').strip()
    categoria = _inferir_categoria(place, categoria_consulta)
    place_name = str(place.get('name') or '').strip()
    place_id = str(place.get('id') or '').strip()
    google_place_id = place_id or (place_name.split('/', 1)[1] if place_name.startswith('places/') else place_name)

    return {
        'nombre': nombre,
        'lat': float(lat),
        'lon': float(lon),
        'ciudad': ciudad,
        'direccion': direccion,
        'categoria': categoria,
        'google_place_id': google_place_id,
    }


class Command(BaseCommand):
    help = 'Pobla la allowlist con POIs de Google Places para las capitales andaluzas.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ciudades',
            type=str,
            default='',
            help='Lista separada por comas de ciudades a procesar (default: 8 capitales andaluzas).',
        )
        parser.add_argument(
            '--limite',
            type=int,
            default=20,
            help='Número máximo de POIs a recuperar por búsqueda (default: 20, máx: 20).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra lo que se haría sin escribir en la base de datos.',
        )
        parser.add_argument(
            '--pausa',
            type=float,
            default=0.3,
            help='Segundos de pausa entre llamadas a la API (default: 0.3).',
        )

    def handle(self, *args, **options):
        api_key = getattr(settings, 'GOOGLE_PLACES_API_KEY', None) or ''
        if not api_key:
            raise CommandError(
                'GOOGLE_PLACES_API_KEY no está configurada. '
                'Añádela a tu .env como GOOGLE_PLACES_API_KEY=tu_clave.'
            )

        dry_run = options['dry_run']
        limite = max(1, min(options['limite'], 20))
        pausa = max(0.0, options['pausa'])

        if options['ciudades']:
            ciudades = [c.strip() for c in options['ciudades'].split(',') if c.strip()]
        else:
            ciudades = CIUDADES_DEFAULT

        if dry_run:
            self.stdout.write(self.style.WARNING('── MODO DRY-RUN: no se escribirá en la base de datos ──'))

        self.stdout.write(f'Ciudades a procesar: {", ".join(ciudades)}')
        self.stdout.write(f'Categorías por ciudad: {len(CONSULTAS_POR_CATEGORIA)}')
        self.stdout.write(f'Límite por búsqueda: {limite}')
        self.stdout.write('')

        total_creados = total_existian = total_errores = 0

        for ciudad in ciudades:
            self.stdout.write(self.style.MIGRATE_HEADING(f'>> {ciudad}'))
            ciudad_creados = ciudad_existian = ciudad_errores = 0

            for termino, categoria in CONSULTAS_POR_CATEGORIA:
                query = f'{termino} en {ciudad}, España'
                places = _buscar_places(query, api_key, limite)

                for rank_position, place in enumerate(places, start=1):
                    datos = _procesar_place(place, ciudad, categoria)
                    if datos is None:
                        ciudad_errores += 1
                        continue
                    datos['google_rank_position'] = rank_position
                    datos['google_search_query'] = query

                    if dry_run:
                        self.stdout.write(
                            f'  [dry-run] #{rank_position} {datos["nombre"]} ({datos["categoria"]}) — {datos["lat"]:.4f},{datos["lon"]:.4f}'
                        )
                        ciudad_creados += 1
                        continue

                    try:
                        with transaction.atomic():
                            poi, fue_creado = POI.objects.get_or_create(
                                nombre=datos['nombre'],
                                ciudad=ciudad,
                                defaults={
                                    'categoria':   datos['categoria'],
                                    'coordenadas': Point(datos['lon'], datos['lat'], srid=4326),
                                    'direccion':   datos['direccion'],
                                    'fuente':      POI.Fuente.GOOGLE,
                                    'google_place_id': datos['google_place_id'],
                                    'google_rank_position': datos['google_rank_position'],
                                    'google_search_query': datos['google_search_query'],
                                    'google_last_seen_at': timezone.now(),
                                },
                            )
                            if not fue_creado and poi.fuente == POI.Fuente.GOOGLE:
                                cambios = []
                                if datos['google_place_id'] and poi.google_place_id != datos['google_place_id']:
                                    poi.google_place_id = datos['google_place_id']
                                    cambios.append('google_place_id')
                                nuevo_rank = datos.get('google_rank_position')
                                if nuevo_rank and (
                                    poi.google_rank_position is None or int(nuevo_rank) < int(poi.google_rank_position)
                                ):
                                    poi.google_rank_position = int(nuevo_rank)
                                    cambios.append('google_rank_position')
                                if poi.google_search_query != datos['google_search_query']:
                                    poi.google_search_query = datos['google_search_query']
                                    cambios.append('google_search_query')
                                poi.google_last_seen_at = timezone.now()
                                cambios.append('google_last_seen_at')
                                if poi.categoria != datos['categoria']:
                                    poi.categoria = datos['categoria']
                                    cambios.append('categoria')
                                if cambios:
                                    poi.save(update_fields=sorted(set(cambios)))
                        if fue_creado:
                            ciudad_creados += 1
                        else:
                            ciudad_existian += 1
                    except Exception as exc:
                        logger.warning('Error al guardar POI "%s" en %s: %s', datos['nombre'], ciudad, exc)
                        ciudad_errores += 1

                if pausa > 0:
                    time.sleep(pausa)

            self.stdout.write(
                f'  Creados: {ciudad_creados} | Ya existían: {ciudad_existian} | Errores: {ciudad_errores}'
            )
            total_creados += ciudad_creados
            total_existian += ciudad_existian
            total_errores += ciudad_errores

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Completado — Creados: {total_creados} | Ya existían: {total_existian} | Errores: {total_errores}'
        ))
