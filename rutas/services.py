"""
rutas/services.py

Capa con la lógica de negocio de la gestión de rutas.

Roles:
  - Guías: siempre autenticados via Django Auth. Solo pueden gestionar sus propias rutas.
  - Turistas: acceso completamente denegado a la gestión de rutas.
  - Anónimo: acceso completamente denegado a la gestión de rutas.
"""

from django.contrib.gis.geos import Point
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Prefetch

from .models import Ruta, Parada

from tours.models import SESION_TOUR


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

        # Buscar sesión activa para esta ruta
        sesion_activa = SESION_TOUR.objects.filter(
            ruta=ruta,
            estado__in=['pendiente', 'en_curso']
        ).first()
        
        sesion_activa_id = sesion_activa.id if sesion_activa else None

        paradas_en_memoria = list(ruta.paradas.all())
        paradas_en_memoria.sort(key=lambda p: p.orden)

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
            "guia": {
                "id": guia_id,
                "username": guia_username,
            },
            "paradas": paradas_data,
            "sesion_activa_id": sesion_activa_id,
        })

    return {
        "results": data,
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages,
        "total_items": paginator.count
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

def obtener_paradas_json(paradas):
    """Mapea una lista de objetos Parada a una estructura JSON-friendly."""
    paradas_json = []
    for parada in paradas:
        coordenadas = [parada.coordenadas.y, parada.coordenadas.x] if parada.coordenadas else None
        paradas_json.append({
            "id": parada.id,
            "orden": parada.orden,
            "nombre": parada.nombre,
            "coordenadas": coordenadas,
        })
    return paradas_json