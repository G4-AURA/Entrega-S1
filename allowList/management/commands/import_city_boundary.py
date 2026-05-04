"""
Importa/actualiza el polígono oficial de una ciudad desde un GeoJSON local.

Ejemplo:
  python manage.py import_city_boundary --ciudad "Sevilla" --geojson /ruta/sevilla.geojson
"""

import json
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError

from allowList.models import CityBoundary


class Command(BaseCommand):
    help = 'Importa un límite oficial de ciudad (MultiPolygon) desde un GeoJSON.'

    def add_arguments(self, parser):
        parser.add_argument('--ciudad', required=True, help='Nombre de la ciudad (ej. Sevilla).')
        parser.add_argument('--geojson', required=True, help='Ruta local al fichero GeoJSON.')
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Reemplaza el límite existente si ya hay uno para la ciudad.',
        )

    def handle(self, *args, **options):
        ciudad = str(options['ciudad'] or '').strip()
        geojson_path = Path(str(options['geojson'] or '').strip())
        replace = bool(options.get('replace'))

        if not ciudad:
            raise CommandError('Debes indicar --ciudad.')
        if not geojson_path.exists():
            raise CommandError(f'No existe el archivo GeoJSON: {geojson_path}')

        try:
            raw = json.loads(geojson_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f'No se pudo leer el GeoJSON: {exc}') from exc

        geometry = self._extract_geometry(raw)
        if geometry is None:
            raise CommandError('No se encontró ninguna geometría válida en el GeoJSON.')

        geos = GEOSGeometry(json.dumps(geometry), srid=4326)
        if geos.geom_type == 'Polygon':
            geos = MultiPolygon(geos, srid=4326)
        elif geos.geom_type != 'MultiPolygon':
            raise CommandError(
                f'La geometría debe ser Polygon/MultiPolygon y se recibió: {geos.geom_type}'
            )

        boundary_qs = CityBoundary.objects.filter(city_name=ciudad)
        if boundary_qs.exists() and not replace:
            raise CommandError(
                f'Ya existe límite para "{ciudad}". Usa --replace para sobreescribir.'
            )

        CityBoundary.objects.update_or_create(
            city_name=ciudad,
            defaults={'polygon': geos, 'active': True},
        )
        self.stdout.write(self.style.SUCCESS(f'Límite de ciudad importado: {ciudad}'))

    @staticmethod
    def _extract_geometry(raw: dict) -> dict | None:
        if not isinstance(raw, dict):
            return None

        geo_type = raw.get('type')
        if geo_type == 'FeatureCollection':
            features = raw.get('features') or []
            if not isinstance(features, list) or not features:
                return None
            first = features[0] if isinstance(features[0], dict) else {}
            geometry = first.get('geometry')
            if isinstance(geometry, dict):
                return geometry
            # Algunos ficheros no envuelven cada feature en {"type":"Feature","geometry":...}
            # y ponen directamente {"type":"MultiPolygon","coordinates":[...]}.
            if first.get('type') in {'Polygon', 'MultiPolygon'} and first.get('coordinates'):
                return first
            return None
        if geo_type == 'Feature':
            return raw.get('geometry')
        if geo_type in {'Polygon', 'MultiPolygon'}:
            return raw
        return None
