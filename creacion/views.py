import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from billing.tier_guard import (
    TierRuleViolation,
    apply_payload_tier_rules,
    clamp_generated_stops_to_tier,
    ensure_ai_generation_allowed,
    ensure_ai_route_confirmation_allowed,
    ensure_ai_stop_replacement_allowed,
    ensure_manual_routes_quota_available,
    ensure_moods_allowed,
    ensure_route_people_count_allowed,
    ensure_route_stop_count_allowed,
    get_allowed_moods_for_guia,
    get_max_stops_per_route_limit,
    get_session_capacity_limit,
    record_ai_generation_usage,
    record_ai_stop_replacement_usage,
    tier_error_response,
)
from creacion import services
from creacion.services import consultar_langgraph
from creacion.tasks import tarea_generar_ruta_ia
from rutas.models import Guia, Ruta

logger = logging.getLogger(__name__)


def _normalizar_moods(moods):
    return services.normalizar_moods(moods)


def _obtener_guia_para_usuario(user):
    if hasattr(user, 'turista'):
        return None
    return services.obtener_guia_para_usuario(user)


def _obtener_guia_para_contexto(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    if hasattr(user, 'turista'):
        return None
    auth_profile = getattr(user, 'auth_profile', None)
    return getattr(auth_profile, 'guia', None)


def _build_tier_ui_context(guia):
    allowed_moods = get_allowed_moods_for_guia(guia)
    allowed_moods_set = set(allowed_moods)
    mood_choices_disponibles = [
        (value, label) for value, label in Ruta.Mood.choices if value in allowed_moods_set
    ]
    return {
        'guia': guia,
        'es_freemium': bool(guia and guia.tipo_suscripcion == Guia.Suscripcion.FREEMIUM),
        'tier_max_personas': get_session_capacity_limit(guia),
        'tier_max_stops': get_max_stops_per_route_limit(guia),
        'mood_choices_disponibles': mood_choices_disponibles,
    }


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
    guia = _obtener_guia_para_contexto(request.user)
    return render(request, 'creacion_manual.html', _build_tier_ui_context(guia))


def generar_ruta(request):
    """Vista para la generación con IA de rutas."""
    guia = _obtener_guia_para_contexto(request.user)
    return render(request, './creacion/personalizacion.html', _build_tier_ui_context(guia))


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
        guia = _obtener_guia_para_usuario(request.user)
        if not guia:
            return JsonResponse(
                {'status': 'ERROR', 'mensaje': 'No se pudo encontrar o crear un perfil de guía para este usuario.'},
                status=500,
            )

        try:
            ensure_ai_generation_allowed(guia)
        except TierRuleViolation as exc:
            return tier_error_response(exc)

        datos, tier_warnings = apply_payload_tier_rules(guia, datos)
        mood_input = datos.get('mood')
        if isinstance(mood_input, str):
            mood_input = [mood_input]
        if not isinstance(mood_input, list):
            mood_input = []

        try:
            ensure_moods_allowed(guia, mood_input)
        except TierRuleViolation as exc:
            return tier_error_response(exc)

        modo_seleccion = bool(datos.get('modo_seleccion'))
        payload = services.normalizar_payload_ia(datos)
        try:
            ensure_route_people_count_allowed(guia, payload.get('personas'))
        except TierRuleViolation as exc:
            return tier_error_response(exc)

        sesion_generacion = services.crear_estado_sesion_generacion(request, payload=payload)
        historial = services.pre_crear_historial_ia(payload, sesion_id=sesion_generacion['session_id'])
        tarea_generar_ruta_ia.delay(historial.id, payload, sesion_id=sesion_generacion['session_id'])

        return JsonResponse(
            {
                'status': 'OK',
                'mensaje': 'Generación de ruta iniciada en segundo plano.',
                'historial_id': historial.id,
                'sesion_generacion_id': sesion_generacion['session_id'],
                'checkpoint_actual': 'procesando_ia',
                'warnings': tier_warnings,
            },
            status=202,
        )
    except (services.ErrorValidacionRuta, ValueError) as exc:
        logger.warning('Error de validación en generar_ruta_ia: %s', exc)
        return JsonResponse({'status': 'ERROR', 'mensaje': f'Error en los datos: {str(exc)}'}, status=400)
    except services.ErrorSesionGeneracionNoEncontrada as exc:
        logger.warning('Sesión de generación no encontrada en generar_ruta_ia: %s', exc)
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=404)
    except services.ErrorSesionGeneracionExpirada as exc:
        logger.warning('Sesión de generación expirada en generar_ruta_ia: %s', exc)
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=410)
    except services.ErrorIntegracionIA as exc:
        logger.warning('Error de integración IA en generar_ruta_ia: %s', exc)
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=502)
    except services.ErrorPersistenciaRuta as exc:
        logger.exception('Error de persistencia en generar_ruta_ia')
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)


@csrf_exempt
@require_POST
def confirmar_ruta_ia(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes iniciar sesión para guardar rutas.'}, status=401)

    if hasattr(request.user, 'turista'):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Solo los guías pueden guardar rutas generadas por IA.'},
            status=403,
        )

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'El cuerpo de la petición no es JSON válido.'}, status=400)

    sesion_generacion_id = str(body.get('sesion_generacion_id') or '').strip()
    seleccion_indices = body.get('seleccion_indices') or []
    if not sesion_generacion_id:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes indicar la sesión de generación.'}, status=400)
    if not isinstance(seleccion_indices, list):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'La selección de paradas no es válida.'}, status=400)

    try:
        indices = sorted(set(int(idx) for idx in seleccion_indices))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'La selección de paradas no es válida.'}, status=400)

    try:
        estado = services.obtener_estado_sesion_generacion(request, sesion_generacion_id)
    except services.ErrorSesionGeneracionNoEncontrada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=404)
    except services.ErrorSesionGeneracionExpirada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=410)

    paradas_propuestas = estado.get('paradas_propuestas') or []
    if not paradas_propuestas:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'No hay paradas propuestas para esta sesión.'}, status=400)

    if not indices:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes seleccionar al menos una parada.'}, status=400)

    if indices[-1] >= len(paradas_propuestas) or indices[0] < 0:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'La selección de paradas no es válida.'}, status=400)

    paradas_seleccionadas = [paradas_propuestas[idx] for idx in indices]
    paradas_rechazadas = [
        parada
        for idx, parada in enumerate(paradas_propuestas)
        if idx not in set(indices)
    ]

    contexto_generacion = estado.get('contexto_generacion') or {}
    payload_guardado = {
        'ciudad': contexto_generacion.get('ciudad') or 'AURA',
        'duracion': contexto_generacion.get('duracion') or 2,
        'personas': contexto_generacion.get('personas') or 4,
        'exigencia': contexto_generacion.get('exigencia') or 'media',
        'mood': contexto_generacion.get('mood') or [],
        'restricciones': estado.get('restricciones_usuario') or [],
    }

    ruta_base = (contexto_generacion.get('ruta_generada_base') or {})
    ruta_generada_final = {
        'titulo': ruta_base.get('titulo') or f"Ruta {payload_guardado['ciudad']}",
        'descripcion': ruta_base.get('descripcion') or 'Ruta creada desde selección guiada por IA.',
        'duracion_horas': ruta_base.get('duracion_horas') or payload_guardado['duracion'],
        'num_personas': ruta_base.get('num_personas') or payload_guardado['personas'],
        'nivel_exigencia': ruta_base.get('nivel_exigencia') or payload_guardado['exigencia'],
        'mood': ruta_base.get('mood') or payload_guardado['mood'],
        'paradas': paradas_seleccionadas,
    }

    try:
        guia = _obtener_guia_para_usuario(request.user)
    except services.ErrorPermisosRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=403)
    except services.ErrorPersistenciaRuta as exc:
        logger.exception('Error de persistencia obteniendo guía en confirmar_ruta_ia')
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)

    if not guia:
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'No se pudo encontrar o crear un perfil de guía para este usuario.'},
            status=500,
        )

    try:
        ensure_ai_route_confirmation_allowed(guia)
        ensure_route_stop_count_allowed(guia, len(paradas_seleccionadas))
        ensure_route_people_count_allowed(guia, payload_guardado.get('personas'))
        ensure_moods_allowed(guia, ruta_generada_final.get('mood') or [])
    except TierRuleViolation as exc:
        return tier_error_response(exc)

    try:
        ruta_guardada = _guardar_ruta_ia_en_bd(guia=guia, payload=payload_guardado, ruta_generada=ruta_generada_final)
    except (services.ErrorValidacionRuta, ValueError) as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorPersistenciaRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)

    try:
        for parada_rechazada in paradas_rechazadas:
            services.avanzar_checkpoint_sesion_generacion(
                request,
                sesion_generacion_id,
                checkpoint='seleccion_paradas_guia',
                parada_rechazada=parada_rechazada,
                motivo_rechazo='No seleccionada por el guía durante la confirmación de la ruta.',
            )

        estado_final = services.avanzar_checkpoint_sesion_generacion(
            request,
            sesion_generacion_id,
            checkpoint='ruta_guardada',
            datos_extra={'ruta_id': ruta_guardada.id},
        )
    except services.ErrorSesionGeneracionNoEncontrada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=404)
    except services.ErrorSesionGeneracionExpirada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=410)

    ruta_generada_final['id'] = ruta_guardada.id
    ruta_generada_final['checkpoint_contexto'] = {
        'restricciones_usuario': estado_final.get('restricciones_usuario') or [],
        'paradas_rechazadas': estado_final.get('paradas_rechazadas') or [],
    }
    services.guardar_historial_ruta_ia(payload_guardado, ruta_generada_final)

    return JsonResponse(
        {
            'status': 'OK',
            'mensaje': 'Ruta guardada correctamente con la selección del guía.',
            'ruta_id': ruta_guardada.id,
            'sesion_generacion_id': sesion_generacion_id,
            'checkpoint_actual': estado_final.get('checkpoint_actual'),
            'datos_ruta': ruta_generada_final,
        },
        status=200,
    )


@csrf_exempt
@require_POST
def generar_paradas_adicionales_ia(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes iniciar sesión para continuar.'}, status=401)

    if hasattr(request.user, 'turista'):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Solo los guías pueden pedir paradas adicionales.'},
            status=403,
        )

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'El cuerpo de la petición no es JSON válido.'}, status=400)

    sesion_generacion_id = str(body.get('sesion_generacion_id') or '').strip()
    sugerencias_texto = str(body.get('sugerencias') or '').strip()
    cantidad_raw = body.get('cantidad', 3)
    if not sesion_generacion_id:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes indicar la sesión de generación.'}, status=400)

    try:
        cantidad = int(cantidad_raw)
    except (TypeError, ValueError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'La cantidad debe ser un entero válido.'}, status=400)

    try:
        estado = services.obtener_estado_sesion_generacion(request, sesion_generacion_id)
        candidatos = services.generar_paradas_adicionales_sesion(
            estado_sesion=estado,
            cantidad=cantidad,
            sugerencias_texto=sugerencias_texto,
        )

        restricciones_extra = [sugerencias_texto] if sugerencias_texto else None
        estado_actualizado = services.avanzar_checkpoint_sesion_generacion(
            request,
            sesion_generacion_id,
            checkpoint='paradas_adicionales_generadas',
            paradas_propuestas=candidatos,
            restricciones=restricciones_extra,
        )
    except services.ErrorSesionGeneracionNoEncontrada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=404)
    except services.ErrorSesionGeneracionExpirada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=410)
    except services.ErrorValidacionRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorIntegracionIA as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=502)

    return JsonResponse(
        {
            'status': 'OK',
            'mensaje': 'Paradas adicionales generadas correctamente.',
            'sesion_generacion_id': sesion_generacion_id,
            'checkpoint_actual': estado_actualizado.get('checkpoint_actual'),
            'datos': {
                'paradas_propuestas': estado_actualizado.get('paradas_propuestas') or [],
            },
        },
        status=200,
    )

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

        try:
            ensure_manual_routes_quota_available(guia)
            ensure_route_stop_count_allowed(guia, len(payload.get('paradas') or []))
            ensure_route_people_count_allowed(guia, payload.get('num_personas'))
            selected_moods = payload.get('mood') if isinstance(payload.get('mood'), list) else []
            ensure_moods_allowed(guia, selected_moods)
        except TierRuleViolation as exc:
            return tier_error_response(exc)

        ruta = services.guardar_ruta_manual(guia=guia, payload=payload)
        return JsonResponse(
            {'status': 'OK', 'mensaje': 'Ruta guardada correctamente.', 'ruta_id': ruta.id},
            status=200,
        )
    except services.ErrorValidacionRuta as exc:
        return JsonResponse({'status': 'ERROR', 'errores': exc.errores}, status=400)
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
    if not ruta.es_generada_ia:
        return JsonResponse(
            {
                'status': 'ERROR',
                'mensaje': 'Las sugerencias de paradas con IA solo están disponibles para rutas generadas con IA.',
            },
            status=400,
        )

    try:
        ensure_ai_stop_replacement_allowed(guia, ruta)
    except TierRuleViolation as exc:
        return tier_error_response(exc)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'El cuerpo de la petición no es JSON válido.'}, status=400)

    cantidad_raw = body.get('cantidad', 3)
    sesion_generacion_id = body.get('sesion_generacion_id')
    try:
        cantidad = int(cantidad_raw)
    except (TypeError, ValueError):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'El parámetro cantidad debe ser un número entero.'},
            status=400,
        )

    try:
        resultado = services.generar_candidatos_paradas_ia(ruta=ruta, cantidad=cantidad)
        if sesion_generacion_id:
            services.avanzar_checkpoint_sesion_generacion(
                request,
                sesion_generacion_id,
                checkpoint='sugerencias_generadas',
                paradas_propuestas=resultado.get('candidatos') or [],
                datos_extra={'ruta_id': ruta.id},
            )
    except services.ErrorValidacionRuta as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorSesionGeneracionNoEncontrada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=404)
    except services.ErrorSesionGeneracionExpirada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=410)
    except services.ErrorIntegracionIA as exc:
        return JsonResponse(
            {
                'status': 'OK',
                'mensaje': f'No se pudieron generar sugerencias IA en este momento: {exc}',
                'datos': {
                    'ruta_id': ruta.id,
                    'ciudad': None,
                    'tematicas': ruta.mood,
                    'paradas_existentes': [],
                    'candidatos': [],
                },
            },
            status=200,
        )

    record_ai_stop_replacement_usage(guia, ruta)
    return JsonResponse({'status': 'OK', 'datos': resultado}, status=200)


@csrf_exempt
@require_GET
def obtener_sesion_generacion_ia(request, session_id):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes iniciar sesión.'}, status=401)

    try:
        estado = services.obtener_estado_sesion_generacion(request, session_id=session_id)
    except services.ErrorSesionGeneracionNoEncontrada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=404)
    except services.ErrorSesionGeneracionExpirada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=410)

    return JsonResponse({'status': 'OK', 'datos': estado}, status=200)


@csrf_exempt
@require_POST
def actualizar_checkpoint_sesion_generacion(request, session_id):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes iniciar sesión.'}, status=401)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'El cuerpo de la petición no es JSON válido.'}, status=400)

    checkpoint = str(body.get('checkpoint') or '').strip() or 'checkpoint_manual'

    try:
        estado = services.avanzar_checkpoint_sesion_generacion(
            request,
            session_id,
            checkpoint=checkpoint,
            paradas_propuestas=body.get('paradas_propuestas') or [],
            parada_rechazada=body.get('parada_rechazada'),
            motivo_rechazo=body.get('motivo_rechazo') or '',
            restricciones=body.get('restricciones'),
            datos_extra=body.get('contexto') if isinstance(body.get('contexto'), dict) else None,
        )
    except services.ErrorSesionGeneracionNoEncontrada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=404)
    except services.ErrorSesionGeneracionExpirada as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=410)

    return JsonResponse({'status': 'OK', 'datos': estado}, status=200)
