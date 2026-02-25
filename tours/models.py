from django.db import models
from django.contrib.auth.models import User
from django.contrib.gis.db import models as gis_models
from rutas.models import Ruta


class TURISTA(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    alias = models.CharField(max_length=255)

    def __str__(self):
        return self.alias


class SESION_TOUR(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('en_curso', 'En Curso'),
        ('finalizado', 'Finalizado'),
    ]

    codigo_acceso = models.CharField(max_length=50, unique=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    fecha_inicio = models.DateTimeField()
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name='sesiones')
    turistas = models.ManyToManyField(TURISTA, blank=True)

    def __str__(self):
        return f"{self.ruta.titulo} - {self.codigo_acceso}"
    


class UBICACION_VIVO(models.Model):
    coordenadas = gis_models.PointField(null=True, blank=True)
    timestamp = models.DateTimeField()
    sesion_tour = models.ForeignKey(SESION_TOUR, on_delete=models.CASCADE)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.usuario.username} - {self.timestamp}"
