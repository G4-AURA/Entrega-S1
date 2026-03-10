"""
rutas/models.py

Modelos de dominio de la aplicación de rutas turísticas.

S2.1-29 / S2.1-30: Se añaden campos de geometría y métricas a Ruta y Parada
para almacenar el resultado calculado por GraphHopper.
"""
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator


class AuthUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='auth_profile')

    def __str__(self):
        return self.user.username


class Guia(models.Model):
    class Suscripcion(models.TextChoices):
        FREEMIUM = 'Freemium', 'Freemium'
        PREMIUM  = 'Premium',  'Premium'

    tipo_suscripcion = models.CharField(
        max_length=50, choices=Suscripcion.choices, default=Suscripcion.FREEMIUM
    )
    user = models.OneToOneField(
        AuthUser, on_delete=models.CASCADE, related_name='guia', null=True, blank=True
    )

    def __str__(self):
        return f"{self.user.user.username} ({self.tipo_suscripcion})"


class Ruta(models.Model):
    titulo       = models.CharField(max_length=255)
    descripcion  = models.TextField(blank=True)
    duracion_horas = models.FloatField()
    num_personas   = models.PositiveIntegerField()

    class Exigencia(models.TextChoices):
        BAJA  = 'Baja',  'Baja'
        MEDIA = 'Media', 'Media'
        ALTA  = 'Alta',  'Alta'

    nivel_exigencia = models.CharField(
        max_length=50, choices=Exigencia.choices, default=Exigencia.MEDIA
    )

    class Mood(models.TextChoices):
        HISTORIA              = 'Historia',              'Historia'
        GASTRONOMIA           = 'Gastronomía',           'Gastronomía'
        NATURALEZA            = 'Naturaleza',            'Naturaleza'
        MISTERIO_Y_LEYENDAS   = 'Misterio y Leyendas',  'Misterio y Leyendas'
        LOCAL                 = 'Local',                 'Local'
        CINE_Y_SERIES         = 'Cine y Series',         'Cine y Series'
        RELIGIOSO_Y_ESPIRITUAL= 'Religioso y Espiritual','Religioso y Espiritual'
        ARQUITECTURA_Y_DISEÑO = 'Arquitectura y Diseño', 'Arquitectura y Diseño'
        OCIO_CULTURAL         = 'Ocio/Cultural',         'Ocio/Cultural'

    mood = ArrayField(
        models.CharField(max_length=25, choices=Mood.choices),
        default=list,
    )
    es_generada_ia = models.BooleanField(default=False)
    guia = models.ForeignKey(Guia, on_delete=models.CASCADE, related_name='rutas')

    # ── S2.1-30: Geometría de la ruta calculada por GraphHopper ──────────────
    # Almacenada como LineString PostGIS para evitar recalcular en cada petición.
    # null=True porque no existe hasta que haya ≥2 paradas con coordenadas.
    geometria_ruta = gis_models.LineStringField(
        null=True, blank=True, srid=4326,
        help_text="Trazado real sobre la red viaria calculado por GraphHopper.",
    )

    # ── S2.1-29: Métricas totales de la ruta ─────────────────────────────────
    distancia_total_m = models.FloatField(
        null=True, blank=True,
        help_text="Distancia total de la ruta en metros (GraphHopper).",
    )
    duracion_total_s = models.IntegerField(
        null=True, blank=True,
        help_text="Duración total estimada de la ruta en segundos (GraphHopper).",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(duracion_horas__gte=0.0),
                name='duracion_horas_positiva',
            )
        ]

    def __str__(self):
        return self.titulo

    # ── Propiedades de conveniencia para vistas y plantillas ─────────────────

    @property
    def distancia_total_km(self) -> str | None:
        """Distancia total en km con 1 decimal, lista para mostrar."""
        if self.distancia_total_m is None:
            return None
        return f"{self.distancia_total_m / 1000:.1f}"

    @property
    def duracion_total_min(self) -> int | None:
        """Duración total redondeada en minutos."""
        if self.duracion_total_s is None:
            return None
        return round(self.duracion_total_s / 60)

    @property
    def geometria_ruta_coords(self) -> list[list[float]] | None:
        """
        Coordenadas en formato Leaflet [[lat, lon], ...].
        GEOS almacena (x=lon, y=lat); Leaflet espera (lat, lon), por eso invertimos.
        """
        if not self.geometria_ruta:
            return None
        return [[y, x] for x, y in self.geometria_ruta.coords]


class Parada(models.Model):
    orden       = models.PositiveIntegerField()
    nombre      = models.CharField(max_length=255)
    coordenadas = gis_models.PointField()
    ruta        = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name='paradas')

    # ── S2.1-29: Métricas del tramo desde esta parada hasta la siguiente ─────
    # La última parada de cada ruta tendrá siempre null en estos campos.
    distancia_siguiente_m = models.FloatField(
        null=True, blank=True,
        help_text="Metros desde esta parada hasta la siguiente (GraphHopper).",
    )
    duracion_siguiente_s = models.IntegerField(
        null=True, blank=True,
        help_text="Segundos estimados desde esta parada hasta la siguiente (GraphHopper).",
    )

    class Meta:
        ordering = ['orden']

    def __str__(self):
        return f"{self.nombre} (Orden: {self.orden})"

    @property
    def duracion_siguiente_min(self) -> int | None:
        if self.duracion_siguiente_s is None:
            return None
        return round(self.duracion_siguiente_s / 60)