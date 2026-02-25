import json
import logging

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import DatabaseError

from creacion.models import Historial_ia
from creacion.services import consultar_langgraph

logger = logging.getLogger(__name__)

def seleccion_tipo_ruta(request):
    """Vista para la selección del tipo de ruta (Manual o IA)"""
    return render(request, 'seleccion_tipo_ruta.html')


def creacion_manual(request):
    """Vista para la creación manual de rutas"""
    return render(request, 'creacion_manual.html')

def generar_ruta(request):
    """Vista para la generacion con ia de rutas"""
    return render(request, './creacion/personalizacion.html')

@csrf_exempt
@require_POST
def generar_ruta_ia(request):
    try:
        body_unicode = request.body.decode('utf-8')
        datos = json.loads(body_unicode)

        ciudad = datos.get('ciudad')
        duracion = datos.get('duracion')
        personas = datos.get('personas')
        exigencia = datos.get('exigencia')
        mood = datos.get('mood')

        # Validación para comprobar que están todos los campos
        if not all([ciudad, duracion, personas, exigencia, mood]):
            return JsonResponse({
                "status": "ERROR",
                "mensaje": "Faltan parámetros obligatorios en la petición."
            }, status=400)
        
        ruta_generada = consultar_langgraph(datos)

        advertencias = []

        try:
            Historial_ia.objects.create(
                prompt=json.dumps(datos),
                respuesta=ruta_generada
            )
        except DatabaseError:
            logger.exception("No se pudo guardar el historial de IA")
            advertencias.append(
                "No se pudo guardar el historial de la ruta generada. "
                "Revisa y ejecuta las migraciones pendientes."
            )

        response_data = {
            "status": "OK",
            "mensaje": "Ruta generada y optimizada correctamente.",
            "datos_ruta": ruta_generada
        }

        if advertencias:
            response_data["advertencias"] = advertencias

        return JsonResponse(response_data, status=200)

    except Exception as e:
        return JsonResponse({
            "status": "ERROR",
            "mensaje": f"Error interno: {str(e)}"
        }, status=500)
