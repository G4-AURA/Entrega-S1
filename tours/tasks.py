from celery import shared_task
from .models import MENSAJE_CHAT

@shared_task
def barrido_mensajes_efimeros(sesion_id):
    """
    Tarea de Celery: Elimina permanentemente todos los mensajes asociados 
    a una sesión de tour específica una vez que ha finalizado.
    """
    # Filtramos por el ID de la sesión y ejecutamos el borrado masivo
    cantidad, _ = MENSAJE_CHAT.objects.filter(sesion_tour_id=sesion_id).delete()
    
    return f"Limpieza completada: {cantidad} mensajes eliminados para la sesión {sesion_id}."