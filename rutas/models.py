from django.db import models
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
        PREMIUM = 'Premium', 'Premium'
    tipo_suscripcion = models.CharField(max_length=50, choices=Suscripcion.choices, default=Suscripcion.FREEMIUM)

    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE, related_name='guia', null=True, blank=True,)

    def __str__(self):
        return f"{self.user.user.username} ({self.tipo_suscripcion})"

class Ruta(models.Model):
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    duracion_horas = models.FloatField(validators=[MinValueValidator(0.1)])
    num_personas = models.IntegerField(validators=[MinValueValidator(1)])
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
        models.CharField(max_length=25, choices=Mood.choices),
        default=list
    )
    es_generada_ia = models.BooleanField(default=False)
    guia = models.ForeignKey(Guia, on_delete=models.CASCADE, related_name='rutas')


    def __str__(self):
        return self.titulo

class Parada(models.Model):
    orden = models.IntegerField(validators=[MinValueValidator(1)])
    nombre = models.CharField(max_length=255)
    coordenadas = gis_models.PointField()
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name='paradas')
    
    class Meta:
        ordering = ['orden']
    
    def __str__(self):
        return f"{self.nombre} (Orden: {self.orden})"