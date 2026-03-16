import os
import json
import math
import logging
import requests
import uuid
from typing import TypedDict
from django.contrib.gis.geos import Point
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone
from langgraph.graph import StateGraph, END

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

from creacion.geo_clients import MapboxGeocodingClient, OSMGeocodingClient
from creacion.geo_validation import (
    NoConvergenciaCoordenadasError,
    completar_lista_paradas_validadas,
)
from creacion.models import Historial_ia
from rutas.models import AuthUser, Guia, Parada, Ruta

logger = logging.getLogger(__name__)


class ErrorRutaBase(Exception):
    """Clase base para errores de dominio en creación de rutas."""


class ErrorValidacionRuta(ErrorRutaBase):
    """Errores de validación de payload y datos de ruta."""


class ErrorPermisosRuta(ErrorRutaBase):
    """Errores de permisos para crear/guardar rutas."""


class ErrorPersistenciaRuta(ErrorRutaBase):
    """Errores al persistir rutas o su historial en base de datos."""


class ErrorIntegracionIA(ErrorRutaBase):
    """Errores al comunicarse o normalizar respuestas del proveedor de IA."""


class ErrorSesionGeneracionRuta(ErrorRutaBase):
    """Errores de estado/checkpoints de sesión de generación IA."""


class ErrorSesionGeneracionExpirada(ErrorSesionGeneracionRuta):
    """La sesión de generación ya no está disponible por expiración."""


class ErrorSesionGeneracionNoEncontrada(ErrorSesionGeneracionRuta):
    """No existe una sesión de generación para el identificador indicado."""


MAPA_MOOD_RUTA = {
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

MAPA_EXIGENCIA_RUTA = {
    'baja': Ruta.Exigencia.BAJA,
    'media': Ruta.Exigencia.MEDIA,
    'medio': Ruta.Exigencia.MEDIA,
    'alta': Ruta.Exigencia.ALTA,
}

MAX_POIS_ALLOWLIST_EN_PROMPT = 15
SESION_GENERACION_STORE_KEY = 'creacion_ruta_ia_sesiones'
SESION_GENERACION_TTL_SECONDS = 60 * 60 * 6
MIN_PARADAS_IA = 5
MAX_PARADAS_IA = 8

_MOOD_A_CATEGORIAS_OSM: dict[str, list[str]] = {
    'historia': [
        'historic=monument', 'historic=castle', 'historic=ruins',
        'tourism=museum', 'amenity=place_of_worship',
    ],
    'gastronomia': [
        'amenity=restaurant', 'amenity=cafe', 'amenity=bar', 'amenity=marketplace',
    ],
    'naturaleza': [
        'leisure=park', 'tourism=viewpoint',
    ],
    'misterio-leyendas': [
        'historic=monument', 'historic=ruins', 'historic=castle',
        'amenity=place_of_worship',
    ],
    'misterio y leyendas': [
        'historic=monument', 'historic=ruins', 'historic=castle',
        'amenity=place_of_worship',
    ],
    'local': [
        'amenity=marketplace', 'place=square', 'amenity=restaurant',
        'amenity=cafe', 'amenity=bar',
    ],
    'cine-series': [
        'amenity=cinema', 'tourism=museum', 'historic=monument',
    ],
    'cine y series': [
        'amenity=cinema', 'tourism=museum', 'historic=monument',
    ],
    'religioso-espiritual': [
        'amenity=place_of_worship', 'historic=monument', 'historic=castle',
    ],
    'religioso y espiritual': [
        'amenity=place_of_worship', 'historic=monument', 'historic=castle',
    ],
    'arquitectura-diseno': [
        'tourism=museum', 'historic=monument', 'historic=castle',
        'tourism=gallery', 'amenity=theatre',
    ],
    'arquitectura y diseño': [
        'tourism=museum', 'historic=monument', 'historic=castle',
        'tourism=gallery', 'amenity=theatre',
    ],
    'ocio-cultural': [
        'amenity=theatre', 'amenity=cinema', 'amenity=library',
        'tourism=gallery', 'tourism=museum', 'leisure=stadium',
    ],
    'ocio/cultural': [
        'amenity=theatre', 'amenity=cinema', 'amenity=library',
        'tourism=gallery', 'tourism=museum', 'leisure=stadium',
    ],
}

def validar_ciudad_existe(ciudad: str) -> bool:
    """
    Consulta a la API de Nominatim (OpenStreetMap) si el nombre de la ciudad existe.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': ciudad,
        'format': 'json',
        'limit': 1
    }
    headers = {
        'User-Agent': 'AURA-RouteApp/1.0' 
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return len(data) > 0
        return True # Fallback por si la API falla
    except requests.RequestException:
        return True

def _obtener_pois_allowlist(ciudad: str, moods: list[str]) -> list[dict]:
    """
    Consulta la allowlist y devuelve hasta MAX_POIS_ALLOWLIST_EN_PROMPT POIs
    filtrados por ciudad y por las categorías OSM relevantes para los moods dados.

    Importa el modelo POI de forma diferida para evitar dependencias circulares
    y para que el módulo sea importable sin Django configurado en tests unitarios.

    Devuelve lista vacía si la allowlist está vacía o hay error de BD.
    """
    try:
        from allowList.models import POI  # importación diferida intencionada
    except ImportError:
        logger.warning('No se pudo importar el modelo POI de allowList; se omiten recomendaciones.')
        return []

    # Reunir categorías relevantes para todos los moods seleccionados
    categorias_relevantes: set[str] = set()
    for mood in moods:
        clave = str(mood).strip().lower()
        categorias_relevantes.update(_MOOD_A_CATEGORIAS_OSM.get(clave, []))

    try:
        qs = POI.objects.filter(ciudad__icontains=ciudad.strip())
        if categorias_relevantes:
            qs = qs.filter(categoria__in=categorias_relevantes)
        qs = qs.order_by('nombre')[:MAX_POIS_ALLOWLIST_EN_PROMPT]

        return [
            {
                'nombre': poi.nombre,
                'coords': [poi.lat, poi.lon],
                'categoria': poi.get_categoria_display(),
            }
            for poi in qs
        ]
    except Exception as exc:
        logger.warning('Error al consultar la allowlist de POIs: %s', exc)
        return []
    

def _construir_bloque_allowlist(pois: list[dict]) -> str:
    """
    Formatea los POIs de la allowlist como un bloque de texto para el prompt.
    Devuelve cadena vacía si no hay POIs.
    """
    if not pois:
        return ''

    lineas = [
        '\n## Puntos de Interés recomendados (allowlist curada)',
        'Los siguientes lugares han sido verificados y aprobados para esta ciudad.',
        'Inclúyelos en la ruta siempre que encajen con la temática solicitada:',
    ]
    for poi in pois:
        lat, lon = poi['coords']
        lineas.append(f'  - {poi["nombre"]} ({poi["categoria"]}) — coords: [{lat}, {lon}]')

    return '\n'.join(lineas)


def normalizar_moods(moods_sin_normalizar):
    if isinstance(moods_sin_normalizar, str):
        moods_sin_normalizar = [moods_sin_normalizar]

    moods_normalizados = []
    for mood in moods_sin_normalizar or []:
        clave_mood = str(mood).strip().lower()
        if not clave_mood:
            continue
        moods_normalizados.append(MAPA_MOOD_RUTA.get(clave_mood, mood))

    return [m for m in moods_normalizados if m in dict(Ruta.Mood.choices)]


def validar_usuario_guia(usuario):
    if not usuario or not usuario.is_authenticated:
        raise ErrorPermisosRuta('Debes iniciar sesión para generar rutas.')
    if hasattr(usuario, 'turista'):
        raise ErrorPermisosRuta('Solo los guías pueden crear y guardar tours generados por IA.')


def obtener_guia_para_usuario(usuario):
    if hasattr(usuario, 'turista'):
        raise ErrorPermisosRuta('Solo los guías pueden crear rutas.')

    try:
        perfil_auth, _ = AuthUser.objects.get_or_create(user=usuario)
        guia, _ = Guia.objects.get_or_create(user=perfil_auth)
        return guia
    except (DatabaseError, IntegrityError) as exc:
        raise ErrorPersistenciaRuta(
            'No se pudo encontrar o crear un perfil de guía para este usuario.'
        ) from exc


def _firma_parada(checkpoint_parada):
    nombre = str(checkpoint_parada.get('nombre') or '').strip().lower()
    coords = checkpoint_parada.get('coordenadas') or [None, None]
    lat = None
    lon = None
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        lat = round(float(coords[0]), 5)
        lon = round(float(coords[1]), 5)
    return f'{nombre}|{lat}|{lon}'


def _normalizar_restricciones(raw_restricciones, deseos=None):
    if raw_restricciones is None:
        raw_restricciones = deseos or []

    if isinstance(raw_restricciones, str):
        raw_restricciones = [raw_restricciones]

    if not isinstance(raw_restricciones, list):
        return []

    normalizadas = []
    vistas = set()
    for restriccion in raw_restricciones:
        texto = str(restriccion).strip()
        if not texto:
            continue
        clave = texto.lower()
        if clave in vistas:
            continue
        vistas.add(clave)
        normalizadas.append(texto[:200])
        if len(normalizadas) >= 20:
            break
    return normalizadas


def _normalizar_parada_checkpoint(parada):
    if not isinstance(parada, dict):
        return None

    nombre = str(parada.get('nombre') or '').strip()
    if not nombre:
        return None

    coordenadas = _normalizar_coordenadas(
        parada.get('coordenadas') or parada.get('coords'),
        lat=parada.get('lat'),
        lon=parada.get('lon'),
    )
    if not coordenadas:
        return None

    return {
        'nombre': nombre[:120],
        'coordenadas': coordenadas,
        'categoria': str(parada.get('categoria') or '').strip()[:80],
        'justificacion': str(parada.get('justificacion') or '').strip()[:500],
    }


def _obtener_store_sesiones_generacion(request):
    store = request.session.get(SESION_GENERACION_STORE_KEY)
    if not isinstance(store, dict):
        store = {}
        request.session[SESION_GENERACION_STORE_KEY] = store
    return store


def crear_estado_sesion_generacion(request, payload, checkpoint='payload_normalizado'):
    ahora_epoch = int(timezone.now().timestamp())
    estado = {
        'session_id': uuid.uuid4().hex,
        'checkpoint_actual': checkpoint,
        'creado_en': ahora_epoch,
        'actualizado_en': ahora_epoch,
        'expira_en': ahora_epoch + SESION_GENERACION_TTL_SECONDS,
        'contexto_generacion': {
            'ciudad': payload.get('ciudad'),
            'duracion': payload.get('duracion'),
            'personas': payload.get('personas'),
            'exigencia': payload.get('exigencia'),
            'mood': payload.get('mood') or [],
        },
        'restricciones_usuario': _normalizar_restricciones(
            payload.get('restricciones'),
            deseos=payload.get('deseos') or [],
        ),
        'paradas_propuestas': [],
        'paradas_rechazadas': [],
    }

    store = _obtener_store_sesiones_generacion(request)
    store[estado['session_id']] = estado
    request.session[SESION_GENERACION_STORE_KEY] = store
    request.session.modified = True
    return estado


def obtener_estado_sesion_generacion(request, session_id, refresh_ttl=True):
    store = _obtener_store_sesiones_generacion(request)
    estado = store.get(str(session_id))
    if not estado:
        raise ErrorSesionGeneracionNoEncontrada(
            'No existe la sesión de generación solicitada. Inicia una nueva generación de ruta.'
        )

    ahora_epoch = int(timezone.now().timestamp())
    if int(estado.get('expira_en') or 0) < ahora_epoch:
        del store[str(session_id)]
        request.session[SESION_GENERACION_STORE_KEY] = store
        request.session.modified = True
        raise ErrorSesionGeneracionExpirada(
            'La sesión de generación ha expirado. Vuelve a iniciar la generación de la ruta.'
        )

    if refresh_ttl:
        estado['actualizado_en'] = ahora_epoch
        estado['expira_en'] = ahora_epoch + SESION_GENERACION_TTL_SECONDS
        store[str(session_id)] = estado
        request.session[SESION_GENERACION_STORE_KEY] = store
        request.session.modified = True

    return estado


def avanzar_checkpoint_sesion_generacion(
    request,
    session_id,
    checkpoint,
    *,
    paradas_propuestas=None,
    parada_rechazada=None,
    motivo_rechazo='',
    restricciones=None,
    datos_extra=None,
):
    estado = obtener_estado_sesion_generacion(request, session_id=session_id, refresh_ttl=False)
    store = _obtener_store_sesiones_generacion(request)

    ahora_epoch = int(timezone.now().timestamp())
    propuestas_actuales = estado.get('paradas_propuestas') or []
    firmas_actuales = {_firma_parada(p) for p in propuestas_actuales if isinstance(p, dict)}

    propuestas_nuevas = []
    for parada in paradas_propuestas or []:
        parada_norm = _normalizar_parada_checkpoint(parada)
        if not parada_norm:
            continue
        firma = _firma_parada(parada_norm)
        if firma in firmas_actuales:
            continue
        firmas_actuales.add(firma)
        parada_norm['checkpoint'] = checkpoint
        parada_norm['registrada_en'] = ahora_epoch
        propuestas_nuevas.append(parada_norm)

    estado['paradas_propuestas'] = propuestas_actuales + propuestas_nuevas

    if parada_rechazada:
        parada_rechazada_norm = _normalizar_parada_checkpoint(parada_rechazada)
        if parada_rechazada_norm:
            parada_rechazada_norm['motivo_rechazo'] = str(motivo_rechazo or '').strip()[:300]
            parada_rechazada_norm['checkpoint'] = checkpoint
            parada_rechazada_norm['registrada_en'] = ahora_epoch

            rechazos_actuales = estado.get('paradas_rechazadas') or []
            firmas_rechazos = {_firma_parada(p) for p in rechazos_actuales if isinstance(p, dict)}
            if _firma_parada(parada_rechazada_norm) not in firmas_rechazos:
                rechazos_actuales.append(parada_rechazada_norm)
                estado['paradas_rechazadas'] = rechazos_actuales

    if restricciones is not None:
        restricciones_existentes = estado.get('restricciones_usuario') or []
        estado['restricciones_usuario'] = _normalizar_restricciones(
            restricciones_existentes + _normalizar_restricciones(restricciones)
        )

    if isinstance(datos_extra, dict) and datos_extra:
        contexto = estado.get('contexto_generacion') or {}
        contexto.update(datos_extra)
        estado['contexto_generacion'] = contexto

    estado['checkpoint_actual'] = checkpoint
    estado['actualizado_en'] = ahora_epoch
    estado['expira_en'] = ahora_epoch + SESION_GENERACION_TTL_SECONDS

    store[str(session_id)] = estado
    request.session[SESION_GENERACION_STORE_KEY] = store
    request.session.modified = True
    return estado


def normalizar_payload_ia(datos):
    if not isinstance(datos, dict):
        raise ErrorValidacionRuta('El cuerpo de la petición debe ser un JSON válido.')

    ciudad = str(datos.get('ciudad') or '').strip()
    
    if not ciudad:
        raise ErrorValidacionRuta("El nombre de la ciudad es obligatorio.")

    if not validar_ciudad_existe(ciudad):
        raise ErrorValidacionRuta("La ciudad ingresada no se encuentra en nuestros registros o no existe.")
    
    duracion = datos.get('duracion')
    personas = datos.get('personas')
    exigencia = str(datos.get('exigencia') or '').strip().lower()
    mood = datos.get('mood')

    if not all([ciudad, duracion, personas, exigencia, mood]):
        raise ErrorValidacionRuta('Faltan parámetros obligatorios en la petición.')

    exigencia_normalizada = MAPA_EXIGENCIA_RUTA.get(exigencia)
    if not exigencia_normalizada:
        raise ErrorValidacionRuta('El nivel de exigencia indicado no es válido.')

    moods_normalizados = normalizar_moods(mood)
    if not moods_normalizados:
        raise ErrorValidacionRuta('Debes indicar al menos una temática (mood) válida.')
    
    deseos_raw = datos.get('deseos') or []
    if not isinstance(deseos_raw, list):
        raise ErrorValidacionRuta('Los deseos personalizados deben ser una lista.')
    deseos = [str(d).strip()[:100] for d in deseos_raw if str(d).strip()][:5]

    restricciones = _normalizar_restricciones(datos.get('restricciones'), deseos=deseos)

    # Metadata contextual enviada automáticamente desde el cliente (sin intervención del usuario)
    metadata = datos.get('metadata') or {}

    try:
        return {
            'ciudad': ciudad,
            'duracion': float(duracion),
            'personas': int(personas),
            'exigencia': exigencia_normalizada,
            'mood': moods_normalizados,
            'deseos': deseos,
            'restricciones': restricciones,
            'metadata': metadata,
        }
    except (TypeError, ValueError) as exc:
        raise ErrorValidacionRuta('Duración y personas deben tener un formato válido.') from exc


def generar_ruta_con_ia(payload):
    try:
        ruta_generada = consultar_langgraph(payload)
    except ErrorIntegracionIA:
        raise
    except Exception as exc:
        raise ErrorPersistenciaRuta('No se pudo generar la ruta con IA en este momento.') from exc

    if not isinstance(ruta_generada, dict):
        raise ErrorPersistenciaRuta('La IA devolvió un formato de ruta no válido.')

    return ruta_generada


def guardar_ruta_ia(guia, payload, ruta_generada):
    raw_paradas = ruta_generada.get('paradas')
    if not isinstance(raw_paradas, list) or not raw_paradas:
        raise ErrorValidacionRuta('La ruta generada no contiene paradas válidas para guardar.')
    objetivo_paradas = len(raw_paradas)

    exigencia_normalizada = MAPA_EXIGENCIA_RUTA.get(
        str(ruta_generada.get('nivel_exigencia') or payload.get('exigencia') or '').lower(),
        Ruta.Exigencia.MEDIA,
    )
    moods_normalizados = normalizar_moods(ruta_generada.get('mood') or payload.get('mood') or [])
    ciudad = str(payload.get('ciudad') or 'AURA').strip()
    fecha_creacion = timezone.localtime().strftime('%Y-%m-%d')

    try:
        with transaction.atomic():
            ruta = Ruta.objects.create(
                titulo=f"{ciudad} {fecha_creacion}",
                descripcion=ruta_generada.get('descripcion', ''),
                duracion_horas=float(ruta_generada.get('duracion_horas') or payload.get('duracion') or 1),
                num_personas=int(ruta_generada.get('num_personas') or payload.get('personas') or 1),
                nivel_exigencia=exigencia_normalizada,
                mood=moods_normalizados,
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
                    raise ErrorValidacionRuta(
                        'La ruta generada contiene paradas sin coordenadas válidas.'
                    )

                if lat is None or lon is None:
                    raise ErrorValidacionRuta(
                        'La ruta generada contiene paradas sin coordenadas válidas.'
                    )

                Parada.objects.create(
                    ruta=ruta,
                    orden=parada.get('orden') or idx,
                    nombre=parada.get('nombre') or f'Parada {idx}',
                    coordenadas=Point(float(lon), float(lat), srid=4326),
                )

                parada_payload = {
                    'orden': parada.get('orden') or idx,
                    'nombre': parada.get('nombre') or f'Parada {idx}',
                    'coordenadas': [float(lat), float(lon)],
                }
                for meta_key in ('fuente_validacion', 'tipo_geometria', 'error_m', 'corregida'):
                    if parada.get(meta_key) is not None:
                        parada_payload[meta_key] = parada.get(meta_key)

                paradas_normalizadas.append(parada_payload)

            if not paradas_normalizadas:
                raise ErrorValidacionRuta('No se han podido guardar coordenadas válidas para las paradas.')
            if len(paradas_normalizadas) != objetivo_paradas:
                raise ErrorValidacionRuta(
                    'No se pudo preservar el tamaño objetivo de la ruta generada al guardar las paradas.'
                )
    except ErrorValidacionRuta:
        raise
    except (DatabaseError, IntegrityError, TypeError, ValueError) as exc:
        raise ErrorPersistenciaRuta('No se pudo guardar la ruta generada en la base de datos.') from exc

    ruta_generada['id'] = ruta.id
    ruta_generada['nivel_exigencia'] = exigencia_normalizada
    ruta_generada['mood'] = moods_normalizados
    ruta_generada['es_generada_ia'] = True
    ruta_generada['paradas'] = paradas_normalizadas

    return ruta


def guardar_historial_ruta_ia(payload, ruta_generada):
    try:
        Historial_ia.objects.create(prompt=json.dumps(payload), respuesta=ruta_generada)
    except DatabaseError:
        logger.exception('No se pudo guardar el historial de IA')
        return (
            'No se pudo guardar el historial de la ruta generada. '
            'Revisa y ejecuta las migraciones pendientes.'
        )
    return None


def obtener_contexto_checkpoint_por_ruta(ruta_id):
    """
    Recupera el contexto de checkpoints guardado en historial IA para una ruta.
    Busca en los historiales más recientes una respuesta cuyo id de ruta coincida.
    """
    contexto_vacio = {
        'restricciones_usuario': [],
        'paradas_rechazadas': [],
    }

    if not ruta_id:
        return contexto_vacio

    try:
        historiales = Historial_ia.objects.order_by('-momento')[:200]
    except DatabaseError:
        return contexto_vacio

    for historial in historiales:
        respuesta = historial.respuesta if isinstance(historial.respuesta, dict) else {}
        if int(respuesta.get('id') or 0) != int(ruta_id):
            continue

        checkpoint_contexto = respuesta.get('checkpoint_contexto')
        if not isinstance(checkpoint_contexto, dict):
            return contexto_vacio

        return {
            'restricciones_usuario': checkpoint_contexto.get('restricciones_usuario') or [],
            'paradas_rechazadas': checkpoint_contexto.get('paradas_rechazadas') or [],
        }

    return contexto_vacio


def guardar_ruta_manual(guia, payload):
    titulo = str(payload.get('titulo') or '').strip()
    descripcion = payload.get('descripcion') or ''
    paradas_data = payload.get('paradas', [])

    if not titulo:
        raise ErrorValidacionRuta('El título de la ruta es obligatorio.')
    if not isinstance(paradas_data, list):
        raise ErrorValidacionRuta('El formato de paradas no es válido.')

    try:
        duracion_horas = float(payload.get('duracion_horas', 2.0))
        num_personas = int(payload.get('num_personas', 10))
    except (TypeError, ValueError) as exc:
        raise ErrorValidacionRuta('Duración y número de personas deben tener un formato válido.') from exc

    exigencia_raw = str(payload.get('nivel_exigencia', Ruta.Exigencia.MEDIA)).strip().lower()
    nivel_exigencia = MAPA_EXIGENCIA_RUTA.get(exigencia_raw, payload.get('nivel_exigencia', Ruta.Exigencia.MEDIA))
    moods = normalizar_moods(payload.get('mood', []))

    try:
        with transaction.atomic():
            ruta = Ruta.objects.create(
                titulo=titulo,
                descripcion=descripcion,
                duracion_horas=duracion_horas,
                num_personas=num_personas,
                nivel_exigencia=nivel_exigencia,
                mood=moods,
                es_generada_ia=False,
                guia=guia,
            )

            for idx, parada_data in enumerate(paradas_data, start=1):
                lat = parada_data.get('lat', 37.38)
                lon = parada_data.get('lon', -5.99)
                Parada.objects.create(
                    ruta=ruta,
                    orden=idx,
                    nombre=parada_data.get('nombre', f'Parada {idx}'),
                    coordenadas=Point(float(lon), float(lat), srid=4326),
                )
    except (DatabaseError, IntegrityError, TypeError, ValueError) as exc:
        raise ErrorPersistenciaRuta('No se pudo guardar la ruta manual en la base de datos.') from exc

    return ruta


def _normalizar_candidato_parada(candidato, idx):
    if not isinstance(candidato, dict):
        return None

    nombre = str(candidato.get('nombre') or '').strip()
    if not nombre:
        return None

    coordenadas = _normalizar_coordenadas(
        candidato.get('coordenadas') or candidato.get('coords'),
        lat=candidato.get('lat'),
        lon=candidato.get('lon'),
    )
    if not coordenadas:
        return None

    confianza_raw = candidato.get('nivel_confianza', candidato.get('confianza', 0.0))
    try:
        nivel_confianza = max(0.0, min(1.0, float(confianza_raw)))
    except (TypeError, ValueError):
        nivel_confianza = 0.0

    return {
        'id_sugerencia': idx,
        'nombre': nombre,
        'coordenadas': coordenadas,
        'categoria': str(candidato.get('categoria') or 'general').strip()[:60],
        'nivel_confianza': round(nivel_confianza, 2),
        'justificacion': str(candidato.get('justificacion') or '').strip()[:500],
    }


def _distancia_haversine_km(coord_a, coord_b):
    lat1, lon1 = coord_a
    lat2, lon2 = coord_b
    radio_tierra_km = 6371.0

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radio_tierra_km * c


def _calcular_contexto_geografico(paradas_existentes):
    coords = [p['coordenadas'] for p in paradas_existentes if isinstance(p.get('coordenadas'), list)]
    if not coords:
        return {'centro': [0.0, 0.0], 'radio_km': 8.0}

    centro_lat = sum(c[0] for c in coords) / len(coords)
    centro_lon = sum(c[1] for c in coords) / len(coords)
    centro = [centro_lat, centro_lon]

    radio_actual_km = max(_distancia_haversine_km(centro, c) for c in coords)
    radio_permitido_km = min(30.0, max(8.0, radio_actual_km + 10.0))

    return {'centro': centro, 'radio_km': radio_permitido_km}


def _esta_en_contexto_geografico(coordenadas, contexto_geo):
    return _distancia_haversine_km(coordenadas, contexto_geo['centro']) <= contexto_geo['radio_km']


def _normalizar_nombre_para_dedupe(nombre):
    return ' '.join(str(nombre or '').strip().lower().split())


def _clave_coordenadas_para_dedupe(coordenadas):
    return (round(float(coordenadas[0]), 5), round(float(coordenadas[1]), 5))


def _formatear_exclusiones_para_prompt(
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> str:
    nombres = sorted([n for n in nombres_excluidos if n])[:40]
    coords = [[lat, lon] for lat, lon in sorted(coords_excluidas)[:40]]
    return json.dumps(
        {
            'nombres': nombres,
            'coordenadas': coords,
        },
        ensure_ascii=False,
    )


def _construir_prompt_candidatos_paradas(
    *,
    cantidad: int,
    ciudad_contexto: str,
    ruta: Ruta,
    preferencias: dict,
    paradas_existentes: list[dict],
    contexto_geo: dict,
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> str:
    exclusiones = _formatear_exclusiones_para_prompt(nombres_excluidos, coords_excluidas)
    return f"""
        Eres un asistente experto en diseño de rutas turísticas.

        Debes proponer EXACTAMENTE {cantidad} nuevas paradas para complementar una ruta existente.

        ## Contexto de la ruta
        - Ciudad: {ciudad_contexto}
        - Temática(s): {', '.join(ruta.mood)}
        - Preferencias: {json.dumps(preferencias, ensure_ascii=False)}
        - Paradas existentes: {json.dumps(paradas_existentes, ensure_ascii=False)}
        - Centro geográfico aproximado de la ruta: {json.dumps(contexto_geo['centro'], ensure_ascii=False)}
        - Distancia máxima permitida desde el centro: {round(contexto_geo['radio_km'], 2)} km
        - Exclusiones obligatorias (NO repetir): {exclusiones}

        ## Criterios
        - Evita sugerir puntos duplicados respecto a las paradas existentes.
        - Evita también duplicados entre las propias sugerencias.
        - NO sugieras ningún nombre o coordenada de la lista de exclusiones.
        - Mantén coherencia temática con la ruta.
        - Propón coordenadas plausibles dentro de la ciudad indicada.
        - REGLA ESTRICTA: NO propongas paradas fuera del área geográfica de la ruta.

        Responde únicamente JSON válido (sin texto adicional) como lista de objetos con esta estructura:
        [
          {{
            "nombre": "Nombre de la parada",
            "coordenadas": [lat, lon],
            "categoria": "Categoría turística",
            "nivel_confianza": 0.0,
            "justificacion": "Motivo breve de por qué encaja en la ruta"
          }}
        ]
    """


def _solicitar_candidatos_paradas_ia(
    *,
    cantidad: int,
    ciudad_contexto: str,
    ruta: Ruta,
    preferencias: dict,
    paradas_existentes: list[dict],
    contexto_geo: dict,
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> list[dict]:
    prompt = _construir_prompt_candidatos_paradas(
        cantidad=cantidad,
        ciudad_contexto=ciudad_contexto,
        ruta=ruta,
        preferencias=preferencias,
        paradas_existentes=paradas_existentes,
        contexto_geo=contexto_geo,
        nombres_excluidos=nombres_excluidos,
        coords_excluidas=coords_excluidas,
    )
    try:
        respuesta = llamar_gemini_bypass(prompt, os.getenv('GEMINI_API_KEY'))
    except ErrorIntegracionIA:
        respuesta = None

    if isinstance(respuesta, list):
        return respuesta

    fallback_pois = _construir_pois_fallback_allowlist(
        ciudad=ciudad_contexto,
        moods=ruta.mood,
        cantidad_objetivo=cantidad,
        nombres_excluidos=set(nombres_excluidos),
        coords_excluidas=set(coords_excluidas),
    )
    if fallback_pois:
        logger.warning(
            'Se usan %s sugerencias fallback de allowlist por indisponibilidad de Gemini.',
            len(fallback_pois),
        )
        return [
            {
                'nombre': poi['nombre'],
                'coordenadas': poi['coords'],
                'categoria': poi.get('categoria', 'general'),
                'nivel_confianza': 0.95,
                'justificacion': poi.get('desc', 'Sugerencia de fallback allowlist.'),
            }
            for poi in fallback_pois
        ]

    raise ErrorIntegracionIA('No se pudieron generar nuevas paradas con IA ni con fallback de allowlist.')


def generar_candidatos_paradas_ia(*, ruta: Ruta, cantidad: int = 3):
    if cantidad < 1 or cantidad > 10:
        raise ErrorValidacionRuta('La cantidad de sugerencias debe estar entre 1 y 10.')

    paradas_existentes = []
    for parada in ruta.paradas.order_by('orden'):
        paradas_existentes.append({
            'orden': parada.orden,
            'nombre': parada.nombre,
            'coordenadas': [parada.coordenadas.y, parada.coordenadas.x],
        })

    if not paradas_existentes:
        raise ErrorValidacionRuta('La ruta no tiene paradas actuales para aportar contexto a la IA.')

    contexto_geo = _calcular_contexto_geografico(paradas_existentes)
    ciudad_contexto = str(ruta.titulo or '').split(' ')[0] or 'Sin ciudad'
    preferencias = {
        'duracion_horas': float(ruta.duracion_horas),
        'num_personas': int(ruta.num_personas),
        'nivel_exigencia': ruta.nivel_exigencia,
        'mood': ruta.mood,
        'descripcion': ruta.descripcion or '',
    }

    mapbox_client = MapboxGeocodingClient()
    osm_client = OSMGeocodingClient()

    respuesta_ia = _solicitar_candidatos_paradas_ia(
        cantidad=cantidad,
        ciudad_contexto=ciudad_contexto,
        ruta=ruta,
        preferencias=preferencias,
        paradas_existentes=paradas_existentes,
        contexto_geo=contexto_geo,
        nombres_excluidos=set(),
        coords_excluidas=set(),
    )

    def _proveedor_candidatos_adicionales(
        cantidad_solicitada: int,
        nombres_excluidos: set[str],
        coords_excluidas: set[tuple[float, float]],
    ) -> list[dict]:
        return _solicitar_candidatos_paradas_ia(
            cantidad=cantidad_solicitada,
            ciudad_contexto=ciudad_contexto,
            ruta=ruta,
            preferencias=preferencias,
            paradas_existentes=paradas_existentes,
            contexto_geo=contexto_geo,
            nombres_excluidos=nombres_excluidos,
            coords_excluidas=coords_excluidas,
        )

    try:
        candidatos = completar_lista_paradas_validadas(
            cantidad_objetivo=cantidad,
            candidatos_iniciales=respuesta_ia,
            normalizador_candidato=_normalizar_candidato_parada,
            proveedor_candidatos=_proveedor_candidatos_adicionales,
            paradas_existentes=paradas_existentes,
            ciudad=ciudad_contexto,
            contexto_geo=contexto_geo,
            mapbox_client=mapbox_client,
            osm_client=osm_client,
        )
    except NoConvergenciaCoordenadasError as exc:
        raise ErrorIntegracionIA(
            'No fue posible completar la cantidad solicitada de paradas válidas y no duplicadas para esta ruta.'
        ) from exc

    return {
        'ruta_id': ruta.id,
        'ciudad': ciudad_contexto,
        'tematicas': ruta.mood,
        'paradas_existentes': paradas_existentes,
        'candidatos': candidatos,
    }


def generar_paradas_adicionales_sesion(*, estado_sesion: dict, cantidad: int = 3, sugerencias_texto: str = ''):
    if cantidad < 1 or cantidad > 10:
        raise ErrorValidacionRuta('La cantidad de sugerencias debe estar entre 1 y 10.')

    contexto = estado_sesion.get('contexto_generacion') or {}
    ciudad = str(contexto.get('ciudad') or 'Sin ciudad').strip() or 'Sin ciudad'
    mood = contexto.get('mood') or []
    restricciones = estado_sesion.get('restricciones_usuario') or []

    paradas_existentes = []
    for idx, parada in enumerate(estado_sesion.get('paradas_propuestas') or [], start=1):
        coordenadas = _normalizar_coordenadas(
            parada.get('coordenadas') or parada.get('coords'),
            lat=parada.get('lat'),
            lon=parada.get('lon'),
        )
        if not coordenadas:
            continue

        nombre = str(parada.get('nombre') or '').strip()
        if not nombre:
            continue

        paradas_existentes.append(
            {
                'orden': parada.get('orden') or idx,
                'nombre': nombre,
                'coordenadas': coordenadas,
            }
        )

    if not paradas_existentes:
        raise ErrorValidacionRuta('No hay contexto de paradas propuestas para pedir alternativas adicionales.')

    contexto_geo = _calcular_contexto_geografico(paradas_existentes)

    bloque_sugerencias = ''
    sugerencias_texto = str(sugerencias_texto or '').strip()
    if sugerencias_texto:
        bloque_sugerencias = f"\nSugerencias adicionales del guía: {sugerencias_texto[:300]}"

    bloque_restricciones = ''
    if restricciones:
        bloque_restricciones = (
            "\nRestricciones activas del guía: "
            + '; '.join(str(r).strip() for r in restricciones if str(r).strip())[:600]
        )

    prompt = f"""
        Eres un asistente experto en diseño de rutas turísticas.

        Debes proponer {cantidad} NUEVAS paradas adicionales para complementar esta selección.

        ## Contexto
        - Ciudad: {ciudad}
        - Temática(s): {', '.join(mood) if mood else 'general'}
        - Paradas ya propuestas: {json.dumps(paradas_existentes, ensure_ascii=False)}
        - Centro geográfico aproximado: {json.dumps(contexto_geo['centro'], ensure_ascii=False)}
        - Distancia máxima permitida desde el centro: {round(contexto_geo['radio_km'], 2)} km
        {bloque_restricciones}
        {bloque_sugerencias}

        ## Criterios obligatorios
        - NO repitas paradas existentes.
        - NO repitas paradas dentro de la respuesta.
        - Mantén coherencia temática y con restricciones.
        - Devuelve coordenadas plausibles y dentro del área indicada.

        Responde únicamente JSON válido (sin texto extra) como lista de objetos:
        [
          {{
            "nombre": "Nombre de la parada",
            "coordenadas": [lat, lon],
            "categoria": "Categoría turística",
            "nivel_confianza": 0.0,
            "justificacion": "Motivo breve"
          }}
        ]
    """

    try:
        respuesta_ia = llamar_gemini_bypass(prompt, os.getenv('GEMINI_API_KEY'))
    except Exception as exc:
        raise ErrorIntegracionIA('No se pudieron generar paradas adicionales con IA en este momento.') from exc

    if not isinstance(respuesta_ia, list):
        raise ErrorIntegracionIA('La IA devolvió un formato inválido para las paradas adicionales.')

    nombres_vistos = {
        _normalizar_nombre_para_dedupe(p.get('nombre'))
        for p in paradas_existentes
        if _normalizar_nombre_para_dedupe(p.get('nombre'))
    }
    coords_vistas = {
        _clave_coordenadas_para_dedupe(p.get('coordenadas'))
        for p in paradas_existentes
        if isinstance(p.get('coordenadas'), list) and len(p.get('coordenadas')) >= 2
    }

    candidatos = []
    for idx, candidato in enumerate(respuesta_ia, start=1):
        normalizado = _normalizar_candidato_parada(candidato, idx)
        if not normalizado:
            continue
        if not _esta_en_contexto_geografico(normalizado['coordenadas'], contexto_geo):
            continue

        nombre_key = _normalizar_nombre_para_dedupe(normalizado.get('nombre'))
        coords_key = _clave_coordenadas_para_dedupe(normalizado.get('coordenadas'))
        if nombre_key in nombres_vistos or coords_key in coords_vistas:
            continue

        nombres_vistos.add(nombre_key)
        coords_vistas.add(coords_key)
        candidatos.append(normalizado)

    if not candidatos:
        raise ErrorIntegracionIA('La IA no devolvió paradas adicionales válidas y no duplicadas.')

    return candidatos

class State(TypedDict):
    usuario_input: dict 
    pois_seleccionados: list
    ruta_final: dict


MOOD_MAP = {
    'historia': 'historia',
    'gastronomia': 'gastronomia',
    'naturaleza': 'naturaleza',
    'misterio-leyendas': 'misterio y leyendas',
    'misterio y leyendas': 'misterio y leyendas',
    'local': 'local',
    'cine-series': 'cine y series',
    'cine y series': 'cine y series',
    'religioso-espiritual': 'religioso y espiritual',
    'religioso y espiritual': 'religioso y espiritual',
    'arquitectura-diseno': 'arquitectura y diseño',
    'arquitectura y diseño': 'arquitectura y diseño',
    'ocio-cultural': 'ocio/cultural',
    'ocio/cultural': 'ocio/cultural',
}

EXIGENCIA_MAP = {
    'baja': 'baja',
    'media': 'media',
    'medio': 'media',
    'alta': 'alta',
}

MAX_REINTENTOS_PARADA_INVALIDA = 3
MAX_ALTERNATIVAS_RUTA = 5
UMBRAL_DISTANCIA_MAXIMA_PARADA_KM = 35.0

_VARIACIONES_ALTERNATIVA = [
    'enfoque historico y monumental',
    'enfoque local y experiencial',
    'enfoque cultural y panoramico',
    'enfoque gastronomico y vida urbana',
    'enfoque naturaleza y espacios abiertos',
]

_KEYWORDS_MOOD = {
    'historia': ['historia', 'historico', 'museo', 'monumento', 'patrimonio'],
    'gastronomia': ['gastronomia', 'mercado', 'tapas', 'cocina', 'comida'],
    'naturaleza': ['parque', 'jardin', 'naturaleza', 'rio', 'mirador'],
    'misterio y leyendas': ['leyenda', 'misterio', 'enigmatico', 'tradicion'],
    'local': ['barrio', 'local', 'plaza', 'cotidiano', 'artesania'],
    'cine y series': ['cine', 'rodaje', 'escena', 'serie'],
    'religioso y espiritual': ['iglesia', 'catedral', 'templo', 'espiritual'],
    'arquitectura y diseño': ['arquitectura', 'diseño', 'fachada', 'edificio'],
    'ocio/cultural': ['teatro', 'galeria', 'cultural', 'ocio', 'espectaculo'],
}


def normalizar_mood(raw_moods):
    if isinstance(raw_moods, str):
        raw_moods = [raw_moods]

    normalizados = []
    for mood in raw_moods or []:
        key = str(mood).strip().lower()
        if not key:
            continue
        normalizados.append(MOOD_MAP.get(key, key))
    return normalizados


def normalizar_nivel_exigencia(raw_value, default='media'):
    return EXIGENCIA_MAP.get(str(raw_value or '').strip().lower(), default)


def _normalizar_coordenadas(raw_coordenadas, lat=None, lon=None):
    if isinstance(raw_coordenadas, dict):
        lat = raw_coordenadas.get('lat')
        lon = raw_coordenadas.get('lon') if raw_coordenadas.get('lon') is not None else raw_coordenadas.get('lng')
    elif isinstance(raw_coordenadas, (list, tuple)) and len(raw_coordenadas) >= 2:
        lat, lon = raw_coordenadas[0], raw_coordenadas[1]

    if lat is None or lon is None:
        return None

    return [float(lat), float(lon)]


def mapear_payload_ia(payload):
    ciudad = str(payload.get('ciudad') or '').strip()
    duracion = payload.get('duracion')
    personas = payload.get('personas')

    if not ciudad or duracion in (None, '') or personas in (None, ''):
        raise ValueError('Faltan parámetros obligatorios en la petición.')

    mood = normalizar_mood(payload.get('mood') or [])
    if not mood:
        raise ValueError('Debes seleccionar al menos un mood para generar la ruta.')

    return {
        'ciudad': ciudad,
        'duracion': float(duracion),
        'personas': int(personas),
        'exigencia': normalizar_nivel_exigencia(payload.get('exigencia')),
        'mood': mood,
    }


def mapear_payload_manual(payload):
    paradas_normalizadas = []
    for idx, parada in enumerate(payload.get('paradas', []), start=1):
        coords = _normalizar_coordenadas(
            parada.get('coordenadas') or parada.get('coords'),
            lat=parada.get('lat'),
            lon=parada.get('lon'),
        )
        if not coords:
            continue

        paradas_normalizadas.append(
            {
                'orden': int(parada.get('orden') or idx),
                'nombre': parada.get('nombre') or f'Parada {idx}',
                'descripcion': parada.get('descripcion') or parada.get('desc') or '',
                'coordenadas': coords,
            }
        )

    if not paradas_normalizadas:
        raise ValueError('La ruta manual debe incluir al menos una parada con coordenadas válidas.')

    return {
        'titulo': str(payload.get('titulo') or '').strip() or 'Ruta manual',
        'descripcion': str(payload.get('descripcion') or '').strip(),
        'duracion_horas': float(payload.get('duracion_horas') or 2.0),
        'num_personas': int(payload.get('num_personas') or 10),
        'nivel_exigencia': normalizar_nivel_exigencia(payload.get('nivel_exigencia')),
        'mood': normalizar_mood(payload.get('mood') or []),
        'paradas': paradas_normalizadas,
    }


def serializar_ruta_creada(ruta, paradas):
    return {
        'id': ruta.id,
        'titulo': ruta.titulo,
        'descripcion': ruta.descripcion,
        'duracion_horas': float(ruta.duracion_horas),
        'num_personas': int(ruta.num_personas),
        'nivel_exigencia': ruta.nivel_exigencia,
        'mood': ruta.mood,
        'es_generada_ia': bool(ruta.es_generada_ia),
        'paradas': paradas,
    }


### --- FUNCIONES AUXILIARES --- ###
def _leer_int_env(nombre: str, default: int) -> int:
    try:
        return int(os.getenv(nombre, str(default)))
    except (TypeError, ValueError):
        return default


def llamar_gemini_bypass(prompt, api_key):
    if not api_key:
        raise ErrorIntegracionIA('No hay API key de Gemini configurada.')

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }
    timeout_s = max(10, _leer_int_env('GEMINI_TIMEOUT_SECONDS', 30))
    max_reintentos = max(0, _leer_int_env('GEMINI_MAX_RETRIES', 2))
    http_reintentable = {408, 409, 425, 429, 500, 502, 503, 504}

    ultimo_error: Exception | None = None
    for intento in range(max_reintentos + 1):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=timeout_s)
            if response.status_code in http_reintentable and intento < max_reintentos:
                logger.warning(
                    'Gemini devolvió status=%s (reintento %s/%s).',
                    response.status_code,
                    intento + 1,
                    max_reintentos,
                )
                continue

            response.raise_for_status()
            resultado = response.json()
            texto_json = resultado['candidates'][0]['content']['parts'][0]['text']
            return json.loads(texto_json)
        except requests.Timeout as exc:
            ultimo_error = exc
            if intento < max_reintentos:
                logger.warning(
                    'Timeout al llamar a Gemini (reintento %s/%s, timeout=%ss).',
                    intento + 1,
                    max_reintentos,
                    timeout_s,
                )
                continue
            raise ErrorIntegracionIA(
                f'La conexión con Gemini agotó el tiempo de espera tras {max_reintentos + 1} intentos.'
            ) from exc
        except requests.HTTPError as exc:
            ultimo_error = exc
            status_code = exc.response.status_code if exc.response is not None else 'desconocido'
            if status_code in http_reintentable and intento < max_reintentos:
                logger.warning(
                    'Error HTTP de Gemini (status=%s) reintentando %s/%s.',
                    status_code,
                    intento + 1,
                    max_reintentos,
                )
                continue
            raise ErrorIntegracionIA(
                f'Error HTTP al llamar a Gemini (status={status_code}).'
            ) from exc
        except requests.RequestException as exc:
            ultimo_error = exc
            if intento < max_reintentos:
                logger.warning(
                    'Error de red al llamar a Gemini (reintento %s/%s): %s',
                    intento + 1,
                    max_reintentos,
                    exc,
                )
                continue
            raise ErrorIntegracionIA('Error de red al conectar con Gemini.') from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ErrorIntegracionIA('Respuesta no válida de Gemini.') from exc
        except Exception as exc:
            raise ErrorIntegracionIA('Error inesperado al invocar Gemini.') from exc

    raise ErrorIntegracionIA('No se pudo obtener respuesta válida de Gemini.') from ultimo_error

def calcular_distancia(coord1, coord2):
    """Calcula distancia euclidiana entre dos puntos [lat, lon]"""
    return math.sqrt((coord1[0] - coord2[0])**2 + (coord1[1] - coord2[1])**2)

def crear_matriz_datos(pois):
    """Genera la matriz de distancias que necesita OR-Tools"""
    cant_nodos = len(pois)
    dist_matrix = {}
    
    for from_node in range(cant_nodos):
        dist_matrix[from_node] = {}
        for to_node in range(cant_nodos):
            if from_node == to_node:
                dist_matrix[from_node][to_node] = 0
            else:
                d = calcular_distancia(pois[from_node]['coords'], pois[to_node]['coords'])
                dist_matrix[from_node][to_node] = int(d * 10000)
                
    return {
        "distance_matrix": dist_matrix,
        "num_vehicles": 1,
        "depot": 0
    }

def _construir_bloque_metadata(metadata: dict) -> str:
    """Construye un bloque de contexto con los metadatos del cliente para enriquecer el prompt."""
    if not metadata:
        return ''

    lineas = ['\n## Contexto adicional del solicitante']

    ubicacion = metadata.get('ubicacion')
    if ubicacion:
        ciudad_origen = ubicacion.get('ciudad') or ubicacion.get('pais') or ''
        if ciudad_origen:
            lineas.append(f'- Ubicación actual del guía: {ciudad_origen}')
        coords = ubicacion.get('coords')
        if coords:
            lineas.append(f'  (coordenadas: {coords[0]:.4f}, {coords[1]:.4f})')

    idioma = metadata.get('idioma')
    if idioma:
        lineas.append(f'- Idioma del navegador: {idioma}')

    hora_local = metadata.get('hora_local')
    if hora_local:
        lineas.append(f'- Hora local del guía al generar: {hora_local}')

    zona_horaria = metadata.get('zona_horaria')
    if zona_horaria:
        lineas.append(f'- Zona horaria: {zona_horaria}')

    dispositivo = metadata.get('dispositivo')
    if dispositivo:
        lineas.append(f'- Tipo de dispositivo: {dispositivo}')

    return '\n'.join(lineas) if len(lineas) > 1 else ''

def _construir_bloque_deseos(deseos: list) -> str:
    """Construye un bloque con los deseos personalizados del guía para el prompt."""
    if not deseos:
        return ''
    items = '\n'.join(f'  - {d}' for d in deseos)
    return f'\n## Preferencias específicas del guía\n{items}'


def _calcular_objetivo_paradas_ia(datos: dict) -> int:
    try:
        duracion_horas = float(datos.get('duracion') or 2.0)
    except (TypeError, ValueError):
        duracion_horas = 2.0

    estimado = int(round(duracion_horas * 2))
    return max(MIN_PARADAS_IA, min(MAX_PARADAS_IA, estimado))


def _construir_pois_fallback_allowlist(
    *,
    ciudad: str,
    moods: list[str],
    cantidad_objetivo: int,
    nombres_excluidos: set[str] | None = None,
    coords_excluidas: set[tuple[float, float]] | None = None,
) -> list[dict]:
    nombres_excluidos = nombres_excluidos or set()
    coords_excluidas = coords_excluidas or set()
    pois_allowlist = _obtener_pois_allowlist(ciudad=ciudad, moods=moods)

    candidatos = []
    for poi in pois_allowlist:
        coords = poi.get('coords')
        if not isinstance(coords, list) or len(coords) < 2:
            continue

        nombre = str(poi.get('nombre') or '').strip()
        if not nombre:
            continue

        nombre_key = _normalizar_nombre_para_dedupe(nombre)
        coord_key = _clave_coordenadas_para_dedupe(coords)
        if nombre_key in nombres_excluidos or coord_key in coords_excluidas:
            continue

        candidatos.append(
            {
                'nombre': nombre,
                'coords': [float(coords[0]), float(coords[1])],
                'desc': f'POI curado en allowlist ({poi.get("categoria", "general")}).',
                'categoria': str(poi.get('categoria') or 'general'),
            }
        )

        nombres_excluidos.add(nombre_key)
        coords_excluidas.add(coord_key)
        if len(candidatos) >= cantidad_objetivo:
            break

    return candidatos


def _calcular_contexto_regeneracion_pois(datos: dict, pois_normalizados: list[dict]) -> dict:
    """
    Calcula contexto geográfico robusto para regeneración de POIs.

    Prioridad:
    1) Coordenadas iniciales normalizadas.
    2) POIs de allowlist de la ciudad/moods.
    3) Sin restricción geográfica dura (centro/radio None) para evitar [0,0].
    """
    if pois_normalizados:
        return _calcular_contexto_geografico(pois_normalizados)

    pois_allowlist = _obtener_pois_allowlist(
        ciudad=str(datos.get('ciudad') or ''),
        moods=datos.get('mood') or [],
    )
    contexto_desde_allowlist = []
    for poi in pois_allowlist:
        coords = poi.get('coords')
        if isinstance(coords, list) and len(coords) >= 2:
            contexto_desde_allowlist.append({'coordenadas': [float(coords[0]), float(coords[1])]})

    if contexto_desde_allowlist:
        return _calcular_contexto_geografico(contexto_desde_allowlist)

    return {'centro': None, 'radio_km': None}


def _normalizar_poi_generado_para_validacion(candidato, idx):
    if not isinstance(candidato, dict):
        return None

    nombre = str(candidato.get('nombre') or '').strip()
    if not nombre:
        return None

    coordenadas = _normalizar_coordenadas(
        candidato.get('coordenadas') or candidato.get('coords'),
        lat=candidato.get('lat'),
        lon=candidato.get('lon'),
    )
    if not coordenadas:
        return None

    descripcion = str(candidato.get('desc') or candidato.get('descripcion') or '').strip()

    return {
        'id_sugerencia': idx,
        'nombre': nombre,
        'coordenadas': coordenadas,
        'categoria': str(candidato.get('categoria') or 'general').strip()[:60],
        'nivel_confianza': 1.0,
        'justificacion': descripcion[:500],
        'descripcion': descripcion[:500],
    }


def _normalizar_lista_pois(pois):
    normalizados = []
    for idx, candidato in enumerate(pois or [], start=1):
        item = _normalizar_poi_generado_para_validacion(candidato, idx)
        if item:
            normalizados.append(item)
    return normalizados


def _construir_prompt_regeneracion_pois(
    *,
    datos: dict,
    cantidad: int,
    contexto_geo: dict,
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> str:
    exclusiones = _formatear_exclusiones_para_prompt(nombres_excluidos, coords_excluidas)
    centro = contexto_geo.get('centro')
    radio_km = contexto_geo.get('radio_km')
    centro_prompt = json.dumps(centro, ensure_ascii=False) if isinstance(centro, list) else '"No definido: usar ciudad solicitada"'
    radio_prompt = (
        f'{round(float(radio_km), 2)} km'
        if isinstance(radio_km, (int, float))
        else 'No definido: priorizar ciudad solicitada'
    )
    return f"""
        Eres un guía turístico experto.

        Debes generar EXACTAMENTE {cantidad} POIs nuevos para una ruta en {datos.get('ciudad')}.

        ## Contexto estricto
        - Duración: {datos.get('duracion')} horas
        - Número de personas: {datos.get('personas')}
        - Nivel de exigencia: {datos.get('exigencia')}
        - Temática(s): {', '.join(datos.get('mood') or [])}
        - Centro geográfico de referencia: {centro_prompt}
        - Radio máximo permitido: {radio_prompt}
        - Exclusiones obligatorias (nombres/coordenadas): {exclusiones}

        ## Reglas obligatorias
        - No devuelvas duplicados ni dentro de la lista ni respecto a exclusiones.
        - No sugieras puntos fuera del área geográfica indicada.
        - Coordenadas reales y plausibles del lugar exacto.

        Responde ÚNICAMENTE JSON válido:
        [
            {{"nombre": "Nombre del sitio", "coords": [lat, lon], "desc": "Breve descripción del lugar"}}
        ]
    """


def _solicitar_pois_adicionales_para_ruta_ia(
    *,
    datos: dict,
    cantidad: int,
    contexto_geo: dict,
    nombres_excluidos: set[str],
    coords_excluidas: set[tuple[float, float]],
) -> list[dict]:
    prompt = _construir_prompt_regeneracion_pois(
        datos=datos,
        cantidad=cantidad,
        contexto_geo=contexto_geo,
        nombres_excluidos=nombres_excluidos,
        coords_excluidas=coords_excluidas,
    )
    try:
        respuesta = llamar_gemini_bypass(prompt, os.getenv('GEMINI_API_KEY'))
    except ErrorIntegracionIA:
        respuesta = None

    if isinstance(respuesta, list):
        return respuesta

    fallback = _construir_pois_fallback_allowlist(
        ciudad=str(datos.get('ciudad') or ''),
        moods=datos.get('mood') or [],
        cantidad_objetivo=cantidad,
        nombres_excluidos=set(nombres_excluidos),
        coords_excluidas=set(coords_excluidas),
    )
    if fallback:
        logger.warning(
            'Se usa fallback de allowlist para regenerar %s paradas por indisponibilidad de Gemini.',
            len(fallback),
        )
        return fallback

    raise ErrorIntegracionIA('No se pudieron regenerar paradas válidas con IA ni con allowlist.')


def _normalizar_poi_para_optimizacion(poi_validado: dict) -> dict:
    return {
        'nombre': poi_validado['nombre'],
        'coords': poi_validado['coordenadas'],
        'desc': poi_validado.get('descripcion') or poi_validado.get('justificacion') or '',
        'fuente_validacion': poi_validado.get('fuente_validacion'),
        'tipo_geometria': poi_validado.get('tipo_geometria'),
        'error_m': poi_validado.get('error_m'),
        'corregida': poi_validado.get('corregida'),
    }


def _serializar_parada_ruta_final(poi: dict, orden: int) -> dict:
    payload = {
        'nombre': poi.get('nombre'),
        'coordenadas': poi.get('coords'),
        'orden': orden,
        'descripcion': poi.get('desc', ''),
    }
    for meta_key in ('fuente_validacion', 'tipo_geometria', 'error_m', 'corregida'):
        if meta_key in poi:
            payload[meta_key] = poi.get(meta_key)
    return payload


def _validar_y_completar_pois_ruta_ia(
    datos: dict,
    pois_iniciales: list[dict],
    *,
    cantidad_objetivo: int | None = None,
) -> list[dict]:
    if not isinstance(pois_iniciales, list):
        raise ErrorIntegracionIA('La IA devolvió un formato inválido para la lista inicial de paradas.')

    pois_normalizados = _normalizar_lista_pois(pois_iniciales)
    objetivo = int(cantidad_objetivo) if cantidad_objetivo else _calcular_objetivo_paradas_ia(datos)
    if objetivo <= 0:
        raise ErrorIntegracionIA('La cantidad objetivo de paradas debe ser mayor que 0.')

    contexto_geo = _calcular_contexto_regeneracion_pois(datos, pois_normalizados)
    ciudad = str(datos.get('ciudad') or '').strip() or 'Sin ciudad'
    mapbox_client = MapboxGeocodingClient()
    osm_client = OSMGeocodingClient()

    def _proveedor(cantidad_solicitada: int, nombres_excluidos: set[str], coords_excluidas: set[tuple[float, float]]):
        return _solicitar_pois_adicionales_para_ruta_ia(
            datos=datos,
            cantidad=cantidad_solicitada,
            contexto_geo=contexto_geo,
            nombres_excluidos=nombres_excluidos,
            coords_excluidas=coords_excluidas,
        )

    try:
        validadas = completar_lista_paradas_validadas(
            cantidad_objetivo=objetivo,
            candidatos_iniciales=pois_iniciales,
            normalizador_candidato=_normalizar_poi_generado_para_validacion,
            proveedor_candidatos=_proveedor,
            paradas_existentes=[],
            ciudad=ciudad,
            contexto_geo=contexto_geo,
            mapbox_client=mapbox_client,
            osm_client=osm_client,
        )
    except NoConvergenciaCoordenadasError as exc:
        raise ErrorIntegracionIA(
            'No fue posible completar el tamaño objetivo de paradas con coordenadas precisas para esta ruta.'
        ) from exc

    return [_normalizar_poi_para_optimizacion(parada) for parada in validadas]


### --- NODOS --- ###
def nodo_seleccion_sitios(state: State):
    print("--- NODO 1: GENERACIÓN DE RUTA ---")
    datos = state['usuario_input']
    api_key = os.getenv("GEMINI_API_KEY")
    objetivo_paradas = _calcular_objetivo_paradas_ia(datos)

    bloque_metadata = _construir_bloque_metadata(datos.get('metadata') or {})
    bloque_deseos = _construir_bloque_deseos(datos.get('deseos') or [])

    pois_allowlist = _obtener_pois_allowlist(
        ciudad=datos.get('ciudad', ''),
        moods=datos.get('mood') or [],
    )
    bloque_allowlist = _construir_bloque_allowlist(pois_allowlist)

    prompt = f"""
        Eres un guía turístico experto. Tu tarea es seleccionar los mejores Puntos de Interés (POIs) para
        una ruta en {datos.get('ciudad')}.

        ## Parámetros de la ruta
        - Duración total: {datos.get('duracion')} horas
        - Número de personas: {datos.get('personas')}
        - Nivel de exigencia física: {datos.get('exigencia')}
        - Temática(s): {', '.join(datos.get('mood') or [])}
        {bloque_metadata}
        {bloque_deseos}
        {bloque_allowlist}

        ## Instrucción
        Genera una lista de EXACTAMENTE {objetivo_paradas} POIs adecuados para estos parámetros. Ten en cuenta el contexto del
        solicitante y sus preferencias específicas si las hay.
        Si se han proporcionado POIs recomendados (allowlist), dales prioridad frente a otros lugares
        siempre que encajen con la temática. Puedes complementar con otros POIs si son necesarios para
        completar la ruta.

        Responde ÚNICAMENTE con un JSON válido (sin texto extra) con esta estructura:
        [
            {{"nombre": "Nombre del sitio", "coords": [lat, lon], "desc": "Breve descripción del lugar"}}
        ]
        """
    
    print(prompt)

    try:
        pois_iniciales = llamar_gemini_bypass(prompt, api_key)
    except ErrorIntegracionIA as exc:
        pois_iniciales = _construir_pois_fallback_allowlist(
            ciudad=str(datos.get('ciudad') or ''),
            moods=datos.get('mood') or [],
            cantidad_objetivo=objetivo_paradas,
        )
        if len(pois_iniciales) < objetivo_paradas:
            raise ErrorIntegracionIA(
                'Gemini no respondió y no hay suficientes POIs curados en la allowlist para completar la ruta.'
            ) from exc
        logger.warning(
            'Se usa fallback de allowlist (%s POIs) por error de Gemini: %s',
            len(pois_iniciales),
            exc,
        )

    pois_validados = _validar_y_completar_pois_ruta_ia(
        datos,
        pois_iniciales,
        cantidad_objetivo=objetivo_paradas,
    )
    return {"pois_seleccionados": pois_validados}
    

def nodo_optimizador_ortools(state: State):
    print("--- NODO 2: OPTIMIZACIÓN DE LA RUTA CON OR-TOOLS ---")
    pois = state['pois_seleccionados']
    
    if not pois or len(pois) < 2:
        paradas_directas = [
            _serializar_parada_ruta_final(poi, orden=idx)
            for idx, poi in enumerate(pois or [], start=1)
        ]
        json_final_simple = {
            "titulo": f"Ruta {state['usuario_input'].get('mood')}",
            "descripcion": "Ruta generada sin optimización necesaria.",
            "duracion_estimada": state['usuario_input'].get('duracion'),
            "nivel_exigencia": state['usuario_input'].get('exigencia'),
            "mood": state['usuario_input'].get('mood'),
            "paradas": paradas_directas
        }
        return {"ruta_final": json_final_simple}
    
    # 1. Preparar datos matemáticos
    data = crear_matriz_datos(pois)
    
    # 2. Crear el gestor de rutas y el modelo
    manager = pywrapcp.RoutingIndexManager(len(data['distance_matrix']),
                                           data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    # 3. Definir callback de distancia
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['distance_matrix'][from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    
    # 4. Definir coste (el objetivo es minimizar la distancia total)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # 5. Configurar estrategia de búsqueda
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

    # 6. Resolver
    solution = routing.SolveWithParameters(search_parameters)

    # 7. Construir la ruta ordenada
    pois_ordenados = []
    if solution:
        index = routing.Start(0)
        orden_contador = 1
        
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            poi_actual = pois[node_index]
            pois_ordenados.append(_serializar_parada_ruta_final(poi_actual, orden=orden_contador))
            
            index = solution.Value(routing.NextVar(index))
            orden_contador += 1
    else:
        print("No se encontró solución óptima, devolviendo orden original.")
        pois_ordenados = [
            _serializar_parada_ruta_final(poi, orden=idx)
            for idx, poi in enumerate(pois, start=1)
        ]

    json_final = {
        "titulo": f"Ruta {state['usuario_input'].get('mood')} Inteligente",
        "descripcion": "Ruta optimizada con algoritmo TSP (Traveling Salesperson Problem).",
        "duracion_estimada": state['usuario_input'].get('duracion'),
        "nivel_exigencia": state['usuario_input'].get('exigencia'),
        "mood": state['usuario_input'].get('mood'),
        "paradas": pois_ordenados
    }

    return {"ruta_final": json_final}


def _normalizar_poi_generado(poi, idx):
    if not isinstance(poi, dict):
        return None

    nombre = str(poi.get('nombre') or '').strip()
    if not nombre:
        return None

    coords = _normalizar_coordenadas(
        poi.get('coordenadas') or poi.get('coords'),
        lat=poi.get('lat'),
        lon=poi.get('lon'),
    )
    if not coords:
        return None

    return {
        'nombre': nombre[:120],
        'coords': coords,
        'desc': str(poi.get('desc') or poi.get('descripcion') or poi.get('justificacion') or '').strip()[:500],
        'categoria': str(poi.get('categoria') or 'general').strip()[:80],
        'orden': idx,
    }


def _validar_paradas_generadas(paradas):
    validas = []
    invalidas = []
    nombres_vistos = set()
    coords_vistas = set()

    for parada in paradas:
        coords = parada.get('coords') or [None, None]
        lat = coords[0] if len(coords) >= 2 else None
        lon = coords[1] if len(coords) >= 2 else None

        if lat is None or lon is None or not (-90 <= float(lat) <= 90) or not (-180 <= float(lon) <= 180):
            invalidas.append({'parada': parada, 'motivo': 'coordenadas_invalidas'})
            continue

        nombre_key = _normalizar_nombre_para_dedupe(parada.get('nombre'))
        coords_key = _clave_coordenadas_para_dedupe([lat, lon])
        if nombre_key in nombres_vistos or coords_key in coords_vistas:
            invalidas.append({'parada': parada, 'motivo': 'duplicada'})
            continue

        nombres_vistos.add(nombre_key)
        coords_vistas.add(coords_key)
        validas.append(parada)

    if len(validas) >= 2:
        centro = _calcular_contexto_geografico([
            {'coordenadas': parada['coords']}
            for parada in validas
        ])['centro']

        filtradas = []
        for parada in validas:
            if _distancia_haversine_km(parada['coords'], centro) > UMBRAL_DISTANCIA_MAXIMA_PARADA_KM:
                invalidas.append({'parada': parada, 'motivo': 'fuera_contexto_geografico'})
                continue
            filtradas.append(parada)
        validas = filtradas

    return validas, invalidas


def _solicitar_alternativa_parada(payload, parada_invalida, motivo, paradas_aceptadas, intento):
    nombres_aceptados = [p.get('nombre') for p in paradas_aceptadas]
    prompt = f"""
        Eres un guía turístico experto.
        Debes generar una alternativa para una parada inválida.

        Ciudad: {payload.get('ciudad')}
        Temática(s): {', '.join(payload.get('mood') or [])}
        Restricciones: {json.dumps(payload.get('restricciones') or [], ensure_ascii=False)}
        Paradas ya aceptadas: {json.dumps(nombres_aceptados, ensure_ascii=False)}

        Parada inválida detectada:
        - Nombre: {parada_invalida.get('nombre')}
        - Coordenadas: {json.dumps(parada_invalida.get('coords') or [], ensure_ascii=False)}
        - Motivo del error: {motivo}
        - Intento de reemplazo: {intento}

        Devuelve SOLO un JSON con una parada alternativa NO duplicada y geográficamente coherente:
        {{
          "nombre": "Nombre del lugar",
          "coords": [lat, lon],
          "desc": "Descripción breve",
          "categoria": "Categoría"
        }}
    """

    alternativa = llamar_gemini_bypass(prompt, os.getenv('GEMINI_API_KEY'))
    if isinstance(alternativa, list):
        alternativa = alternativa[0] if alternativa else None
    return _normalizar_poi_generado(alternativa, 1)


def _optimizar_pois_en_ruta(pois, payload):
    if not pois or len(pois) < 2:
        return {
            'titulo': f"Ruta {payload.get('mood')}",
            'descripcion': 'Ruta generada sin optimización necesaria.',
            'duracion_estimada': payload.get('duracion'),
            'nivel_exigencia': payload.get('exigencia'),
            'mood': payload.get('mood'),
            'paradas': [
                {
                    'nombre': p.get('nombre'),
                    'coordenadas': p.get('coords'),
                    'orden': idx + 1,
                    'descripcion': p.get('desc', ''),
                    'categoria': p.get('categoria', 'general'),
                }
                for idx, p in enumerate(pois)
            ],
        }

    data = crear_matriz_datos(pois)
    manager = pywrapcp.RoutingIndexManager(len(data['distance_matrix']), data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['distance_matrix'][from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        ordenadas = pois
    else:
        ordenadas = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            ordenadas.append(pois[node_index])
            index = solution.Value(routing.NextVar(index))

    paradas = []
    for idx, poi in enumerate(ordenadas, start=1):
        paradas.append(
            {
                'nombre': poi.get('nombre'),
                'coordenadas': poi.get('coords'),
                'orden': idx,
                'descripcion': poi.get('desc', ''),
                'categoria': poi.get('categoria', 'general'),
            }
        )

    return {
        'titulo': f"Ruta {payload.get('mood')} Inteligente",
        'descripcion': 'Ruta optimizada con algoritmo TSP (Traveling Salesperson Problem).',
        'duracion_estimada': payload.get('duracion'),
        'nivel_exigencia': payload.get('exigencia'),
        'mood': payload.get('mood'),
        'paradas': paradas,
    }


def _calcular_distancia_total_km(paradas):
    if len(paradas) < 2:
        return 0.0
    total = 0.0
    for idx in range(len(paradas) - 1):
        total += _distancia_haversine_km(paradas[idx]['coordenadas'], paradas[idx + 1]['coordenadas'])
    return total


def _calcular_diversidad_paradas(paradas):
    if not paradas:
        return 0.0
    nombres_unicos = {
        _normalizar_nombre_para_dedupe(parada.get('nombre'))
        for parada in paradas
        if parada.get('nombre')
    }
    ratio_nombres = len(nombres_unicos) / len(paradas)

    categorias_unicas = {
        str(parada.get('categoria') or '').strip().lower()
        for parada in paradas
        if parada.get('categoria')
    }
    ratio_categorias = len(categorias_unicas) / max(1, len(paradas))
    return min(1.0, 0.7 * ratio_nombres + 0.3 * ratio_categorias)


def _calcular_coherencia_tematica(paradas, moods):
    if not paradas:
        return 0.0
    keywords = []
    for mood in moods or []:
        keywords.extend(_KEYWORDS_MOOD.get(str(mood).strip().lower(), []))

    if not keywords:
        return 0.5

    matches = 0
    for parada in paradas:
        texto = f"{parada.get('nombre', '')} {parada.get('descripcion', '')} {parada.get('categoria', '')}".lower()
        if any(k in texto for k in keywords):
            matches += 1
    return matches / len(paradas)


def _generar_pois_base(payload, variacion):
    bloque_metadata = _construir_bloque_metadata(payload.get('metadata') or {})
    bloque_deseos = _construir_bloque_deseos(payload.get('deseos') or [])
    bloque_restricciones = _construir_bloque_deseos(payload.get('restricciones') or [])
    pois_allowlist = _obtener_pois_allowlist(ciudad=payload.get('ciudad', ''), moods=payload.get('mood') or [])
    bloque_allowlist = _construir_bloque_allowlist(pois_allowlist)

    prompt = f"""
        Eres un guía turístico experto. Selecciona POIs para una ruta en {payload.get('ciudad')}.

        Parámetros:
        - Duración: {payload.get('duracion')} horas
        - Personas: {payload.get('personas')}
        - Exigencia: {payload.get('exigencia')}
        - Temática(s): {', '.join(payload.get('mood') or [])}
        - Variación de alternativa: {variacion}
        {bloque_metadata}
        {bloque_deseos}
        {bloque_restricciones}
        {bloque_allowlist}

        Devuelve SOLO JSON válido con una lista de 5 a 8 POIs:
        [
          {{"nombre": "...", "coords": [lat, lon], "desc": "...", "categoria": "..."}}
        ]
    """
    return llamar_gemini_bypass(prompt, os.getenv('GEMINI_API_KEY'))


def _generar_ruta_alternativa_con_reintentos(payload, variacion):
    respuesta = _generar_pois_base(payload, variacion)
    if not isinstance(respuesta, list):
        raise ErrorIntegracionIA('La IA devolvió un formato inválido para la ruta alternativa.')

    candidatos = []
    for idx, poi in enumerate(respuesta, start=1):
        normalizado = _normalizar_poi_generado(poi, idx)
        if normalizado:
            candidatos.append(normalizado)

    validas, invalidas = _validar_paradas_generadas(candidatos)
    rechazadas = []

    for invalida in invalidas:
        parada = invalida['parada']
        motivo = invalida['motivo']
        reemplazo = None
        for intento in range(1, MAX_REINTENTOS_PARADA_INVALIDA + 1):
            try:
                reemplazo = _solicitar_alternativa_parada(payload, parada, motivo, validas, intento)
            except Exception:
                reemplazo = None
            if not reemplazo:
                continue

            validas_tmp = validas + [reemplazo]
            validas_revalidadas, invalidas_revalidadas = _validar_paradas_generadas(validas_tmp)
            if len(validas_revalidadas) == len(validas_tmp) and not invalidas_revalidadas:
                validas = validas_revalidadas
                break

        if not reemplazo:
            rechazadas.append(
                {
                    'nombre': parada.get('nombre') or 'Sin nombre',
                    'coordenadas': parada.get('coords') or [],
                    'motivo_rechazo': f'No superó validación: {motivo}',
                }
            )

    ruta = _optimizar_pois_en_ruta(validas, payload)
    distancia_total_km = _calcular_distancia_total_km(ruta.get('paradas') or [])
    diversidad = _calcular_diversidad_paradas(ruta.get('paradas') or [])
    coherencia = _calcular_coherencia_tematica(ruta.get('paradas') or [], payload.get('mood') or [])

    return {
        'ruta': ruta,
        'metricas': {
            'distancia_total_km': round(distancia_total_km, 3),
            'diversidad': round(diversidad, 3),
            'coherencia_tematica': round(coherencia, 3),
        },
        'paradas_rechazadas_validacion': rechazadas,
    }


def _seleccionar_mejor_alternativa(alternativas):
    if not alternativas:
        raise ErrorIntegracionIA('No se pudieron generar alternativas de ruta válidas.')

    distancias = [a['metricas']['distancia_total_km'] for a in alternativas]
    min_d, max_d = min(distancias), max(distancias)

    for alternativa in alternativas:
        dist = alternativa['metricas']['distancia_total_km']
        if max_d == min_d:
            distancia_score = 1.0
        else:
            distancia_score = 1.0 - ((dist - min_d) / (max_d - min_d))

        diversidad = alternativa['metricas']['diversidad']
        coherencia = alternativa['metricas']['coherencia_tematica']
        alternativa['score_total'] = round(0.45 * distancia_score + 0.30 * diversidad + 0.25 * coherencia, 4)

    alternativas.sort(key=lambda a: a['score_total'], reverse=True)
    return alternativas[0], alternativas


### --- GRAFO --- ###
def construir_grafo():
    workflow = StateGraph(State)
    
    workflow.add_node("agente_turistico", nodo_seleccion_sitios)
    workflow.add_node("matematico", nodo_optimizador_ortools)
    
    # Flujo: Entrada -> IA -> Matemáticas -> Fin
    workflow.set_entry_point("agente_turistico")
    workflow.add_edge("agente_turistico", "matematico")
    workflow.add_edge("matematico", END)
    
    return workflow.compile()

def consultar_langgraph(prompt_params):
    try:
        num_alternativas = int(prompt_params.get('num_alternativas', 3))
    except (TypeError, ValueError):
        num_alternativas = 3

    num_alternativas = max(1, min(MAX_ALTERNATIVAS_RUTA, num_alternativas))

    alternativas = []
    for idx in range(num_alternativas):
        variacion = _VARIACIONES_ALTERNATIVA[idx % len(_VARIACIONES_ALTERNATIVA)]
        try:
            alternativa = _generar_ruta_alternativa_con_reintentos(prompt_params, variacion)
        except ErrorIntegracionIA:
            continue
        alternativas.append(alternativa)

    mejor, evaluadas = _seleccionar_mejor_alternativa(alternativas)
    ruta_final = mejor['ruta']
    ruta_final['paradas_rechazadas_validacion'] = mejor.get('paradas_rechazadas_validacion') or []
    ruta_final['alternativas_evaluadas'] = [
        {
            'score_total': a.get('score_total'),
            'metricas': a.get('metricas'),
        }
        for a in evaluadas
    ]
    ruta_final['metricas_seleccion'] = mejor.get('metricas')
    return ruta_final
