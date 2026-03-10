import os
import json
import math
import logging
import requests
from typing import TypedDict
from django.contrib.gis.geos import Point
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone
from langgraph.graph import StateGraph, END

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

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


def normalizar_payload_ia(datos):
    if not isinstance(datos, dict):
        raise ErrorValidacionRuta('El cuerpo de la petición debe ser un JSON válido.')

    ciudad = str(datos.get('ciudad') or '').strip()
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
            'metadata': metadata,
        }
    except (TypeError, ValueError) as exc:
        raise ErrorValidacionRuta('Duración y personas deben tener un formato válido.') from exc


def generar_ruta_con_ia(payload):
    try:
        ruta_generada = consultar_langgraph(payload)
    except Exception as exc:
        raise ErrorPersistenciaRuta('No se pudo generar la ruta con IA en este momento.') from exc

    if not isinstance(ruta_generada, dict):
        raise ErrorPersistenciaRuta('La IA devolvió un formato de ruta no válido.')

    return ruta_generada


def guardar_ruta_ia(guia, payload, ruta_generada):
    raw_paradas = ruta_generada.get('paradas')
    if not isinstance(raw_paradas, list) or not raw_paradas:
        raise ErrorValidacionRuta('La ruta generada no contiene paradas válidas para guardar.')

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
                raise ErrorValidacionRuta('No se han podido guardar coordenadas válidas para las paradas.')
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

    ciudad_contexto = str(ruta.titulo or '').split(' ')[0] or 'Sin ciudad'
    preferencias = {
        'duracion_horas': float(ruta.duracion_horas),
        'num_personas': int(ruta.num_personas),
        'nivel_exigencia': ruta.nivel_exigencia,
        'mood': ruta.mood,
        'descripcion': ruta.descripcion or '',
    }

    prompt = f"""
        Eres un asistente experto en diseño de rutas turísticas.

        Debes proponer {cantidad} nuevas paradas para complementar una ruta existente.

        ## Contexto de la ruta
        - Ciudad: {ciudad_contexto}
        - Temática(s): {', '.join(ruta.mood)}
        - Preferencias: {json.dumps(preferencias, ensure_ascii=False)}
        - Paradas existentes: {json.dumps(paradas_existentes, ensure_ascii=False)}

        ## Criterios
        - Evita sugerir puntos duplicados respecto a las paradas existentes.
        - Mantén coherencia temática con la ruta.
        - Propón coordenadas plausibles dentro de la ciudad indicada.

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

    try:
        respuesta_ia = llamar_gemini_bypass(prompt, os.getenv('GEMINI_API_KEY'))
    except Exception as exc:
        raise ErrorIntegracionIA('No se pudieron generar nuevas paradas con IA en este momento.') from exc

    if not isinstance(respuesta_ia, list):
        raise ErrorIntegracionIA('La IA devolvió un formato inválido para las sugerencias de paradas.')

    candidatos = []
    for idx, candidato in enumerate(respuesta_ia, start=1):
        normalizado = _normalizar_candidato_parada(candidato, idx)
        if normalizado:
            candidatos.append(normalizado)

    if not candidatos:
        raise ErrorIntegracionIA('La IA no devolvió candidatos de paradas válidos.')

    return {
        'ruta_id': ruta.id,
        'ciudad': ciudad_contexto,
        'tematicas': ruta.mood,
        'paradas_existentes': paradas_existentes,
        'candidatos': candidatos,
    }

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
def llamar_gemini_bypass(prompt, api_key):

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

    try:
        response = requests.post(url, headers=headers, json=data, timeout=20)
        response.raise_for_status()

        resultado = response.json()
        texto_json = resultado['candidates'][0]['content']['parts'][0]['text']
        return json.loads(texto_json)
    except requests.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else "desconocido"
        print(f"ERROR HTTP al llamar a Gemini (status={status_code}): {e}")
    except requests.RequestException as e:
        print(f"ERROR de conexión al llamar a Gemini: {e}")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        print(f"ERROR procesando la respuesta de Gemini: {e}")
    except Exception as e:
        print(f"ERROR inesperado al llamar a la API: {e}")

    # Si se llega aquí, devolvemos datos de fallback.
    # Nota: un 429 (Too Many Requests) entra en requests.HTTPError y dispara este retorno.
        
    #Datos de prueba por si la conexión a la IA falla.
        
    return [
            {"nombre": f"Centro Histórico", "coords": [40.4167, -3.7037], "desc": "Punto de interés principal recomendado."},
            {"nombre": "Parque Principal", "coords": [40.4233, -3.6827], "desc": "Zona verde ideal para el descanso del grupo."},
            {"nombre": "Museo de Arte", "coords": [40.4137, -3.6921], "desc": "Parada cultural imprescindible."},
            {"nombre": "Mirador de la Ciudad", "coords": [40.4070, -3.7115], "desc": "Las mejores vistas para fotografías."},
            {"nombre": "Zona Gastronómica", "coords": [40.4150, -3.7070], "desc": "Lugar perfecto para degustar platos locales."}
        ]

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


### --- NODOS --- ###
def nodo_seleccion_sitios(state: State):
    print("--- NODO 1: GENERACIÓN DE RUTA ---")
    datos = state['usuario_input']
    api_key = os.getenv("GEMINI_API_KEY")

    bloque_metadata = _construir_bloque_metadata(datos.get('metadata') or {})
    bloque_deseos = _construir_bloque_deseos(datos.get('deseos') or [])

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

        ## Instrucción
        Genera una lista de 5 a 8 POIs adecuados para estos parámetros. Ten en cuenta el contexto del
        solicitante y sus preferencias específicas si las hay.

        Responde ÚNICAMENTE con un JSON válido (sin texto extra) con esta estructura:
        [
            {{"nombre": "Nombre del sitio", "coords": [lat, lon], "desc": "Breve descripción del lugar"}}
        ]
        """

    pois = llamar_gemini_bypass(prompt, api_key)
    return {"pois_seleccionados": pois}
    

def nodo_optimizador_ortools(state: State):
    print("--- NODO 2: OPTIMIZACIÓN DE LA RUTA CON OR-TOOLS ---")
    pois = state['pois_seleccionados']
    
    if not pois or len(pois) < 2:
        json_final_simple = {
            "titulo": f"Ruta {state['usuario_input'].get('mood')}",
            "descripcion": "Ruta generada sin optimización necesaria.",
            "duracion_estimada": state['usuario_input'].get('duracion'),
            "nivel_exigencia": state['usuario_input'].get('exigencia'),
            "mood": state['usuario_input'].get('mood'),
            "paradas": pois
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
            
            pois_ordenados.append({
                "nombre": poi_actual['nombre'],
                "coordenadas": poi_actual['coords'], 
                "orden": orden_contador,
                "descripcion": poi_actual.get('desc', '')
            })
            
            index = solution.Value(routing.NextVar(index))
            orden_contador += 1
    else:
        print("No se encontró solución óptima, devolviendo orden original.")
        pois_ordenados = pois

    json_final = {
        "titulo": f"Ruta {state['usuario_input'].get('mood')} Inteligente",
        "descripcion": "Ruta optimizada con algoritmo TSP (Traveling Salesperson Problem).",
        "duracion_estimada": state['usuario_input'].get('duracion'),
        "nivel_exigencia": state['usuario_input'].get('exigencia'),
        "mood": state['usuario_input'].get('mood'),
        "paradas": pois_ordenados
    }

    return {"ruta_final": json_final}


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
    app = construir_grafo()
    resultado = app.invoke({"usuario_input": prompt_params})
    return resultado["ruta_final"]
