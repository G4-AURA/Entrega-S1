from celery import shared_task
import logging
import json
# Importaciones relativas al paquete para evitar rutas absolutas
from . import services

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def tarea_generar_ruta_ia(self, payload, historial_id):
    """
    Tarea de Celery para generar la ruta con IA en segundo plano.
    Utiliza el historial_id para reportar progreso y telemetría en tiempo real.
    """
    logger.info(f"Iniciando tarea Celery para Historial_ia ID: {historial_id}")
    try:
        # El historial_id permite que consultar_langgraph y el decorador de telemetría actualicen la DB
        resultado_ruta = services.consultar_langgraph(payload, historial_id=historial_id)
        
        # Guardar resultado final y marcar como completado
        services.registrar_resultado_final_ia(historial_id, resultado_ruta)
        
        logger.info(f"Tarea Celery completada con éxito para ID: {historial_id}")
        return {"status": "success", "historial_id": historial_id}
        
    except Exception as exc:
        logger.error(f"Error en tarea Celery para Historial_ia ID: {historial_id}: {exc}", exc_info=True)
        # Registrar el error para que el polling del frontend lo detecte
        services.registrar_error_ia(historial_id, str(exc))
        return {"status": "error", "message": str(exc)}
