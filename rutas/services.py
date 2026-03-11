"""
rutas/services.py

Capa con la lógica de negocio de la gestión de rutas.

Roles:
  - Guías: siempre autenticados via Django Auth. Solo pueden gestionar sus propias rutas.
  - Turistas: acceso completamente denegado a la gestión de rutas.
  - Anónimo: acceso completamente denegado a la gestión de rutas.

S2.1-28/29/30/32: Se añaden las funciones de orquestación GraphHopper.
"""
import logging
import json

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Prefetch
from google import genai

from .models import Parada, Ruta
from tours.models import SESION_TOUR

logger = logging.getLogger(__name__)


# ================================================
# LISTADO DE RUTAS (CATÁLOGO)
# ================================================

def obtener_datos_catalogo_paginado(user, limit, page_number, tipo):
    """
    Obtiene el catálogo de rutas de un guía, filtrado y paginado.
    """
    rutas_qs = (
        Ruta.objects.select_related("guia")
        .prefetch_related(
            Prefetch('paradas', queryset=Parada.objects.all())
        )
        .filter(guia__user__user=user)
        .distinct()
        .order_by("-id")
    )

    if tipo == "ia":
        rutas_qs = rutas_qs.filter(es_generada_ia=True)
    elif tipo == "manual":
        rutas_qs = rutas_qs.filter(es_generada_ia=False)

    paginator = Paginator(rutas_qs, limit)

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    data = []
    for ruta in page_obj.object_list:
        guia_username = None
        guia_id = None

        try:
            if ruta.guia and ruta.guia.user:
                guia_id = ruta.guia.id
                guia_username = ruta.guia.user.user.username
        except Exception:
            pass

        sesion_activa = SESION_TOUR.objects.filter(
            ruta=ruta,
            estado__in=['pendiente', 'en_curso']
        ).first()
        sesion_activa_id = sesion_activa.id if sesion_activa else None

        paradas_en_memoria = sorted(ruta.paradas.all(), key=lambda p: p.orden)

        paradas_data = []
        for parada in paradas_en_memoria:
            coords = None
            if parada.coordenadas:
                coords = {
                    "lat": parada.coordenadas.y,
                    "lng": parada.coordenadas.x,
                }
            paradas_data.append({
                "id": parada.id,
                "orden": parada.orden,
                "nombre": parada.nombre,
                "coordenadas": coords,
            })

        data.append({
            "id": ruta.id,
            "titulo": ruta.titulo,
            "descripcion": ruta.descripcion,
            "duracion_horas": ruta.duracion_horas,
            "num_personas": ruta.num_personas,
            "nivel_exigencia": ruta.nivel_exigencia,
            "mood": list(ruta.mood or []),
            "es_generada_ia": ruta.es_generada_ia,
            "guia": {"id": guia_id, "username": guia_username},
            "paradas": paradas_data,
            "sesion_activa_id": sesion_activa_id,
        })

    return {
        "results": data,
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages,
        "total_items": paginator.count,
    }


# ================================================
# ELIMINAR RUTA
# ================================================

def eliminar_ruta(ruta):
    """Elimina una ruta de la base de datos."""
    ruta.delete()


# ================================================
# EDITAR RUTA
# ================================================

def actualizar_titulo_ruta(ruta, raw_titulo):
    titulo = (raw_titulo or "").strip()
    if not titulo:
        raise ValueError("El título no puede estar vacío")
    if len(titulo) > 255:
        raise ValueError("El título no puede superar los 255 caracteres")

    ruta.titulo = titulo
    ruta.save(update_fields=["titulo"])


def actualizar_descripcion_ruta(ruta, descripcion):
    ruta.descripcion = descripcion
    ruta.save(update_fields=["descripcion"])


def actualizar_duracion_ruta(ruta, raw_duracion):
    try:
        duracion_horas = float((raw_duracion or "").strip())
    except (TypeError, ValueError):
        raise ValueError("Valores numéricos inválidos (duración)")

    if duracion_horas <= 0 or duracion_horas > 24:
        raise ValueError("Valores numéricos inválidos (duración)")

    ruta.duracion_horas = duracion_horas
    ruta.save(update_fields=["duracion_horas"])


def actualizar_personas_ruta(ruta, raw_personas):
    try:
        num_personas = int((raw_personas or "").strip())
    except (TypeError, ValueError):
        raise ValueError("Valores numéricos inválidos (número de personas)")

    if num_personas <= 0 or num_personas > 50:
        raise ValueError("Valores numéricos inválidos (número de personas)")

    ruta.num_personas = num_personas
    ruta.save(update_fields=["num_personas"])


def actualizar_exigencia_ruta(ruta, raw_exigencia):
    nivel_exigencia = (raw_exigencia or "").strip()
    exigencias_validas = {value for value, _ in Ruta.Exigencia.choices}

    if nivel_exigencia not in exigencias_validas:
        raise ValueError("Valor inválido (nivel de exigencia)")

    ruta.nivel_exigencia = nivel_exigencia
    ruta.save(update_fields=["nivel_exigencia"])


def eliminar_parada_y_reordenar(ruta, parada):
    parada.delete()
    for index, parada_restante in enumerate(ruta.paradas.order_by("orden", "id"), start=1):
        if parada_restante.orden != index:
            parada_restante.orden = index
            parada_restante.save(update_fields=["orden"])


def _validar_coordenadas(raw_lat, raw_lon):
    """
    Función auxiliar.
    Convierte y valida que las coordenadas estén en el rango correcto.
    """
    try:
        lat = float((raw_lat or "").strip())
        lon = float((raw_lon or "").strip())
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Coordenadas fuera de rango")
        return lat, lon
    except (TypeError, ValueError):
        raise ValueError("Coordenadas inválidas")


def editar_parada(parada, raw_nombre, raw_lat, raw_lon):
    nombre = (raw_nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre no puede estar vacío")
    if len(nombre) > 255:
        raise ValueError("El nombre de la parada no puede superar los 255 caracteres")

    lat, lon = _validar_coordenadas(raw_lat, raw_lon)

    parada.nombre = nombre
    parada.coordenadas = Point(lon, lat, srid=4326)
    parada.save(update_fields=["nombre", "coordenadas"])


def añadir_parada(ruta, raw_nombre, raw_lat, raw_lon):
    nombre = (raw_nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre no puede estar vacío")
    if len(nombre) > 255:
        raise ValueError("El nombre de la parada no puede superar los 255 caracteres")

    lat, lon = _validar_coordenadas(raw_lat, raw_lon)

    ultimo_orden = ruta.paradas.order_by("-orden").values_list("orden", flat=True).first() or 0
    Parada.objects.create(
        ruta=ruta,
        orden=ultimo_orden + 1,
        nombre=nombre,
        coordenadas=Point(lon, lat, srid=4326),
    )


def reordenar_paradas(ruta, ordered_ids):
    """
    Actualiza el campo `orden` de cada parada según la nueva secuencia.

    Args:
        ordered_ids: Lista de IDs enteros ya parseada por la vista.
    """
    paradas_by_id = {parada.id: parada for parada in ruta.paradas.all()}
    for index, parada_id in enumerate(ordered_ids, start=1):
        parada = paradas_by_id.get(parada_id)
        if parada and parada.orden != index:
            parada.orden = index
            parada.save(update_fields=["orden"])


def actualizar_moods(ruta, raw_moods):
    allowed_moods = {value for value, _ in Ruta.Mood.choices}
    moods_limpios = [mood for mood in raw_moods if mood in allowed_moods]

    ruta.mood = moods_limpios
    ruta.save(update_fields=["mood"])


def obtener_paradas_json(paradas) -> list[dict]:
    """
    Serializa una lista de Parada a formato JSON-friendly para el template.
    Incluye métricas de GraphHopper si están disponibles (S2.1-29).
    """
    resultado = []
    for parada in paradas:
        coordenadas = [parada.coordenadas.y, parada.coordenadas.x] if parada.coordenadas else None
        resultado.append({
            "id": parada.id,
            "orden": parada.orden,
            "nombre": parada.nombre,
            "coordenadas": coordenadas,
            # Métricas del segmento hacia la siguiente parada (null en la última)
            "distancia_siguiente_m": getattr(parada, 'distancia_siguiente_m', None),
            "duracion_siguiente_min": getattr(parada, 'duracion_siguiente_min', None),
        })
    return resultado


# ================================================
# GRAPHHOPPER — Orquestación (S2.1-28/29/30/32)
# ================================================

def recalcular_ruta_graphhopper(ruta) -> bool:
    """
    Calcula la ruta GraphHopper y persiste geometría + métricas en BD.

    Diseño defensivo: cualquier fallo de GraphHopper se registra en log
    pero NUNCA interrumpe la operación principal del guía. Las operaciones
    de edición de paradas son críticas; el cálculo de ruta es un enriquecimiento.

    Args:
        ruta: Instancia del modelo Ruta. Sus paradas deben estar ya guardadas en BD.
    Returns:
        True si el cálculo fue exitoso, False en caso contrario.
    """
    # Importación local para evitar ciclo de imports (graphhopper → models → services)
    from .graphhopper import calcular_ruta, GraphHopperError

    paradas = list(ruta.paradas.order_by("orden"))

    # Con < 2 paradas no hay ruta que calcular: limpiar datos obsoletos
    if len(paradas) < 2:
        _limpiar_datos_graphhopper(ruta, paradas)
        return False

    try:
        resultado = calcular_ruta(paradas)
    except GraphHopperError as exc:
        logger.error(
            "GraphHopper: no se pudo calcular Ruta(id=%d): %s", ruta.id, exc
        )
        return False
    except Exception:
        logger.exception(
            "GraphHopper: error inesperado al calcular Ruta(id=%d)", ruta.id
        )
        return False

    # ── Guardar métricas globales en Ruta ─────────────────────────────────────
    ruta.geometria_ruta   = resultado.geometria
    ruta.distancia_total_m = resultado.distancia_total_m
    ruta.duracion_total_s  = resultado.duracion_total_s
    ruta.save(update_fields=["geometria_ruta", "distancia_total_m", "duracion_total_s"])

    # ── Guardar métricas por segmento en cada Parada ──────────────────────────
    segmentos_por_parada = {s.parada_origen_id: s for s in resultado.segmentos}

    for parada in paradas:
        seg = segmentos_por_parada.get(parada.id)
        if seg:
            parada.distancia_siguiente_m = seg.distancia_m
            parada.duracion_siguiente_s  = seg.duracion_s
        else:
            # Última parada o segmento no calculado
            parada.distancia_siguiente_m = None
            parada.duracion_siguiente_s  = None
        parada.save(update_fields=["distancia_siguiente_m", "duracion_siguiente_s"])

    logger.info(
        "GraphHopper: Ruta(id=%d) actualizada — %.0fm, %ds, %d segmentos.",
        ruta.id,
        resultado.distancia_total_m,
        resultado.duracion_total_s,
        len(resultado.segmentos),
    )
    return True


def _limpiar_datos_graphhopper(ruta, paradas: list) -> None:
    """
    Borra geometría y métricas cuando la ruta tiene < 2 paradas.
    Evita mostrar datos obsoletos de una configuración anterior.
    """
    ruta.geometria_ruta    = None
    ruta.distancia_total_m = None
    ruta.duracion_total_s  = None
    ruta.save(update_fields=["geometria_ruta", "distancia_total_m", "duracion_total_s"])

    for parada in paradas:
        parada.distancia_siguiente_m = None
        parada.duracion_siguiente_s  = None
        parada.save(update_fields=["distancia_siguiente_m", "duracion_siguiente_s"])


def serializar_resultado_graphhopper(ruta) -> dict:
    """
    Serializa el estado actual de la ruta para respuesta JSON del endpoint AJAX.
    Refresca la instancia desde BD antes de serializar para garantizar datos frescos.
    """
    ruta.refresh_from_db()
    paradas = list(ruta.paradas.order_by("orden"))

    segmentos_data = []
    for p in paradas:
        if p.distancia_siguiente_m is not None:
            segmentos_data.append({
                "parada_id": p.id,
                "distancia_m": p.distancia_siguiente_m,
                "duracion_min": p.duracion_siguiente_min,
            })

    return {
        "status": "ok",
        "geometria": ruta.geometria_ruta_coords,
        "distancia_total_km": ruta.distancia_total_km,
        "duracion_total_min": ruta.duracion_total_min,
        "segmentos": segmentos_data,
    }

# ================================================
# GENERACIÓN DE CURIOSIDADES (IA) - S2.2-36
# ================================================

class ServicioCuriosidadesIA:
    """
    Servicio encargado de generar curiosidades turísticas usando la API nueva de Gemini.
    S2.2-36.
    """
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def generar_curiosidad(self, parada: Parada, ciudad: str = "Sevilla") -> dict:
        """
        Genera el prompt, llama a la IA y devuelve un diccionario con los datos estructurados.
        """
       # Extraemos los temas reales de la ruta. Si no tiene, usamos uno por defecto.
        if getattr(parada, 'ruta', None) and getattr(parada.ruta, 'mood', None):
            temas_ruta = ", ".join(parada.ruta.mood)
        else:
            temas_ruta = "Historia, Cultura y Curiosidades locales"
        
        prompt = f"""
        Actúa como un guía turístico experto y carismático de la aplicación AURA. Tu misión es generar una píldora de conocimiento (curiosidad) sobre una parada turística específica. El tono debe ser divulgativo, ameno, fácil de entender para turistas y sorprendente.

        Contexto de la parada:
        - Ciudad: {ciudad}
        - Lugar: {parada.nombre}
        - Enfoque temático: {temas_ruta}

        Restricciones Estrictas:
        1. Responde ÚNICA Y EXCLUSIVAMENTE con un objeto JSON válido.
        2. No incluyas saludos, explicaciones, ni formato markdown (no uses ```json).
        3. El texto debe estar en Español.

        Estructura JSON requerida:
        {{
          "titulo": "Un titular gancho y atractivo (máximo 10 palabras)",
          "texto": "Un dato curioso, histórico o cultural sorprendente sobre el lugar. Debe ser fácil de leer en el móvil (máximo 60 palabras)",
          "tipo": "Clasifica la curiosidad eligiendo EXACTAMENTE uno de estos valores: [Historia, Arquitectura, Personaje, Evento, Dato Curioso]",
          "busqueda_imagen": "3 o 4 palabras clave muy precisas EN INGLÉS para buscar una foto real de este detalle en una API de imágenes"
        }}
        """

        try:
            respuesta = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            
            texto_ia = respuesta.text.strip()

            if texto_ia.startswith("```json"):
                texto_ia = texto_ia[7:-3].strip()
            elif texto_ia.startswith("```"):
                texto_ia = texto_ia[3:-3].strip()

            datos_curiosidad = json.loads(texto_ia)
            return datos_curiosidad

        except json.JSONDecodeError:
            raise ValueError("Error de formato: La IA no devolvió un JSON válido.")
        except Exception as e:
            raise Exception(f"Error al comunicarse con la API de IA: {str(e)}")