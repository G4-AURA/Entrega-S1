import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from creacion.models import Historial_ia
from creacion.services import (
    consultar_langgraph,
    mapear_payload_ia,
    mapear_payload_manual,
    normalizar_mood,
    normalizar_nivel_exigencia,
    serializar_ruta_creada,
)
from rutas.models import AuthUser, Guia, Parada, Ruta

logger = logging.getLogger(__name__)


def _ok_response(mensaje, datos, status_code=200):
    return JsonResponse(
        {
            'status': 'OK',
            'mensaje': mensaje,
            'datos': datos,
        },
        status=status_code,
    )


def _error_response(mensaje, status_code=400, codigo_error=None):
    body = {
        'status': 'ERROR',
        'mensaje': mensaje,
    }
    if codigo_error:
        body['codigo_error'] = codigo_error
    return JsonResponse(body, status=status_code)


def _obtener_guia_para_usuario(user):
    if hasattr(user, 'turista'):
        return None

    auth_profile, _ = AuthUser.objects.get_or_create(user=user)
    guia, _ = Guia.objects.get_or_create(user=auth_profile)
    return guia


def _guardar_ruta_ia_en_bd(guia, payload, ruta_generada):
    raw_paradas = ruta_generada.get('paradas')
    if not isinstance(raw_paradas, list) or not raw_paradas:
        raise ValueError('La ruta generada no contiene paradas válidas para guardar.')

    nivel_exigencia = normalizar_nivel_exigencia(
        ruta_generada.get('nivel_exigencia') or payload.get('exigencia'),
        default=Ruta.Exigencia.MEDIA,
    )
    moods = [m for m in normalizar_mood(ruta_generada.get('mood') or payload.get('mood') or []) if m in dict(Ruta.Mood.choices)]

    ciudad = str(payload.get('ciudad') or 'AURA').strip()
    fecha_creacion = timezone.localtime().strftime('%Y-%m-%d')

    with transaction.atomic():
        ruta = Ruta.objects.create(
            titulo=f"{ciudad} {fecha_creacion}",
            descripcion=ruta_generada.get('descripcion', ''),
            duracion_horas=float(ruta_generada.get('duracion_horas') or payload.get('duracion') or 1),
            num_personas=int(ruta_generada.get('num_personas') or payload.get('personas') or 1),
            nivel_exigencia=nivel_exigencia,
            mood=moods,
            es_generada_ia=True,
            guia=guia,
        )

        paradas_normalizadas = []
        for idx, parada in enumerate(raw_paradas, start=1):
            coordenadas = parada.get('coordenadas') or parada.get('coords')
            if isinstance(coordenadas, dict):
                lat = coordenadas.get('lat')
                lon = coordenadas.get('lon') if coordenadas.get('lon') is not None else coordenadas.get('lng')
            elif isinstance(coordenadas, (list, tuple)) and len(coordenadas) >= 2:
                lat, lon = coordenadas[0], coordenadas[1]
            else:
                continue

            if lat is None or lon is None:
                continue

            Parada.objects.create(
                ruta=ruta,
                orden=parada.get('orden') or idx,
                nombre=parada.get('nombre') or f'Parada {idx}',
                coordenadas=Point(float(lon), float(lat), srid=4326),
            )

            paradas_normalizadas.append(
                {
                    'orden': parada.get('orden') or idx,
                    'nombre': parada.get('nombre') or f'Parada {idx}',
                    'descripcion': parada.get('descripcion') or parada.get('desc') or '',
                    'coordenadas': [float(lat), float(lon)],
                }
            )

        if not paradas_normalizadas:
            raise ValueError('No se han podido guardar coordenadas válidas para las paradas.')

    return serializar_ruta_creada(ruta, paradas_normalizadas)


#@login_required
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
    """
    Contrato POST creacion:generar_ruta_ia
    Request JSON:
      ciudad:str, duracion:number, personas:int, exigencia:str, mood:list[str]|str
    Success JSON:
      {status, mensaje, datos:{ruta_id:int, ruta:{...serializada...}, advertencias:list[str]?}}
    Error JSON:
      {status, mensaje, codigo_error?}
    """
    if not request.user.is_authenticated:
        return _error_response('Debes iniciar sesión para generar rutas.', 401, 'AUTH_REQUIRED')

    if hasattr(request.user, 'turista'):
        return _error_response('Solo los guías pueden crear y guardar tours generados por IA.', 403, 'FORBIDDEN_ROLE')

    try:
        datos = mapear_payload_ia(json.loads(request.body.decode('utf-8')))

        ruta_generada = consultar_langgraph(datos)

        guia = _obtener_guia_para_usuario(request.user)
        if not guia:
            return _error_response('No se pudo encontrar o crear un perfil de guía para este usuario.', 500, 'GUIA_NOT_FOUND')

        ruta_serializada = _guardar_ruta_ia_en_bd(guia=guia, payload=datos, ruta_generada=ruta_generada)
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
        try:
            Historial_ia.objects.create(
                prompt=json.dumps(datos),
                respuesta=ruta_serializada,
            )
        except DatabaseError:
            logger.exception('No se pudo guardar el historial de IA')
            advertencias.append(
                'No se pudo guardar el historial de la ruta generada. Revisa y ejecuta las migraciones pendientes.'
            )
        advertencia_historial = services.guardar_historial_ruta_ia(payload, ruta_generada)
        if advertencia_historial:
            advertencias.append(advertencia_historial)

        response_datos = {
            'ruta_id': ruta_serializada['id'],
            'ruta': ruta_serializada,
        response_data = {
            'status': 'OK',
            'mensaje': 'Ruta generada, optimizada y guardada correctamente.',
            'ruta_id': ruta_guardada.id,
            'datos_ruta': ruta_generada,
        }
        if advertencias:
            response_datos['advertencias'] = advertencias
            response_data['advertencias'] = advertencias

        return _ok_response('Ruta generada, optimizada y guardada correctamente.', response_datos)

    except json.JSONDecodeError:
        return _error_response('El cuerpo de la petición no es JSON válido.', 400, 'INVALID_JSON')
    except ValueError as e:
        logger.warning('Error de validación en generar_ruta_ia: %s', e)
        return _error_response(f'Error en los datos: {str(e)}', 400, 'VALIDATION_ERROR')
    except Exception as e:
        logger.exception('Error interno en generar_ruta_ia')
        return _error_response(f'Error interno del servidor: {str(e)}', 500, 'INTERNAL_ERROR')
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
    """
    Contrato POST creacion:guardar_ruta_manual
    Request JSON:
      titulo:str, descripcion:str, duracion_horas:number?, num_personas:int?,
      nivel_exigencia:str?, mood:list[str]|str?, paradas:list[{nombre, coordenadas|coords|lat/lon}]
    Success JSON:
      {status, mensaje, datos:{ruta_id:int, ruta:{...serializada...}}}
    Error JSON:
      {status, mensaje, codigo_error?}
    """
    if not request.user.is_authenticated:
        return _error_response('Debes iniciar sesión.', 401, 'AUTH_REQUIRED')

    if hasattr(request.user, 'turista'):
        return _error_response('Solo los guías pueden crear rutas.', 403, 'FORBIDDEN_ROLE')

    try:
        payload = mapear_payload_manual(json.loads(request.body))

        guia = _obtener_guia_para_usuario(request.user)
        if not guia:
            return _error_response('Perfil de guía no encontrado.', 500, 'GUIA_NOT_FOUND')

        with transaction.atomic():
            ruta = Ruta.objects.create(
                titulo=payload['titulo'],
                descripcion=payload['descripcion'],
                duracion_horas=payload['duracion_horas'],
                num_personas=payload['num_personas'],
                nivel_exigencia=payload['nivel_exigencia'],
                mood=payload['mood'],
                es_generada_ia=False,
                guia=guia,
            )

            paradas_response = []
            for parada in payload['paradas']:
                lat, lon = parada['coordenadas']
                Parada.objects.create(
                    ruta=ruta,
                    orden=parada['orden'],
                    nombre=parada['nombre'],
                    coordenadas=Point(float(lon), float(lat), srid=4326),
                )
                paradas_response.append(parada)

        ruta_serializada = serializar_ruta_creada(ruta, paradas_response)
        return _ok_response('Ruta guardada correctamente.', {'ruta_id': ruta.id, 'ruta': ruta_serializada})

    except json.JSONDecodeError:
        return _error_response('El cuerpo de la petición no es JSON válido.', 400, 'INVALID_JSON')
    except ValueError as e:
        return _error_response(str(e), 400, 'VALIDATION_ERROR')
    except Exception as e:
        logger.exception('Error al guardar ruta manual')
        return _error_response(str(e), 400, 'SAVE_ERROR')

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
