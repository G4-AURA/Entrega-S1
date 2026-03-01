from celery import shared_task
from .models import MENSAJE_CHAT, SESION_TOUR

@shared_task
def barrido_mensajes_efimeros(sesion_id):
    """
    Tarea de Celery: Elimina permanentemente todos los mensajes asociados 
    a una sesión de tour específica SOLO si la sesión ha finalizado.
    """
    try:
        sesion = SESION_TOUR.objects.get(id=sesion_id)

        if sesion.estado != 'finalizado':
            return f"Operación cancelada: La sesión {sesion_id} aún está {sesion.estado}."
            
    except SESION_TOUR.DoesNotExist:
        return f"Error: No existe la sesión {sesion_id}."

    cantidad, _ = MENSAJE_CHAT.objects.filter(sesion_tour_id=sesion_id).delete()
    
    return f"Limpieza completada: {cantidad} mensajes eliminados para la sesión {sesion_id}."