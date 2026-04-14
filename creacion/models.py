from django.db import models

class Historial_ia(models.Model):
    id = models.AutoField(primary_key=True)
    prompt = models.TextField(blank=False, null=False)
    respuesta = models.JSONField(blank=False, null=False)
    momento = models.DateTimeField(auto_now_add=True)

    '''
    guia = models.ForeignKey(Guia, on_delete=models.CASCADE)
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE)
    '''

    # Telemetría y Seguimiento
    duracion_generacion = models.FloatField(null=True, blank=True)
    duracion_validacion = models.FloatField(null=True, blank=True)
    duracion_scoring = models.FloatField(null=True, blank=True)
    duracion_optimizacion = models.FloatField(null=True, blank=True)
    duracion_total = models.FloatField(null=True, blank=True)
    
    # Estado de la tarea asíncrona
    estado_tarea = models.CharField(max_length=20, default='pendiente') # pendiente, en_progreso, completado, error
    etapa_actual = models.CharField(max_length=50, default='pendiente')
    mensaje_error = models.TextField(null=True, blank=True)
    sesion_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Ruta IA {self.id} - {self.momento} ({self.estado_tarea})"

