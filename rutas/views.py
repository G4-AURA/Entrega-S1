from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import Ruta, Parada

MAX_RUTAS_PAGE_SIZE = 100

@require_GET
def rutas_catalogo(request):
    try:
        limit = int(request.GET.get("limit", MAX_RUTAS_PAGE_SIZE))
    
    except (TypeError, ValueError):
        limit = MAX_RUTAS_PAGE_SIZE
    
    if limit <= 0:
        limit = MAX_RUTAS_PAGE_SIZE
    
    elif limit > MAX_RUTAS_PAGE_SIZE:
        limit = MAX_RUTAS_PAGE_SIZE
    
    try:
        offset = int(request.GET.get("offset", 0))
    
    except (TypeError, ValueError):
        offset = 0
    
    if offset < 0:
        offset = 0
    
    rutas = (
        Ruta.objects.select_related("guia")
        .prefetch_related(
            Prefetch('paradas', queryset=Parada.objects.order_by('orden'))
        )
        .order_by("id")
    )[offset:offset + limit]

    data = []
    for ruta in rutas:
        guia_username = None
        guia_id = None
        
        try:
            if ruta.guia:
                guia_id = ruta.guia.id
                if ruta.guia.user:
                    guia_username = ruta.guia.user.user.username
        except Exception:
            pass

        paradas_data = []
        for parada in ruta.paradas.all():
            coords = None
            if parada.coordenadas:
                coords = {
                    "lat": parada.coordenadas.y,
                    "lng": parada.coordenadas.x,
                }

            paradas_data.append(
                {
                    "id": parada.id,
                    "orden": parada.orden,
                    "nombre": parada.nombre,
                    "coordenadas": coords,
                }
            )

        data.append(
            {
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
            }
        )

    response = JsonResponse(data, safe=False, json_dumps_params={'ensure_ascii': False})
    response['Content-Type'] = 'application/json; charset=utf-8'
    return response


@require_GET
def catalogo_view(request):
    """Vista que renderiza la página del catálogo de rutas"""
    return render(request, 'rutas/catalogo.html')
