import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from creacion import services
from creacion.services import consultar_langgraph
from rutas.models import Ruta

logger = logging.getLogger(__name__)


def _normalizar_moods(moods):
    return services.normalizar_moods(moods)


def _obtener_guia_para_usuario(user):
    if hasattr(user, 'turista'):
        return None
    return services.obtener_guia_para_usuario(user)


def _guardar_ruta_ia_en_bd(guia, payload, ruta_generada):
    try:
        return services.guardar_ruta_ia(guia=guia, payload=payload, ruta_generada=ruta_generada)
    except services.ErrorValidacionRuta as exc:
        raise ValueError(str(exc)) from exc


# @login_required
def seleccion_tipo_ruta(request):
    """Vista para la selección del tipo de ruta (Manual o IA)."""
    return render(request, 'seleccion_tipo_ruta.html')


def creacion_manual(request):
    """Vista para la creación manual de rutas."""
    return render(request, 'creacion_manual.html')


def generar_ruta(request):
    """Vista para la generación con IA de rutas."""
    return render(request, './creacion/personalizacion.html')


@csrf_exempt
@require_POST
def generar_ruta_ia(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes iniciar sesión para generar rutas.'}, status=401)

    if hasattr(request.user, 'turista'):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Solo los guías pueden crear y guardar tours generados por IA.'},
            status=403,
        )

    try:
        datos = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'El cuerpo de la petición no es JSON válido.'}, status=400)

    try:
        payload = services.normalizar_payload_ia(datos)
        ruta_generada = consultar_langgraph(payload)

        guia = _obtener_guia_para_usuario(request.user)
        if not guia:
            return JsonResponse(
                {'status': 'ERROR', 'mensaje': 'No se pudo encontrar o crear un perfil de guía para este usuario.'},
                status=500,
            )

        ruta_guardada = _guardar_ruta_ia_en_bd(guia=guia, payload=payload, ruta_generada=ruta_generada)

        advertencias = []
        advertencia_historial = services.guardar_historial_ruta_ia(payload, ruta_generada)
        if advertencia_historial:
            advertencias.append(advertencia_historial)

        response_data = {
            'status': 'OK',
            'mensaje': 'Ruta generada, optimizada y guardada correctamente.',
            'ruta_id': ruta_guardada.id,
            'datos_ruta': ruta_generada,
            'datos': {
                'ruta_id': ruta_guardada.id,
                'ruta': ruta_generada,
            },
        }
        if advertencias:
            response_data['advertencias'] = advertencias
            response_data['datos']['advertencias'] = advertencias

        return JsonResponse(response_data, status=200)
    except (services.ErrorValidacionRuta, ValueError) as exc:
        logger.warning('Error de validación en generar_ruta_ia: %s', exc)
        return JsonResponse({'status': 'ERROR', 'mensaje': f'Error en los datos: {str(exc)}'}, status=400)
    except services.ErrorPersistenciaRuta as exc:
        logger.exception('Error de persistencia en generar_ruta_ia')
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)


@csrf_exempt
@require_POST
def guardar_ruta_manual(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes iniciar sesión.'}, status=401)

    if hasattr(request.user, 'turista'):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Solo los guías pueden crear rutas.'}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'El cuerpo de la petición no es JSON válido.'}, status=400)

    try:
        guia = _obtener_guia_para_usuario(request.user)
        if not guia:
            return JsonResponse({'status': 'ERROR', 'mensaje': 'Perfil de guía no encontrado.'}, status=500)

        ruta = services.guardar_ruta_manual(guia=guia, payload=payload)
        return JsonResponse(
            {'status': 'OK', 'mensaje': 'Ruta guardada correctamente.', 'ruta_id': ruta.id},
            status=200,
        )
    except services.ErrorValidacionRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorPersistenciaRuta as exc:
        logger.exception('Error de persistencia en guardar_ruta_manual')
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)


@csrf_exempt
@require_POST
def generar_paradas_ia(request, ruta_id):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes iniciar sesión.'}, status=401)

    if hasattr(request.user, 'turista'):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Solo los guías pueden generar nuevas paradas.'}, status=403)

    try:
        guia = _obtener_guia_para_usuario(request.user)
    except services.ErrorPermisosRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=403)
    except services.ErrorPersistenciaRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)

    ruta = get_object_or_404(Ruta, id=ruta_id, guia=guia)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'El cuerpo de la petición no es JSON válido.'}, status=400)

    cantidad_raw = body.get('cantidad', 3)
    try:
        cantidad = int(cantidad_raw)
    except (TypeError, ValueError):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'El parámetro cantidad debe ser un número entero.'},
            status=400,
        )

    try:
        resultado = services.generar_candidatos_paradas_ia(ruta=ruta, cantidad=cantidad)
    except services.ErrorValidacionRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorIntegracionIA as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=502)

    return JsonResponse({'status': 'OK', 'datos': resultado}, status=200)
