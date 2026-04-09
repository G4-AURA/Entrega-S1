from django.db import models

class Historial_ia(models.Model):
    id = models.AutoField(primary_key=True)
    prompt = models.TextField(blank=False, null=False)
    respuesta = models.JSONField(blank=True, null=True)
    momento = models.DateTimeField(auto_now_add=True)
    sesion_generacion_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)

    # Tracking de estado y errores
    estado_tarea = models.CharField(max_length=20, default='procesando')
    etapa_actual = models.CharField(max_length=50, default='pendiente')
    timestamp_inicio_etapa = models.DateTimeField(null=True, blank=True)
    mensaje_error = models.TextField(null=True, blank=True)

    # Duraciones por etapa (en segundos)
    duracion_generacion = models.FloatField(null=True, blank=True)
    duracion_validacion = models.FloatField(null=True, blank=True)
    duracion_scoring = models.FloatField(null=True, blank=True)
    duracion_optimizacion = models.FloatField(null=True, blank=True)
    duracion_total = models.FloatField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"Generación {self.id} - {self.estado_tarea} ({self.momento})"

