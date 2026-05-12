"""
Importa/actualiza límites oficiales de ciudad desde un GeoJSON local.

Ejemplos:
  python manage.py import_city_boundary --ciudad "Sevilla" --geojson /ruta/sevilla.geojson
  python manage.py import_city_boundary --geojson static/geojson/capitales_andalucia.geojson --replace
"""

import json
import unicodedata
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError

from allowList.models import CityBoundary


class Command(BaseCommand):
    help = 'Importa límites oficiales de ciudad (MultiPolygon) desde un GeoJSON.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ciudad',
            required=False,
            help='Nombre de la ciudad. Opcional si el GeoJSON trae properties.nombre por feature.',
        )
        parser.add_argument(
            '--geojson',
            required=False,
            help='Ruta local a un fichero GeoJSON concreto. Si se omite, se recorre la carpeta de GeoJSON.',
        )
        parser.add_argument(
            '--geojson-dir',
            required=False,
            help='Carpeta con ficheros GeoJSON. Default: static/geojson.',
        )
        parser.add_argument(
            '--pattern',
            default='*.geojson',
            help='Patrón de ficheros a importar dentro de --geojson-dir. Default: *.geojson.',
        )
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Reemplaza el límite existente si ya hay uno para la ciudad.',
        )

    def handle(self, *args, **options):
        ciudad = str(options['ciudad'] or '').strip()
        geojson_arg = str(options.get('geojson') or '').strip()
        geojson_dir_arg = str(options.get('geojson_dir') or '').strip()
        pattern = str(options.get('pattern') or '*.geojson').strip() or '*.geojson'
        replace = bool(options.get('replace'))

        geojson_paths = self._resolve_geojson_paths(
            geojson_arg=geojson_arg,
            geojson_dir_arg=geojson_dir_arg,
            pattern=pattern,
        )

        imported = 0
        skipped = 0
        files_without_boundaries = 0

        for geojson_path in geojson_paths:
            try:
                raw = json.loads(geojson_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                raise CommandError(f'No se pudo leer el GeoJSON {geojson_path}: {exc}') from exc

            boundaries = self._extract_boundaries(raw, ciudad=ciudad)
            if not boundaries and not ciudad:
                inferred_city = self._city_name_from_path(geojson_path)
                boundaries = self._extract_boundaries(raw, ciudad=inferred_city)

            if not boundaries:
                files_without_boundaries += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'No se encontró ninguna ciudad importable en {geojson_path}. '
                        'Usa properties.nombre por feature o un nombre de fichero de ciudad.'
                    )
                )
                continue

            self.stdout.write(self.style.MIGRATE_HEADING(f'>> {geojson_path}'))
            for city_name, geometry in boundaries:
                geos = self._geometry_to_multipolygon(geometry, city_name=city_name)
                boundary_qs = CityBoundary.objects.filter(city_name=city_name)
                if boundary_qs.exists() and not replace:
                    skipped += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'Ya existe límite para "{city_name}". Omitido; usa --replace para sobreescribir.'
                        )
                    )
                    continue

                CityBoundary.objects.update_or_create(
                    city_name=city_name,
                    defaults={'polygon': geos, 'active': True},
                )
                imported += 1
                self.stdout.write(self.style.SUCCESS(f'Límite de ciudad importado: {city_name}'))

        if imported == 0 and skipped == 0:
            raise CommandError(
                'No se importó ningún límite. Revisa que la carpeta contenga GeoJSON con geometrías '
                'Polygon/MultiPolygon y nombre de ciudad.'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Importación finalizada. Archivos: {len(geojson_paths)}. '
                f'Importados: {imported}. Omitidos: {skipped}. Sin ciudades: {files_without_boundaries}.'
            )
        )

    @staticmethod
    def _resolve_geojson_paths(*, geojson_arg: str, geojson_dir_arg: str, pattern: str) -> list[Path]:
        if geojson_arg:
            geojson_path = Path(geojson_arg)
            if not geojson_path.exists():
                raise CommandError(f'No existe el archivo GeoJSON: {geojson_path}')
            if not geojson_path.is_file():
                raise CommandError(f'La ruta indicada no es un fichero GeoJSON: {geojson_path}')
            return [geojson_path]

        geojson_dir = Path(geojson_dir_arg) if geojson_dir_arg else Path(settings.BASE_DIR) / 'static' / 'geojson'
        if not geojson_dir.exists():
            raise CommandError(f'No existe la carpeta de GeoJSON: {geojson_dir}')
        if not geojson_dir.is_dir():
            raise CommandError(f'La ruta indicada no es una carpeta: {geojson_dir}')

        paths = sorted(path for path in geojson_dir.glob(pattern) if path.is_file())
        if not paths:
            raise CommandError(f'No se encontraron ficheros GeoJSON en {geojson_dir} con patrón {pattern}.')
        return paths

    @classmethod
    def _extract_boundaries(cls, raw: dict, ciudad: str = '') -> list[tuple[str, dict]]:
        if not isinstance(raw, dict):
            return []

        geo_type = raw.get('type')
        if geo_type == 'FeatureCollection':
            registros = []
            features = [feature for feature in (raw.get('features') or []) if isinstance(feature, dict)]
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                feature_city_name = cls._extract_city_name(feature)
                if (
                    ciudad
                    and feature_city_name
                    and cls._normalize_city_name(feature_city_name) != cls._normalize_city_name(ciudad)
                ):
                    continue
                if ciudad:
                    if not feature_city_name and len(features) > 1:
                        continue
                    city_name = feature_city_name or ciudad
                else:
                    city_name = feature_city_name
                    if not city_name:
                        continue
                geometry = cls._extract_geometry(feature)
                if geometry is not None:
                    registros.append((city_name, geometry))
            return registros

        geometry = cls._extract_geometry(raw)
        if geometry is None or not ciudad:
            return []
        return [(ciudad, geometry)]

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

    @staticmethod
    def _extract_city_name(feature: dict) -> str:
        properties = feature.get('properties') or {}
        if not isinstance(properties, dict):
            return ''
        for key in (
            'nombre',
            'ciudad',
            'city_name',
            'name',
            'municipio',
            'NOMBRE',
            'Nombre',
            'NOM_MUN',
        ):
            value = str(properties.get(key) or '').strip()
            if value:
                return value
        return ''

    @staticmethod
    def _normalize_city_name(value: str) -> str:
        base = ' '.join(str(value or '').strip().casefold().split())
        normalized = unicodedata.normalize('NFD', base)
        return ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')

    @staticmethod
    def _city_name_from_path(path: Path) -> str:
        return ' '.join(path.stem.replace('-', ' ').replace('_', ' ').split()).title()

    @staticmethod
    def _geometry_to_multipolygon(geometry: dict, *, city_name: str):
        geos = GEOSGeometry(json.dumps(geometry), srid=4326)
        if geos.geom_type == 'Polygon':
            return MultiPolygon(geos, srid=4326)
        if geos.geom_type == 'MultiPolygon':
            return geos
        raise CommandError(
            f'La geometría de "{city_name}" debe ser Polygon/MultiPolygon y se recibió: {geos.geom_type}'
        )
