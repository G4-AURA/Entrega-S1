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
import math

from django.contrib.gis.geos import Point
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import DatabaseError, IntegrityError
from django.db.models import Prefetch
import requests
from config.gemini_keys import iter_gemini_api_keys, is_quota_or_rate_limit_error

from .models import Curiosidad, Parada, Ruta
from tours.models import SESION_TOUR

logger = logging.getLogger(__name__)
MIN_DURACION_HORAS = 0.5
MAX_DURACION_HORAS = 24.0
MIN_NUM_PERSONAS = 1
MAX_NUM_PERSONAS = 50


def _es_incremento_media_hora(valor):
    return math.isclose(valor * 2, round(valor * 2), rel_tol=0.0, abs_tol=1e-9)


def _es_misma_duracion(ruta, duracion_horas):
    try:
        actual = float(ruta.duracion_horas)
    except (TypeError, ValueError):
        return False
    return math.isclose(actual, duracion_horas, rel_tol=0.0, abs_tol=1e-9)


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
        .distinct()
        .order_by("-id")
    )

    if not user.is_superuser:
        rutas_qs = rutas_qs.filter(guia__user__user=user)

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
        # El único fallo posible es AttributeError
        except AttributeError:
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
    if len(descripcion or "") > 150:
        raise ValueError("La descripción no puede superar los 150 caracteres.")
    ruta.descripcion = descripcion
    ruta.save(update_fields=["descripcion"])


def actualizar_duracion_ruta(ruta, raw_duracion):
    try:
        duracion_horas = float((raw_duracion or "").strip())
    except (TypeError, ValueError):
        raise ValueError("Valores numéricos inválidos (duración)")

    if not math.isfinite(duracion_horas):
        raise ValueError("Valores numéricos inválidos (duración)")
    if duracion_horas < MIN_DURACION_HORAS or duracion_horas > MAX_DURACION_HORAS:
        raise ValueError("Valores numéricos inválidos (duración)")
    if not _es_incremento_media_hora(duracion_horas):
        # Compatibilidad retroactiva:
        # si la ruta ya tenía una duración legacy (p. ej. 1.2h) y no se modifica,
        # permitimos guardar otros metadatos sin bloquear la edición.
        if not _es_misma_duracion(ruta, duracion_horas):
            raise ValueError("Valores numéricos inválidos (duración)")

    ruta.duracion_horas = duracion_horas
    ruta.save(update_fields=["duracion_horas"])


def actualizar_personas_ruta(ruta, raw_personas):
    try:
        num_personas = int((raw_personas or "").strip())
    except (TypeError, ValueError):
        raise ValueError("Valores numéricos inválidos (número de personas)")

    if num_personas < MIN_NUM_PERSONAS or num_personas > MAX_NUM_PERSONAS:
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
        if not math.isfinite(lat) or not math.isfinite(lon):
            raise ValueError("Coordenadas fuera de rango")
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


def añadir_parada(ruta, raw_nombre, raw_lat, raw_lon, descripcion=''):
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
        descripcion=(descripcion or "").strip()[:500],
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
    
    except DatabaseError as exc:
        logger.error(
            "GraphHopper: error de BD al persistir métricas de Ruta(id=%d): %s",
            ruta.id, exc,
        )
        return False
    except (AttributeError, TypeError) as exc:
        logger.error(
            "GraphHopper: datos de parada malformados en Ruta(id=%d): %s",
            ruta.id, exc,
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
    WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"
    WIKIMEDIA_HEADERS = {
        "User-Agent": "AURA/1.0 (academic project image lookup)"
    }

    def __init__(self):
        from google import genai
        self._genai = genai

    def generar_curiosidad(self, parada: Parada, ciudad: str = "Sevilla") -> dict:
        """
        Devuelve una curiosidad para una parada reutilizando caché en BD cuando exista.
        """
        curiosidad_cacheada = self._obtener_curiosidad_cache(parada)
        if curiosidad_cacheada:
            logger.info(
                "Curiosidad cacheada reutilizada para Parada(id=%d).",
                parada.id,
            )
            return self._serializar_curiosidad(curiosidad_cacheada)

        datos_curiosidad = self._generar_curiosidad_ia(parada=parada, ciudad=ciudad)
        curiosidad_guardada = self._guardar_curiosidad_en_cache(
            parada=parada,
            ciudad=ciudad,
            datos_curiosidad=datos_curiosidad,
        )
        return self._serializar_curiosidad(curiosidad_guardada)

    def _obtener_curiosidad_cache(self, parada: Parada) -> Curiosidad | None:
        return Curiosidad.objects.filter(parada=parada).first()

    def _serializar_curiosidad(self, curiosidad: Curiosidad) -> dict:
        return {
            "parada_id": curiosidad.parada_id,
            "ciudad": curiosidad.ciudad,
            "titulo": curiosidad.titulo,
            "texto": curiosidad.texto,
            "tipo": curiosidad.tipo,
            "imagen_url": curiosidad.imagen_url,
            "busqueda_imagen": curiosidad.imagen_url,
        }

    def _normalizar_payload_curiosidad(self, parada: Parada, datos_curiosidad: dict) -> dict:
        titulo = str(datos_curiosidad.get("titulo") or "").strip()
        if not titulo:
            titulo = f"Curiosidad sobre {parada.nombre}"
        titulo = titulo[:255]

        texto = str(datos_curiosidad.get("texto") or "").strip()
        if not texto:
            raise ValueError("Error de formato: La IA devolvió una curiosidad sin texto.")

        tipo_recibido = str(datos_curiosidad.get("tipo") or "").strip()
        tipos_validos = {valor for valor, _ in Curiosidad.TipoCuriosidad.choices}
        tipo = (
            tipo_recibido
            if tipo_recibido in tipos_validos
            else Curiosidad.TipoCuriosidad.DATO_CURIOSO
        )

        imagen_url = str(datos_curiosidad.get("imagen_url") or "").strip()
        imagen_url = imagen_url or None

        return {
            "titulo": titulo,
            "texto": texto,
            "tipo": tipo,
            "imagen_url": imagen_url,
        }

    def _guardar_curiosidad_en_cache(
        self,
        parada: Parada,
        ciudad: str,
        datos_curiosidad: dict,
    ) -> Curiosidad:
        payload = self._normalizar_payload_curiosidad(parada=parada, datos_curiosidad=datos_curiosidad)
        ciudad_limpia = (str(ciudad or "").strip() or "Sevilla")[:100]

        try:
            curiosidad, creada = Curiosidad.objects.get_or_create(
                parada=parada,
                defaults={
                    "ciudad": ciudad_limpia,
                    "titulo": payload["titulo"],
                    "texto": payload["texto"],
                    "tipo": payload["tipo"],
                    "imagen_url": payload["imagen_url"],
                },
            )
        except IntegrityError:
            curiosidad = Curiosidad.objects.get(parada=parada)
            creada = False

        if creada:
            logger.info(
                "Curiosidad generada y almacenada para Parada(id=%d).",
                parada.id,
            )
        else:
            logger.info(
                "Curiosidad ya existente detectada durante el guardado para Parada(id=%d).",
                parada.id,
            )

        return curiosidad

    def _generar_curiosidad_ia(self, parada: Parada, ciudad: str = "Sevilla") -> dict:
        """
        Genera el prompt, llama a la IA y devuelve los datos estructurados.
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
          "busqueda_imagen": "3 o 4 palabras clave muy precisas EN INGLÉS para encontrar una foto real y específica del detalle en Wikimedia Commons u otra API de imágenes"
        }}
        """

        claves = list(iter_gemini_api_keys())
        if not claves:
            raise RuntimeError('No hay API key de Gemini configurada.')

        ultimo_error_cuota: Exception | None = None
        for indice, clave in enumerate(claves, start=1):
            client = self._genai.Client(api_key=clave)
            try:
                respuesta = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )

                texto_ia = str(getattr(respuesta, 'text', '') or '').strip()

                if texto_ia.startswith("```json"):
                    texto_ia = texto_ia[7:-3].strip()
                elif texto_ia.startswith("```"):
                    texto_ia = texto_ia[3:-3].strip()

                datos_curiosidad = json.loads(texto_ia)
                busqueda_imagen = (datos_curiosidad.get("busqueda_imagen") or "").strip()
                datos_curiosidad["imagen_url"] = self._buscar_imagen_curiosidad(
                    busqueda_imagen=busqueda_imagen,
                    parada=parada,
                    ciudad=ciudad,
                )
                return datos_curiosidad

            except json.JSONDecodeError:
                raise ValueError("Error de formato: La IA no devolvió un JSON válido.")
            except (requests.RequestException, TimeoutError, ConnectionError) as e:
                raise RuntimeError(f"Error de red al comunicarse con la API de IA: {e}") from e
            except (AttributeError, KeyError, IndexError) as e:
                raise ValueError(f"Respuesta inesperada de la API de IA: {e}") from e
            except Exception as exc:
                if is_quota_or_rate_limit_error(exception=exc):
                    ultimo_error_cuota = exc
                    logger.warning(
                        'Gemini devolvió cuota/429 al generar curiosidad (clave %s/%s).',
                        indice,
                        len(claves),
                    )
                    continue
                raise

        if ultimo_error_cuota is not None:
            raise RuntimeError('Todas las API keys de Gemini agotaron cuota o devolvieron 429.') from ultimo_error_cuota

        raise RuntimeError('No se pudo generar curiosidad con Gemini.')

    def _buscar_imagen_curiosidad(self, busqueda_imagen: str, parada: Parada, ciudad: str) -> str | None:
        """
        Busca una imagen relevante en Wikimedia Commons a partir de la sugerencia
        generada por la IA. Si da error o no encuentra resultados, devuelve None.
        """
        if not busqueda_imagen:
            return None

        consultas = []
        consulta_principal = f"{busqueda_imagen} {ciudad}".strip()
        for consulta in (consulta_principal, busqueda_imagen.strip(), parada.nombre.strip()):
            if consulta and consulta not in consultas:
                consultas.append(consulta)

        for consulta in consultas:
            imagen_url = self._buscar_wikimedia(consulta)
            if imagen_url:
                return imagen_url

        logger.info(
            "Curiosidades IA: sin imagen para parada '%s' con consultas=%s",
            parada.nombre,
            consultas,
        )
        return None

    def _buscar_wikimedia(self, consulta: str) -> str | None:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": consulta,
            "gsrnamespace": 6,
            "gsrlimit": 10,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 800,
        }

        try:
            response = requests.get(
                self.WIKIMEDIA_API_URL,
                params=params,
                headers=self.WIKIMEDIA_HEADERS,
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.warning(
                "Curiosidades IA: error consultando Wikimedia para '%s': %s",
                consulta,
                exc,
            )
            return None
        
        # Solo json.JSONDecodeError es esperado
        except json.JSONDecodeError:
            logger.warning(
                "Curiosidades IA: respuesta JSON inválida de Wikimedia para '%s'",
                consulta,
            )
            return None

        pages = payload.get("query", {}).get("pages", {})
        for page in pages.values():
            titulo = (page.get("title") or "").lower()
            if not (titulo.endswith(".jpg") or titulo.endswith(".jpeg") or titulo.endswith(".png")):
                continue

            for image_info in page.get("imageinfo", []):
                image_url = image_info.get("thumburl") or image_info.get("url")
                if image_url:
                    return image_url

        return None


def _normalizar_tipo_curiosidad(tipo_ia: str) -> str:
    tipos_validos = {valor for valor, _ in Curiosidad.TipoCuriosidad.choices}
    tipo_limpio = (tipo_ia or "").strip()
    if tipo_limpio in tipos_validos:
        return tipo_limpio
    return Curiosidad.TipoCuriosidad.DATO_CURIOSO


def obtener_o_generar_curiosidad_parada(parada: Parada, ciudad: str = "Sevilla") -> tuple[Curiosidad, bool]:
    """
    Devuelve la curiosidad asociada a una parada.

    Flujo:
      1) Si ya existe en BD, se reutiliza.
      2) Si no existe, se genera con IA, se persiste y se devuelve.

    Returns:
        (curiosidad, fue_generada)
    """
    curiosidad_existente = Curiosidad.objects.filter(parada=parada).first()
    if curiosidad_existente:
        return curiosidad_existente, False

    servicio_ia = ServicioCuriosidadesIA()
    datos_ia = servicio_ia._generar_curiosidad_ia(parada=parada, ciudad=ciudad)
    curiosidad = servicio_ia._guardar_curiosidad_en_cache(
        parada=parada,
        ciudad=ciudad,
        datos_curiosidad=datos_ia,
    )

    return curiosidad, True


def generar_curiosidad_parada_preview(parada: Parada, ciudad: str = "Sevilla") -> dict:
    """
    Genera una curiosidad para previsualización sin persistir en BD.

    Se usa en UI para que el usuario pueda cancelar sin guardar cambios.
    """
    servicio_ia = ServicioCuriosidadesIA()
    datos_ia = servicio_ia._generar_curiosidad_ia(parada=parada, ciudad=ciudad)
    payload = servicio_ia._normalizar_payload_curiosidad(parada=parada, datos_curiosidad=datos_ia)
    payload["parada_id"] = parada.id
    payload["ciudad"] = (str(ciudad or "").strip() or "Sevilla")[:100]
    return payload
