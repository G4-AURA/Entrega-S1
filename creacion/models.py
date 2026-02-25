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

    def __str__(self):
        return str(self.momento)

