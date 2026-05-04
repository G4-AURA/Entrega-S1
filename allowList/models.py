"""
allowlist/models.py

Modelo para la base de datos de lugares autorizados (Allowlist de POIs).
Actúa como fuente de verdad para el motor generador de rutas.
"""
from django.contrib.gis.db import models as gis_models
from django.db import models


class CategoriaOSM(models.TextChoices):
    """Categorías predefinidas mapeadas a etiquetas OSM para el buscador asistido."""
    MUSEO           = 'tourism=museum',          'Museo'
    MONUMENTO       = 'historic=monument',       'Monumento'
    RESTAURANTE     = 'amenity=restaurant',      'Restaurante'
    CAFE            = 'amenity=cafe',            'Café'
    BAR             = 'amenity=bar',             'Bar'
    IGLESIA         = 'amenity=place_of_worship','Lugar de culto'
    PARQUE          = 'leisure=park',            'Parque'
    TEATRO          = 'amenity=theatre',         'Teatro'
    BIBLIOTECA      = 'amenity=library',         'Biblioteca'
    GALERIA_ARTE    = 'tourism=gallery',         'Galería de arte'
    HOTEL           = 'tourism=hotel',           'Hotel'
    MIRADOR         = 'tourism=viewpoint',       'Mirador'
    CASTILLO        = 'historic=castle',         'Castillo'
    RUINAS          = 'historic=ruins',          'Ruinas'
    MERCADO         = 'amenity=marketplace',     'Mercado'
    PLAZA           = 'place=square',            'Plaza'
    CINE            = 'amenity=cinema',          'Cine'
    ESTADIO         = 'leisure=stadium',         'Estadio'
    OTRO            = 'other',                   'Otro'


class POI(models.Model):
    """
    Punto de Interés curado y autorizado para ser usado en rutas generadas.

    Puede originarse de dos formas:
      - fuente='osm': importado desde OpenStreetMap vía Overpass API
      - fuente='manual': creado directamente por un administrador
    """

    class Fuente(models.TextChoices):
        OSM    = 'osm',    'OpenStreetMap'
        MANUAL = 'manual', 'Manual'
        GOOGLE = 'google', 'Google Places'

    # ── Identificación ────────────────────────────────────────────────────────
    nombre     = models.CharField(max_length=255, db_index=True)
    categoria  = models.CharField(
        max_length=60,
        choices=CategoriaOSM.choices,
        default=CategoriaOSM.OTRO,
        db_index=True,
    )

    # ── Geolocalización ───────────────────────────────────────────────────────
    coordenadas = gis_models.PointField(srid=4326)
    ciudad      = models.CharField(max_length=120, blank=True, db_index=True)
    direccion   = models.CharField(max_length=255, blank=True)

    # ── Metadatos de origen ───────────────────────────────────────────────────
    fuente       = models.CharField(max_length=10, choices=Fuente.choices, default=Fuente.MANUAL)
    osm_id       = models.BigIntegerField(null=True, blank=True, unique=True,
                                          help_text='ID del elemento en OpenStreetMap (nulo para entradas manuales).')
    osm_type     = models.CharField(max_length=10, blank=True,
                                    help_text='Tipo OSM: node, way o relation.')

    # ── Señales de ranking Google Places SearchText (rankPreference=RELEVANCE) ──
    google_place_id = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        help_text='ID de lugar devuelto por Google Places v1 (places/{id}).',
    )
    google_rank_position = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Posición de ranking devuelta por Google SearchText (1 = más relevante).',
    )
    google_search_query = models.CharField(
        max_length=255,
        blank=True,
        help_text='Consulta de SearchText utilizada para descubrir el POI.',
    )
    google_last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Última fecha en la que el POI apareció en SearchText.',
    )


    class Meta:
        verbose_name      = 'POI (Allowlist)'
        verbose_name_plural = 'POIs (Allowlist)'
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['ciudad', 'categoria']),
            models.Index(fields=['ciudad', 'google_rank_position']),
        ]

    def __str__(self):
        return f"{self.nombre} [{self.get_categoria_display()}] – {self.ciudad or 'sin ciudad'}"

    @property
    def lat(self) -> float:
        return self.coordenadas.y

    @property
    def lon(self) -> float:
        return self.coordenadas.x


class CityBoundary(models.Model):
    """
    Polígono oficial de una ciudad para filtrar POIs dentro de su límite urbano.
    """

    city_name = models.CharField(max_length=120, unique=True)
    polygon = gis_models.MultiPolygonField(srid=4326)
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Límite oficial de ciudad'
        verbose_name_plural = 'Límites oficiales de ciudades'
        ordering = ['city_name']

    def __str__(self):
        return self.city_name
