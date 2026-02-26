import json
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from creacion.models import Historial_ia
from creacion.services import consultar_langgraph
from rutas.models import AuthUser, Guia, Parada, Ruta

logger = logging.getLogger(__name__)

MOOD_MAP = {
    'historia': Ruta.Mood.HISTORIA,
    'gastronomia': Ruta.Mood.GASTRONOMIA,
    'naturaleza': Ruta.Mood.NATURALEZA,
    'misterio-leyendas': Ruta.Mood.MISTERIO_Y_LEYENDAS,
    'misterio y leyendas': Ruta.Mood.MISTERIO_Y_LEYENDAS,
    'local': Ruta.Mood.LOCAL,
    'cine-series': Ruta.Mood.CINE_Y_SERIES,
    'cine y series': Ruta.Mood.CINE_Y_SERIES,
    'religioso-espiritual': Ruta.Mood.RELIGIOSO_Y_ESPIRITUAL,
    'religioso y espiritual': Ruta.Mood.RELIGIOSO_Y_ESPIRITUAL,
    'arquitectura-diseno': Ruta.Mood.ARQUITECTURA_Y_DISEÑO,
    'arquitectura y diseño': Ruta.Mood.ARQUITECTURA_Y_DISEÑO,
    'ocio-cultural': Ruta.Mood.OCIO_CULTURAL,
    'ocio/cultural': Ruta.Mood.OCIO_CULTURAL,
}

EXIGENCIA_MAP = {
    'baja': Ruta.Exigencia.BAJA,
    'media': Ruta.Exigencia.MEDIA,
    'medio': Ruta.Exigencia.MEDIA,
    'alta': Ruta.Exigencia.ALTA,
}


def _normalizar_moods(raw_moods):
    if isinstance(raw_moods, str):
        raw_moods = [raw_moods]

    normalizados = []
    for mood in raw_moods or []:
        key = str(mood).strip().lower()
        if not key:
            continue
        normalizados.append(MOOD_MAP.get(key, mood))

    return [m for m in normalizados if m in dict(Ruta.Mood.choices)]


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

    nivel_exigencia = EXIGENCIA_MAP.get(
        str(ruta_generada.get('nivel_exigencia') or payload.get('exigencia') or '').lower(),
        Ruta.Exigencia.MEDIA,
    )
    moods = _normalizar_moods(ruta_generada.get('mood') or payload.get('mood') or [])

    with transaction.atomic():
        ruta = Ruta.objects.create(
            titulo=ruta_generada.get('titulo') or f"Ruta IA por {payload.get('ciudad', 'AURA')}",
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
                    'coordenadas': [float(lat), float(lon)],
                }
            )

        if not paradas_normalizadas:
            raise ValueError('No se han podido guardar coordenadas válidas para las paradas.')

    ruta_generada['id'] = ruta.id
    ruta_generada['nivel_exigencia'] = nivel_exigencia
    ruta_generada['mood'] = moods
    ruta_generada['es_generada_ia'] = True
    ruta_generada['paradas'] = paradas_normalizadas

    return ruta


#@login_required
def seleccion_tipo_ruta(request):
    """Vista para la selección del tipo de ruta (Manual o IA)"""
    return render(request, 'seleccion_tipo_ruta.html')


#@login_required
def creacion_manual(request):
    """Vista para la creación manual de rutas"""
    return render(request, 'creacion_manual.html')

# @login_required
def generar_ruta(request):
    """Vista para la generacion con ia de rutas"""
    return render(request, './creacion/personalizacion.html')


@login_required
@csrf_exempt
@require_POST
def generar_ruta_ia(request):
    """
    Endpoint para generar rutas mediante IA y guardarlas en BD.
    
    Requisitos:
    - Usuario debe estar autenticado (por @login_required)
    - Usuario debe ser guía (no turista)
    - Se requiere un perfil de Guía para crear la ruta
    """
    
    # Validar que el usuario es guía (no turista)
    if hasattr(request.user, 'turista'):
        return JsonResponse(
            {
                'status': 'ERROR',
                'mensaje': 'Solo los guías pueden crear y guardar tours generados por IA.',
            },
            status=403,
        )

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
        
        # Generar la ruta con IA
        ruta_generada = consultar_langgraph(datos)
        
        # Obtener o crear perfil de guía para el usuario autenticado
        guia = _obtener_guia_para_usuario(request.user)
        if not guia:
            return JsonResponse(
                {
                    'status': 'ERROR',
                    'mensaje': 'No se pudo encontrar o crear un perfil de guía para este usuario.',
                },
                status=500,
            )

        # Guardar la ruta y sus paradas en BD
        ruta_guardada = _guardar_ruta_ia_en_bd(guia=guia, payload=datos, ruta_generada=ruta_generada)

        advertencias = []

        # Guardar historial de generación IA (opcional, no bloquea)
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
            "mensaje": "Ruta generada, optimizada y guardada correctamente.",
            "ruta_id": ruta_guardada.id,
            "datos_ruta": ruta_generada
        }

        if advertencias:
            response_data["advertencias"] = advertencias

        return JsonResponse(response_data, status=200)

    except ValueError as e:
        # Errores de validación de datos
        logger.warning("Error de validación en generar_ruta_ia: %s", e)
        return JsonResponse({
            "status": "ERROR",
            "mensaje": f"Error en los datos: {str(e)}"
        }, status=400)
    except Exception as e:
        # Errores internos
        logger.exception("Error interno en generar_ruta_ia")
        return JsonResponse({
            "status": "ERROR",
            "mensaje": f"Error interno del servidor: {str(e)}"
        }, status=500)
