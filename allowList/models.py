"""
allowlist/models.py

Modelo para la base de datos de lugares autorizados (Allowlist de POIs).
Actúa como fuente de verdad para el motor generador de rutas.
"""
from django.contrib.auth.models import User
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils import timezone


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


    class Meta:
        verbose_name      = 'POI (Allowlist)'
        verbose_name_plural = 'POIs (Allowlist)'
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['ciudad', 'categoria']),
        ]

    def __str__(self):
        return f"{self.nombre} [{self.get_categoria_display()}] – {self.ciudad or 'sin ciudad'}"

    @property
    def lat(self) -> float:
        return self.coordenadas.y

    @property
    def lon(self) -> float:
        return self.coordenadas.x
