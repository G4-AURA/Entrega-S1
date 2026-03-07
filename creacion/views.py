import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from creacion import services

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
    """Endpoint HTTP delgado para generar rutas mediante IA."""
    try:
        services.validar_usuario_guia(request.user)
    except services.ErrorPermisosRuta as exc:
        mensaje = str(exc)
        status = 401 if 'iniciar sesión' in mensaje else 403
        return JsonResponse({'status': 'ERROR', 'mensaje': mensaje}, status=status)

    try:
        datos = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'El cuerpo de la petición debe ser un JSON válido.'},
            status=400,
        )

    try:
        payload = services.normalizar_payload_ia(datos)
        guia = services.obtener_guia_para_usuario(request.user)
        ruta_generada = services.generar_ruta_con_ia(payload)
        ruta_guardada = services.guardar_ruta_ia(guia=guia, payload=payload, ruta_generada=ruta_generada)

        advertencias = []
        advertencia_historial = services.guardar_historial_ruta_ia(payload, ruta_generada)
        if advertencia_historial:
            advertencias.append(advertencia_historial)

        response_data = {
            'status': 'OK',
            'mensaje': 'Ruta generada, optimizada y guardada correctamente.',
            'ruta_id': ruta_guardada.id,
            'datos_ruta': ruta_generada,
        }
        if advertencias:
            response_data['advertencias'] = advertencias

        return JsonResponse(response_data, status=200)
    except services.ErrorValidacionRuta as exc:
        logger.warning('Error de validación en generar_ruta_ia: %s', exc)
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorPermisosRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=403)
    except services.ErrorPersistenciaRuta as exc:
        logger.exception('Error de persistencia en generar_ruta_ia')
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)


@csrf_exempt
@require_POST
def guardar_ruta_manual(request):
    """Endpoint HTTP delgado para guardar una ruta manual."""
    try:
        services.validar_usuario_guia(request.user)
    except services.ErrorPermisosRuta as exc:
        mensaje = str(exc)
        status = 401 if 'iniciar sesión' in mensaje else 403
        return JsonResponse({'status': 'ERROR', 'mensaje': mensaje}, status=status)

    try:
        datos = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'El cuerpo de la petición debe ser un JSON válido.'},
            status=400,
        )

    try:
        guia = services.obtener_guia_para_usuario(request.user)
        ruta = services.guardar_ruta_manual(guia=guia, payload=datos)
        return JsonResponse(
            {'status': 'OK', 'mensaje': 'Ruta guardada correctamente.', 'ruta_id': ruta.id},
            status=200,
        )
    except services.ErrorValidacionRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorPermisosRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=403)
    except services.ErrorPersistenciaRuta as exc:
        logger.exception('Error de persistencia en guardar_ruta_manual')
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)
