"""
rutas/views.py

Vistas delgadas: validan HTTP y delegan al módulo rutas/services.

Roles:
  - Guía: autenticado con Django Auth (@login_required)

S2.1-28/32: Tras cada modificación de paradas se dispara recalcular_ruta_graphhopper.
S2.1-32:    Endpoint AJAX para recalcular sin recargar la página completa.
"""
import logging

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Parada, Ruta
from . import services

logger = logging.getLogger(__name__)
MAX_RUTAS_PAGE_SIZE = 9


# ================================================
# Guardia de rol: solo guías autenticados
# ================================================

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
# Helper: recalcular GraphHopper sin bloquear
# ================================================

def _recalcular_silencioso(ruta) -> None:
    """
    Dispara el recálculo GraphHopper de forma que nunca interrumpa la vista.
    Los errores ya son capturados y logueados dentro del servicio.
    """
    try:
        services.recalcular_ruta_graphhopper(ruta)
    except Exception:
        # Última barrera: la excepción ya fue logueada en services
        logger.exception(
            "Error inesperado en recálculo externo GraphHopper para Ruta(id=%d)", ruta.id
        )


# ================================================
# CATÁLOGO
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

    response_data = services.obtener_datos_catalogo_paginado(
        request.user, limit, page_number, tipo
    )

    response = JsonResponse(
        response_data, safe=False, json_dumps_params={'ensure_ascii': False}
    )
    response['Content-Type'] = 'application/json; charset=utf-8'
    return response


@require_GET
@login_required
@user_passes_test(es_guia)
def catalogo_view(request):
    """Renderiza la página del catálogo de rutas."""
    return render(request, 'rutas/catalogo.html')


# ================================================
# ELIMINAR RUTA
# ================================================

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


# ================================================
# DETALLE Y EDICIÓN DE RUTA (S2.1-32: recálculo tras modificaciones)
# ================================================

@login_required
@require_http_methods(["GET", "POST"])
@user_passes_test(es_guia)
def ruta_detalle_view(request, ruta_id):
    ruta = get_object_or_404(
        Ruta.objects.select_related("guia").prefetch_related("paradas"),
        id=ruta_id,
        guia__user__user=request.user,
    )

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        # ── Título / descripción (sin efecto en la geometría) ─────────────────
        if form_type == "title":
            try:
                services.actualizar_titulo_ruta(ruta, request.POST.get("titulo"))
                services.actualizar_descripcion_ruta(ruta, request.POST.get("descripcion"))
                return redirect(f"{request.path}?title_updated=1")
            except ValueError:
                return redirect(f"{request.path}?title_error=1")

        # ── Metadatos numéricos (sin efecto en la geometría) ─────────────────
        if form_type == "meta":
            try:
                services.actualizar_duracion_ruta(ruta, request.POST.get("duracion_horas"))
                services.actualizar_personas_ruta(ruta, request.POST.get("num_personas"))
                services.actualizar_exigencia_ruta(ruta, request.POST.get("nivel_exigencia"))
                return redirect(f"{request.path}?meta_updated=1")
            except ValueError:
                return redirect(f"{request.path}?meta_error=1")

        # ── Eliminar parada → recalcular (S2.1-32) ───────────────────────────
        if form_type == "stop_delete":
            parada_id = request.POST.get("parada_id")
            parada = get_object_or_404(Parada, id=parada_id, ruta=ruta)
            services.eliminar_parada_y_reordenar(ruta, parada)
            _recalcular_silencioso(ruta)
            return redirect(f"{request.path}?stop_deleted=1")

        # ── Editar parada → recalcular solo si cambian coordenadas (S2.1-32) ─
        if form_type == "stop_edit":
            parada_id = request.POST.get("parada_id")
            parada = get_object_or_404(Parada, id=parada_id, ruta=ruta)

            # Guardar coordenadas antes de editar para detectar cambios
            coords_antes = (
                (parada.coordenadas.y, parada.coordenadas.x)
                if parada.coordenadas else None
            )
            try:
                services.editar_parada(
                    parada,
                    request.POST.get("nombre"),
                    request.POST.get("lat"),
                    request.POST.get("lon"),
                )
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

            # Refrescar para comparar coordenadas guardadas
            parada.refresh_from_db()
            coords_despues = (
                (parada.coordenadas.y, parada.coordenadas.x)
                if parada.coordenadas else None
            )
            if coords_antes != coords_despues:
                _recalcular_silencioso(ruta)

            return redirect(f"{request.path}?stop_updated=1")

        # ── Añadir parada → recalcular (S2.1-32) ────────────────────────────
        if form_type == "stop_add":
            try:
                services.añadir_parada(
                    ruta,
                    request.POST.get("nombre"),
                    request.POST.get("lat"),
                    request.POST.get("lon"),
                )
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

            _recalcular_silencioso(ruta)
            return redirect(f"{request.path}?stop_added=1")

        # ── Reordenar paradas → recalcular (S2.1-32) ─────────────────────────
        if form_type == "stop_reorder":
            raw_order = (request.POST.get("stop_order") or "").strip()
            try:
                ordered_ids = [int(v) for v in raw_order.split(",") if v.strip()]
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

            # Validar que los IDs coinciden con las paradas de esta ruta
            current_ids = set(ruta.paradas.values_list("id", flat=True))
            if not ordered_ids or set(ordered_ids) != current_ids:
                return redirect(f"{request.path}?stop_error=1")

            try:
                services.reordenar_paradas(ruta, ordered_ids)
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

            # El cambio de orden modifica la ruta óptima
            _recalcular_silencioso(ruta)
            return redirect(f"{request.path}?stop_reordered=1")

        # ── Etiquetas mood (sin efecto en la geometría) ───────────────────────
        if form_type == "mood":
            services.actualizar_moods(ruta, request.POST.getlist("mood"))
            return redirect(f"{request.path}?mood_updated=1")

        return redirect(request.path)

    # ── GET: construir contexto ────────────────────────────────────────────────
    # refresh_from_db garantiza que se leen los campos de GraphHopper recién guardados
    ruta.refresh_from_db()
    paradas = sorted(ruta.paradas.all(), key=lambda p: p.orden)
    paradas_json = services.obtener_paradas_json(paradas)

    context = {
        "ruta": ruta,
        "paradas": paradas,
        "paradas_json": paradas_json,
        # Geometría en formato Leaflet [[lat, lon], ...] (S2.1-31)
        "geometria_ruta_json": ruta.geometria_ruta_coords,
        # Métricas totales para el panel (S2.1-29)
        "distancia_total_km": ruta.distancia_total_km,
        "duracion_total_min": ruta.duracion_total_min,
        "mood_choices": Ruta.Mood.choices,
        "mood_updated":   request.GET.get("mood_updated")   == "1",
        "title_updated":  request.GET.get("title_updated")  == "1",
        "title_error":    request.GET.get("title_error")    == "1",
        "meta_updated":   request.GET.get("meta_updated")   == "1",
        "meta_error":     request.GET.get("meta_error")     == "1",
        "stop_updated":   request.GET.get("stop_updated")   == "1",
        "stop_deleted":   request.GET.get("stop_deleted")   == "1",
        "stop_added":     request.GET.get("stop_added")     == "1",
        "stop_reordered": request.GET.get("stop_reordered") == "1",
        "stop_error":     request.GET.get("stop_error")     == "1",
        "exigencia_choices": Ruta.Exigencia.choices,
    }
    return render(request, "rutas/detalle_ruta.html", context)


# ================================================
# API AJAX: recalcular ruta GraphHopper (S2.1-32)
# ================================================

@login_required
@require_POST
@user_passes_test(es_guia)
def recalcular_ruta_api(request, ruta_id):
    """
    Fuerza el recálculo de la geometría GraphHopper para una ruta.

    Permite al frontend actualizar el mapa y el panel de métricas dinámicamente
    sin recargar la página completa. Útil para extensiones futuras con edición AJAX.

    POST /api/rutas/<ruta_id>/recalcular/
    Response (200):
        {
          "status": "ok",
          "geometria": [[lat, lon], ...] | null,
          "distancia_total_km": "1.5" | null,
          "duracion_total_min": 23 | null,
          "segmentos": [{"parada_id": 1, "distancia_m": 300.0, "duracion_min": 4}, ...]
        }
    """
    ruta = get_object_or_404(
        Ruta,
        id=ruta_id,
        guia__user__user=request.user,
    )

    # El servicio ya maneja errores y limpia datos si hay < 2 paradas
    services.recalcular_ruta_graphhopper(ruta)

    return JsonResponse(services.serializar_resultado_graphhopper(ruta))


