import json

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from creacion.models import Historial_ia
from creacion.services import consultar_langgraph

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

        Historial_ia.objects.create(
            prompt=json.dumps(datos),
            respuesta=ruta_generada
        )

        return JsonResponse({
            "status": "OK",
            "mensaje": "Ruta generada y optimizada correctamente.",
            "datos_ruta": ruta_generada
        }, status=200)

    except Exception as e:
        return JsonResponse({
            "status": "ERROR",
            "mensaje": f"Error interno: {str(e)}"
        }, status=500)