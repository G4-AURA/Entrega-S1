from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from .models import Ruta, Parada

MAX_RUTAS_PAGE_SIZE = 100

@require_GET
@login_required
def rutas_catalogo(request):
    try:
        limit = int(request.GET.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
        
    try:
        page_number = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page_number = 1

    tipo = request.GET.get("tipo")

    rutas_qs = (
        Ruta.objects.select_related("guia")
        .prefetch_related(
            Prefetch('paradas', queryset=Parada.objects.all()) 
        )
        .filter(guia__user__user=request.user)
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
        })

    response_data = {
        "results": data,
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages,
        "total_items": paginator.count
    }

    response = JsonResponse(response_data, safe=False, json_dumps_params={'ensure_ascii': False})
    response['Content-Type'] = 'application/json; charset=utf-8'
    return response


@require_GET
def catalogo_view(request):
    """Vista que renderiza la página del catálogo de rutas"""
    return render(request, 'rutas/catalogo.html')


@login_required
@require_http_methods(["POST"])
def eliminar_ruta_view(request, ruta_id):
    ruta = get_object_or_404(
        Ruta,
        id=ruta_id,
        guia__user__user=request.user,
    )
    ruta.delete()
    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["GET", "POST"])
def ruta_detalle_view(request, ruta_id):
    ruta = get_object_or_404(
        Ruta.objects.select_related("guia").prefetch_related("paradas"),
        id=ruta_id,
        guia__user__user=request.user,
    )

    allowed_moods = {value for value, _ in Ruta.Mood.choices}
    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "title":
            new_title = (request.POST.get("titulo") or "").strip()
            new_description = (request.POST.get("descripcion") or "").strip()
            if new_title:
                ruta.titulo = new_title
                ruta.descripcion = new_description
                ruta.save(update_fields=["titulo", "descripcion"])
                return redirect(f"{request.path}?title_updated=1")
            return redirect(f"{request.path}?title_error=1")

        if form_type == "meta":
            try:
                duracion_horas = float((request.POST.get("duracion_horas") or "").strip())
                num_personas = int((request.POST.get("num_personas") or "").strip())
            except (TypeError, ValueError):
                return redirect(f"{request.path}?meta_error=1")

            nivel_exigencia = (request.POST.get("nivel_exigencia") or "").strip()
            exigencias_validas = {value for value, _ in Ruta.Exigencia.choices}

            if duracion_horas <= 0 or num_personas <= 0 or nivel_exigencia not in exigencias_validas:
                return redirect(f"{request.path}?meta_error=1")

            ruta.duracion_horas = duracion_horas
            ruta.num_personas = num_personas
            ruta.nivel_exigencia = nivel_exigencia
            ruta.save(update_fields=["duracion_horas", "num_personas", "nivel_exigencia"])
            return redirect(f"{request.path}?meta_updated=1")

        if form_type == "stop_delete":
            parada_id = request.POST.get("parada_id")
            parada = get_object_or_404(Parada, id=parada_id, ruta=ruta)
            parada.delete()

            for index, parada_restante in enumerate(ruta.paradas.order_by("orden", "id"), start=1):
                if parada_restante.orden != index:
                    parada_restante.orden = index
                    parada_restante.save(update_fields=["orden"])

            return redirect(f"{request.path}?stop_deleted=1")

        if form_type == "stop_edit":
            parada_id = request.POST.get("parada_id")
            parada = get_object_or_404(Parada, id=parada_id, ruta=ruta)

            nombre = (request.POST.get("nombre") or "").strip()
            lat_raw = (request.POST.get("lat") or "").strip()
            lon_raw = (request.POST.get("lon") or "").strip()

            if not nombre:
                return redirect(f"{request.path}?stop_error=1")

            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except (TypeError, ValueError):
                return redirect(f"{request.path}?stop_error=1")

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return redirect(f"{request.path}?stop_error=1")

            parada.nombre = nombre
            parada.coordenadas = Point(lon, lat, srid=4326)
            parada.save(update_fields=["nombre", "coordenadas"])
            return redirect(f"{request.path}?stop_updated=1")

        if form_type == "stop_add":
            nombre = (request.POST.get("nombre") or "").strip()
            lat_raw = (request.POST.get("lat") or "").strip()
            lon_raw = (request.POST.get("lon") or "").strip()

            if not nombre:
                return redirect(f"{request.path}?stop_error=1")

            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except (TypeError, ValueError):
                return redirect(f"{request.path}?stop_error=1")

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return redirect(f"{request.path}?stop_error=1")

            ultimo_orden = ruta.paradas.order_by("-orden").values_list("orden", flat=True).first() or 0
            Parada.objects.create(
                ruta=ruta,
                orden=ultimo_orden + 1,
                nombre=nombre,
                coordenadas=Point(lon, lat, srid=4326),
            )
            return redirect(f"{request.path}?stop_added=1")

        if form_type == "stop_reorder":
            raw_order = (request.POST.get("stop_order") or "").strip()
            try:
                ordered_ids = [int(value) for value in raw_order.split(",") if value.strip()]
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

            current_ids = list(ruta.paradas.values_list("id", flat=True))
            if len(ordered_ids) != len(current_ids) or set(ordered_ids) != set(current_ids):
                return redirect(f"{request.path}?stop_error=1")

            paradas_by_id = {parada.id: parada for parada in ruta.paradas.all()}
            for index, parada_id in enumerate(ordered_ids, start=1):
                parada = paradas_by_id.get(parada_id)
                if parada and parada.orden != index:
                    parada.orden = index
                    parada.save(update_fields=["orden"])

            return redirect(f"{request.path}?stop_reordered=1")

        if form_type == "mood":
            selected_moods = request.POST.getlist("mood")
            cleaned_moods = [mood for mood in selected_moods if mood in allowed_moods]
            ruta.mood = cleaned_moods
            ruta.save(update_fields=["mood"])
            return redirect(f"{request.path}?mood_updated=1")

        return redirect(request.path)

    paradas = sorted(ruta.paradas.all(), key=lambda parada: parada.orden)

    paradas_json = []
    for parada in paradas:
        if parada.coordenadas:
            coordenadas = [parada.coordenadas.y, parada.coordenadas.x]
        else:
            coordenadas = None

        paradas_json.append(
            {
                "id": parada.id,
                "orden": parada.orden,
                "nombre": parada.nombre,
                "coordenadas": coordenadas,
            }
        )

    context = {
        "ruta": ruta,
        "paradas": paradas,
        "paradas_json": paradas_json,
        "mood_choices": Ruta.Mood.choices,
        "mood_updated": request.GET.get("mood_updated") == "1",
        "title_updated": request.GET.get("title_updated") == "1",
        "title_error": request.GET.get("title_error") == "1",
        "meta_updated": request.GET.get("meta_updated") == "1",
        "meta_error": request.GET.get("meta_error") == "1",
        "stop_updated": request.GET.get("stop_updated") == "1",
        "stop_deleted": request.GET.get("stop_deleted") == "1",
        "stop_added": request.GET.get("stop_added") == "1",
        "stop_reordered": request.GET.get("stop_reordered") == "1",
        "stop_error": request.GET.get("stop_error") == "1",
        "exigencia_choices": Ruta.Exigencia.choices,
    }
    return render(request, "rutas/detalle_ruta.html", context)
