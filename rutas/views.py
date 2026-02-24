from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Ruta


@require_GET
def rutas_catalogo(request):
    rutas = (
        Ruta.objects.select_related("guia", "guia__user", "guia__user__user")
        .prefetch_related("paradas")
        .order_by("id")
    )

    data = []
    for ruta in rutas:
        guia_username = None
        guia_id = None
        if ruta.guia and ruta.guia.user and ruta.guia.user.user:
            guia_username = ruta.guia.user.user.username
            guia_id = ruta.guia.id

        paradas_data = []
        for parada in ruta.paradas.all().order_by("orden"):
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

    return JsonResponse(data, safe=False)
