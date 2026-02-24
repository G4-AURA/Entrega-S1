from django.db import models
from django.contrib.auth.models import User
from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.fields import ArrayField

class AUTH_USER(models.Model):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)

    def __str__(self):
        return self.username

class GUIA(models.Model):
    class Suscripcion(models.TextChoices):
        FREEMIUM = 'Freemium', 'Freemium'
        PREMIUM = 'Premium', 'Premium'
    tipo_suscripcion = models.CharField(max_length=50, choices=Suscripcion.choices, default=Suscripcion.FREEMIUM)

    def __str__(self):
        return self.tipo_suscripcion

class RUTA(models.Model):
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    duracion_horas = models.FloatField()
    num_personas = models.IntegerField()
    class Exigencia(models.TextChoices):
        BAJA = 'Baja', 'Baja'
        MEDIA = 'Media', 'Media'
        ALTA = 'Alta', 'Alta'
    nivel_exigencia = models.CharField(max_length=50, choices=Exigencia.choices, default=Exigencia.MEDIA)
    class Mood(models.TextChoices):
        HISTORIA = 'Historia', 'Historia'
        GASTRONOMIA = 'Gastronomía', 'Gastronomía'
        NATURALEZA = 'Naturaleza', 'Naturaleza'
        MISTERIO_Y_LEYENDAS = 'Misterio y Leyendas', 'Misterio y Leyendas'
        LOCAL = 'Local', 'Local'
        CINE_Y_SERIES = 'Cine y Series', 'Cine y Series'
        RELIGIOSO_Y_ESPIRITUAL = 'Religioso y Espiritual', 'Religioso y Espiritual'
        ARQUITECTURA_Y_DISEÑO = 'Arquitectura y Diseño', 'Arquitectura y Diseño'
        OCIO_CULTURAL = 'Ocio/Cultural', 'Ocio/Cultural'
    mood = ArrayField(
        models.CharField(max_length=20, choices=Mood.choices),
        default=list
    )
    es_generada_ia = models.BooleanField(default=False)
    guia = models.ForeignKey(GUIA, on_delete=models.CASCADE)


    def __str__(self):
        return self.titulo

class PARADA(models.Model):
    orden = models.IntegerField()
    nombre = models.CharField(max_length=255)
    coordenadas = gis_models.PointField()
    ruta = models.ForeignKey(RUTA, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.nombre} (Orden: {self.orden})"