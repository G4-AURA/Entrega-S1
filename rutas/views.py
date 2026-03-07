"""
rutas/views.py

Vistas delgadas: validan HTTP y delegan al módulo rutas/services.

Roles:
  - Guía: autenticado con Django Auth (@login_required)

Funcionalidades:
  - Gestión de rutas: listado, visualización y eliminación.
"""

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from django.core.exceptions import PermissionDenied

from .models import Ruta, Parada
from . import services

MAX_RUTAS_PAGE_SIZE = 9

# ================================================
# Método auxiliar para validar que rol sea <guía>
# ================================================

from django.core.exceptions import PermissionDenied

def es_guia(user):
    """
    Comprueba si el usuario autenticado tiene un perfil de Guia asociado.
    Ruta de modelos: User -> AuthUser (auth_profile) -> Guia (guia)
    """
    if user.is_authenticated:
        if hasattr(user, 'auth_profile') and hasattr(user.auth_profile, 'guia'):
            if user.auth_profile.guia is not None:
                return True
                
    raise PermissionDenied("Acceso denegado: área exclusiva para guías.")

# ================================================


@require_GET
@login_required
@user_passes_test(es_guia)
def rutas_catalogo(request):
    try:
        limit = int(request.GET.get("limit", 3))
        if limit > MAX_RUTAS_PAGE_SIZE:
            limit = MAX_RUTAS_PAGE_SIZE
    except (TypeError, ValueError):
        limit = 3

    try:
        page_number = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page_number = 1
    
    tipo = request.GET.get("tipo")

    response_data = services.obtener_datos_catalogo_paginado(request.user, limit, page_number, tipo)

    response = JsonResponse(response_data, safe=False, json_dumps_params={'ensure_ascii': False})
    response['Content-Type'] = 'application/json; charset=utf-8'
    return response


@require_GET
@login_required
@user_passes_test(es_guia)
def catalogo_view(request):
    """
    Vista que renderiza la página del catálogo de rutas
    """
    return render(request, 'rutas/catalogo.html')


@login_required
@require_http_methods(["POST"])
@user_passes_test(es_guia)
def eliminar_ruta_view(request, ruta_id):
    ruta = get_object_or_404(
        Ruta,
        id=ruta_id,
        guia__user__user=request.user,
    )
    services.eliminar_ruta(ruta)
    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["GET", "POST"])
@user_passes_test(es_guia)
def ruta_detalle_view(request, ruta_id):
    ruta = get_object_or_404(
        Ruta.objects.select_related("guia").prefetch_related("paradas"),
        id=ruta_id,
        guia__user__user=request.user,
    )

    # Gestión de peticiones POST (formularios de edición)
    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "title":
            try:
                services.actualizar_titulo_ruta(ruta, request.POST.get("titulo"))
                services.actualizar_descripcion_ruta(ruta, request.POST.get("descripcion"))
                return redirect(f"{request.path}?title_updated=1")
            except ValueError:
                return redirect(f"{request.path}?title_error=1")

        if form_type == "meta":
            try:
                services.actualizar_duracion_ruta(ruta, request.POST.get("duracion_horas"))
                services.actualizar_personas_ruta(ruta, request.POST.get("num_personas"))
                services.actualizar_exigencia_ruta(ruta, request.POST.get("nivel_exigencia"))
                return redirect(f"{request.path}?meta_updated=1")
            except ValueError:
                return redirect(f"{request.path}?meta_error=1")

        if form_type == "stop_delete":
            parada_id = request.POST.get("parada_id")
            parada = get_object_or_404(Parada, id=parada_id, ruta=ruta)
            services.eliminar_parada_y_reordenar(ruta, parada)
            return redirect(f"{request.path}?stop_deleted=1")

        if form_type == "stop_edit":
            parada_id = request.POST.get("parada_id")
            parada = get_object_or_404(Parada, id=parada_id, ruta=ruta)
            try:
                services.editar_parada(
                    parada,
                    request.POST.get("nombre"),
                    request.POST.get("lat"),
                    request.POST.get("lon")
                )
                return redirect(f"{request.path}?stop_updated=1")
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

        if form_type == "stop_add":
            try:
                services.añadir_parada(
                    ruta,
                    request.POST.get("nombre"),
                    request.POST.get("lat"),
                    request.POST.get("lon")
                )
                return redirect(f"{request.path}?stop_added=1")
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

        if form_type == "stop_reorder":
            try:
                services.reordenar_paradas(
                    ruta, 
                    request.POST.get("stop_order")
                )
                return redirect(f"{request.path}?stop_reordered=1")
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

        if form_type == "mood":
            services.actualizar_moods(ruta, request.POST.getlist("mood"))
            return redirect(f"{request.path}?mood_updated=1")

        return redirect(request.path)

    # Gestión de peticiones GET (renderizado de la página)
    paradas = sorted(ruta.paradas.all(), key=lambda parada: parada.orden)
    paradas_json = services.obtener_paradas_json(paradas)

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


