import uuid
from django.db import models
from django.contrib.auth.models import User
from django.contrib.gis.db import models as gis_models
from django.conf import settings
from rutas.models import Ruta


class TURISTA(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
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
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    fecha_inicio = models.DateTimeField()
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name='sesiones')
    turistas = models.ManyToManyField(TURISTA, through='TURISTASESION', blank=True)
    parada_actual = models.ForeignKey('rutas.Parada', on_delete=models.SET_NULL, null=True, blank=True, related_name='sesiones_actuales')

    def __str__(self):
        return f"{self.ruta.titulo} - {self.codigo_acceso}"
    


class TURISTASESION(models.Model):
    turista = models.ForeignKey(TURISTA, on_delete=models.CASCADE)
    sesion_tour = models.ForeignKey(SESION_TOUR, on_delete=models.CASCADE)
    fecha_union = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = ['turista', 'sesion_tour']

    def __str__(self):
        return f"{self.turista.alias} - {self.sesion_tour.codigo_acceso}"


class UBICACION_VIVO(models.Model):
    coordenadas = gis_models.PointField(null=True, blank=True)
    timestamp = models.DateTimeField()
    sesion_tour = models.ForeignKey(SESION_TOUR, on_delete=models.CASCADE)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.usuario.username} - {self.timestamp}"


class MENSAJE_CHAT(models.Model):
    sesion_tour = models.ForeignKey(SESION_TOUR, on_delete=models.CASCADE, related_name='mensajes')
    remitente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    texto = models.TextField()
    momento = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        fecha = self.momento.strftime('%H:%M') if self.momento else "S/F"
        return f"[{fecha}] {self.remitente}: {self.texto[:20]}"