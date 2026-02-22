import json

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@require_POST
def generar_ruta_ia(request):
    try:
        body_unicode = request.body.decode('utf-8')
        datos = json.loads(body_unicode)

        duracion = datos.get('duracion')
        personas = datos.get('personas')
        exigencia = datos.get('exigencia')
        mood = datos.get('mood')

        # Validación para comprobar que están todos los campos
        if not all([duracion, personas, exigencia, mood]):
            return JsonResponse({
                "status": "ERROR",
                "mensaje": "Faltan parámetros obligatorios en la petición."
            }, status=400)
        
        # TODO: conectar con LangGraph
        print(f"Petición recibida -> Duración: {duracion}h, Personas: {personas}, Exigencia: {exigencia}, Mood: {mood}")

        return JsonResponse({
            "status": "OK",
            "mensaje": "Parámetros recibidos correctamente."
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({
            "status": "ERROR",
            "mensaje": "El formato del JSON no es válido."
        }, status=400)