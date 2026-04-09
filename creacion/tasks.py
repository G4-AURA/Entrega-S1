import logging
from celery import shared_task
from django.utils import timezone
from creacion.models import Historial_ia
from creacion.services import consultar_langgraph

logger = logging.getLogger(__name__)

@shared_task
def tarea_generar_ruta_ia(historial_id, payload):
    t_inicio_total = timezone.now()
    try:
        logger.info("Iniciando tarea Celery para Historial_ia ID: %s", historial_id)
        
        # Ejecutar el pipeline (pasamos historial_id para que el decorador funcione)
        resultado_ruta = consultar_langgraph(payload, historial_id=historial_id)
        
        t_fin_total = timezone.now()
        duracion_total = (t_fin_total - t_inicio_total).total_seconds()

        # Actualizar con éxito
        Historial_ia.objects.filter(id=historial_id).update(
            respuesta=resultado_ruta,
            estado_tarea='completado',
            etapa_actual='finalizado',
            duracion_total=round(duracion_total, 3)
        )
        logger.info("Tarea Celery completada con éxito para ID: %s", historial_id)
        
    except Exception as e:
        logger.exception("Error en tarea Celery para Historial_ia ID: %s", historial_id)
        Historial_ia.objects.filter(id=historial_id).update(
            estado_tarea='error',
            mensaje_error=str(e)
        )
