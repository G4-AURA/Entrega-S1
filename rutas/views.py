from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
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
