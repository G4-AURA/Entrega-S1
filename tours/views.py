"""
tours/views.py

Vistas delgadas: validan HTTP y delegan al módulo services.

Roles:
  - Guía    → autenticado con Django Auth (@login_required)
  - Turista → siempre anónimo, identificado por alias + cookie de sesión Django
"""
import json

from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from rutas.models import Ruta

from . import services
from .models import SesionTour, TuristaSesion, UbicacionVivo

def _json_error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _render_join_error(request, message: str, status: int):
    return render(request, "tours/join_error.html", {"error": message}, status=status)


def _service_error_response(exc: services.TourServiceError) -> JsonResponse:
    return _json_error(exc.message, exc.status_code)


def _es_guia_de_ruta(user, ruta: Ruta) -> bool:
    try:
        return ruta.guia.user.user == user
    except AttributeError:
        return False


# ===========================================================================
# TURISTAS ANÓNIMOS
# Flujo único: /live/code/<codigo>/ → alias → /live/<token>/mapa/
# ===========================================================================

def join_tour_by_code(request, codigo):
    """
    Punto de entrada para turistas. Resuelve el código legible al token UUID
    interno y redirige. El código es insensible a mayúsculas/minúsculas.
    """
    sesion = SesionTour.objects.filter(codigo_acceso=codigo.upper()).first()
    if not sesion:
        return _render_join_error(
            request,
            "No existe una sesión con ese código de acceso.",
            404,
        )

    try:
        services.validar_sesion_no_finalizada(sesion, "unirse a esta sesión")
    except services.TourServiceError as exc:
        return _render_join_error(
            request,
            exc.message,
            exc.status_code,
        )

    return redirect("tours:join_tour", token=sesion.token)


@require_http_methods(["GET", "POST"])
def join_tour(request, token):
    """
    GET:  Formulario de alias.
    POST: Crea/reactiva el turista anónimo y redirige al mapa.
    """
    sesion = SesionTour.objects.filter(token=token).first()
    if not sesion:
        return _render_join_error(
            request,
            "La sesión solicitada no existe.",
            404,
        )

    try:
        services.validar_sesion_no_finalizada(sesion, "unirse a esta sesión")
    except services.TourServiceError as exc:
        return _render_join_error(
            request,
            exc.message,
            exc.status_code,
        )

    if request.method == "GET":
        turista = services.obtener_turista_anonimo(request)
        if turista and TuristaSesion.objects.filter(
            turista=turista, sesion_tour=sesion, activo=True
        ).exists():
            return redirect("tours:mapa_turista_anonimo", token=token)

    if request.method == "POST":
        alias = request.POST.get("alias", "").strip()

        if len(alias) < 2:
            return render(
                request,
                "tours/join_tour.html",
                {"sesion": sesion, "error": "El alias debe tener al menos 2 caracteres."},
                status=400,
            )
        if len(alias) > 50:
            return render(
                request,
                "tours/join_tour.html",
                {"sesion": sesion, "error": "El alias no puede exceder 50 caracteres."},
                status=400,
            )

        turista_id_cookie = request.session.get("turista_id")
        try:
            turista, error = services.unir_turista_anonimo(
                sesion,
                alias,
                turista_id_cookie,
            )
        except services.SesionFinalizadaError as exc:
            return _render_join_error(request, exc.message, exc.status_code)
        except services.TourServiceError as exc:
            return render(
                request,
                "tours/join_tour.html",
                {"sesion": sesion, "error": exc.message},
                status=exc.status_code,
            )

        if error:
            return render(
                request,
                "tours/join_tour.html",
                {"sesion": sesion, "error": error},
                status=409,
            )

        request.session["turista_id"] = turista.id
        request.session["turista_alias"] = turista.alias
        return redirect("tours:mapa_turista_anonimo", token=token)

    return render(request, "tours/join_tour.html", {"sesion": sesion})


def mapa_turista_anonimo(request, token):
    """
    Mapa en vivo para el turista anónimo verificado por cookie.
    """
    sesion = SesionTour.objects.filter(token=token).first()
    if not sesion:
        return _render_join_error(
            request,
            "La sesión solicitada no existe.",
            404,
        )

    try:
        services.validar_sesion_no_finalizada(sesion, "acceder al mapa en vivo")
    except services.TourServiceError as exc:
        return _render_join_error(request, exc.message, exc.status_code)

    turista = services.obtener_turista_anonimo(request)
    if not turista:
        return redirect("tours:join_tour", token=token)

    if not TuristaSesion.objects.filter(
        turista=turista,
        sesion_tour=sesion,
        activo=True,
    ).exists():
        return redirect("tours:join_tour", token=token)

    paradas_json = services.serializar_paradas(sesion)

    return render(
        request,
        "turista/turista_mapa.html",
        {
            "sesion":              sesion,
            "turista":             turista,
            "paradas":             sesion.ruta.paradas.all(),
            "paradas_json":        paradas_json,
            # Geometría pre-calculada en BD. None si la ruta aún no tiene
            # geometría guardada (p.ej. < 2 paradas o sin ejecutar recalcular_rutas).
            "geometria_ruta_json": sesion.ruta.geometria_ruta_coords,
            "current_user_name":   turista.alias,
        },
    )


# ===========================================================================
# GUÍAS (requieren @login_required)
# ===========================================================================

@login_required
@require_http_methods(["GET"])
def crear_sesion(request):
    """
    Crea una SesionTour para la ruta indicada en ?ruta_id=X.
    """
    ruta_id_raw = request.GET.get("ruta_id")
    if not ruta_id_raw:
        return JsonResponse({"error": "Parámetro ruta_id requerido."}, status=400)

    try:
        ruta_id = int(ruta_id_raw)
    except (TypeError, ValueError):
        return _json_error("Parámetro ruta_id inválido.", 400)

    ruta = get_object_or_404(Ruta, id=ruta_id)

    if not _es_guia_de_ruta(request.user, ruta):
        return JsonResponse(
            {"error": "No autorizado para crear sesión para esta ruta."}, status=403
        )

    sesion = SesionTour.objects.create(
        codigo_acceso=services.generar_codigo_unico(),
        estado=SesionTour.PENDIENTE,
        fecha_inicio=timezone.now(),
        ruta=ruta,
    )

    return redirect("tours:guia_sesion", sesion_id=sesion.id)


@login_required
def guia_sesion(request, sesion_id):
    """Panel de control del guía para una sesión activa."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)
    if not services.es_guia_de_sesion(request.user, sesion):
        return _json_error("No autorizado.", 403)

    return render(request, "tours/guia_sesion.html", {"sesion": sesion})


@login_required
@require_POST
def iniciar_tour(request, sesion_id):
    """Transiciona la sesión de PENDIENTE → EN_CURSO."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    try:
        services.validar_guia_de_sesion(request.user, sesion, "iniciar el tour")
        services.iniciar_sesion(sesion)
    except services.TourServiceError as exc:
        return _service_error_response(exc)

    return JsonResponse(
        {
            "message": "Tour iniciado correctamente.",
            "sesion_id": sesion.id,
            "estado": sesion.estado,
            "codigo_acceso": sesion.codigo_acceso,
        }
    )


@login_required
@require_POST
def regenerar_codigo(request, sesion_id):
    """Genera un nuevo codigo_acceso para que el guía lo comparta."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    try:
        services.validar_guia_de_sesion(
            request.user,
            sesion,
            "regenerar el código de acceso",
        )
        services.validar_sesion_no_finalizada(sesion, "regenerar el código de acceso")
    except services.TourServiceError as exc:
        return _service_error_response(exc)

    sesion.codigo_acceso = services.generar_codigo_unico()
    sesion.save(update_fields=["codigo_acceso"])
    return JsonResponse({"codigo_acceso": sesion.codigo_acceso})


@login_required
@require_POST
def cerrar_acceso(request, sesion_id):
    """Finaliza la sesión y desactiva a todos los participantes."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    try:
        services.validar_guia_de_sesion(request.user, sesion, "cerrar el acceso")
        services.cerrar_sesion(sesion)
    except services.TourServiceError as exc:
        return _service_error_response(exc)

    return JsonResponse({"status": "cerrado", "estado": sesion.estado})


@login_required
@require_GET
def participantes_sesion(request, sesion_id):
    """Lista de turistas activos en la sesión (solo para el guía)."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    try:
        services.validar_guia_de_sesion(
            request.user,
            sesion,
            "consultar participantes",
        )
    except services.TourServiceError as exc:
        return _service_error_response(exc)

    participantes = (
        TuristaSesion.objects.filter(sesion_tour=sesion, activo=True)
        .select_related("turista")
        .values("turista__id", "turista__alias", "fecha_union")
    )

    return JsonResponse(
        {
            "participantes": [
                {
                    "id": p["turista__id"],
                    "alias": p["turista__alias"],
                    "fecha_union": p["fecha_union"].isoformat(),
                }
                for p in participantes
            ]
        }
    )


@login_required
def mapa_guia(request, sesion_id):
    """
    Mapa en vivo para el guía autenticado.
    Ruta exclusiva del guía — omite el formulario de alias de turistas.
    """
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    try:
        services.validar_guia_de_sesion(request.user, sesion, "acceder al mapa en vivo")
        services.validar_sesion_no_finalizada(sesion, "acceder al mapa en vivo")
    except services.TourServiceError as exc:
        return _service_error_response(exc)

    paradas_json = services.serializar_paradas(sesion)

    return render(
        request,
        "turista/turista_mapa.html",
        {
            "sesion":              sesion,
            "paradas":             sesion.ruta.paradas.all(),
            "paradas_json":        paradas_json,
            "geometria_ruta_json": sesion.ruta.geometria_ruta_coords,
            "es_guia":             True,
            "current_user_name":   request.user.username,
        },
    )


# ===========================================================================
# UBICACIÓN (exclusivo del guía)
# ===========================================================================

@login_required
@require_POST
def registrar_ubicacion(request):
    """Registra la posición GPS del guía autenticado."""
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)

    latitud   = body.get("latitud")
    longitud  = body.get("longitud")
    sesion_id = body.get("sesion_id")

    if any(v is None for v in (latitud, longitud, sesion_id)):
        return JsonResponse(
            {"error": "Los campos sesion_id, latitud y longitud son obligatorios."},
            status=400,
        )

    try:
        latitud, longitud = float(latitud), float(longitud)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Latitud/longitud deben ser numéricas."}, status=400)

    try:
        sesion_id = int(sesion_id)
    except (TypeError, ValueError):
        return _json_error("El campo sesion_id debe ser numérico.", 400)

    if not (-90 <= latitud <= 90) or not (-180 <= longitud <= 180):
        return JsonResponse({"error": "Coordenadas fuera de rango válido."}, status=400)

    sesion = get_object_or_404(SesionTour, id=sesion_id)

    try:
        services.validar_guia_de_sesion(
            request.user,
            sesion,
            "registrar ubicaciones",
        )
        services.validar_sesion_en_curso(sesion, "registrar ubicaciones")
    except services.TourServiceError as exc:
        return _service_error_response(exc)

    ubicacion = UbicacionVivo.objects.create(
        coordenadas=Point(longitud, latitud, srid=4326),
        timestamp=timezone.now(),
        sesion_tour=sesion,
        usuario=request.user,
    )

    return JsonResponse(
        {
            "ubicacion_id": ubicacion.id,
            "sesion_id":    sesion.id,
            "latitud":      latitud,
            "longitud":     longitud,
            "timestamp":    ubicacion.timestamp.isoformat(),
        },
        status=201,
    )


@require_GET
def obtener_ubicacion_guia(request, sesion_id):
    """Última posición GPS del guía (polling desde el mapa del turista)."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.tiene_acceso_a_sesion(request, sesion):
        return _json_error("Acceso denegado.", 403)

    try:
        services.validar_sesion_en_curso(sesion, "consultar la ubicación del guía")
    except services.TourServiceError as exc:
        return _service_error_response(exc)

    try:
        guia_user = sesion.ruta.guia.user.user
    except AttributeError:
        return _json_error("No se pudo identificar al guía de esta ruta.", 404)

    ultima_ubi = (
        UbicacionVivo.objects.filter(sesion_tour=sesion, usuario=guia_user)
        .order_by("-timestamp")
        .first()
    )

    if ultima_ubi and ultima_ubi.coordenadas:
        return JsonResponse(
            {
                "available": True,
                "lat":       ultima_ubi.coordenadas.y,
                "lng":       ultima_ubi.coordenadas.x,
                "timestamp": ultima_ubi.timestamp.isoformat(),
            }
        )

    return JsonResponse(
        {
            "available": False,
            "lat": None,
            "lng": None,
            "timestamp": None,
            "message": "El guía aún no ha compartido su ubicación.",
        }
    )


# ===========================================================================
# CHAT (accesible a turistas anónimos y al guía)
# ===========================================================================

@require_POST
def enviar_mensaje(request, sesion_id):
    """Envía un mensaje. Acepta turistas anónimos (cookie) y el guía (auth)."""
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)

    texto_raw = body.get("texto", "")
    if not isinstance(texto_raw, str):
        texto_raw = str(texto_raw)
    texto = texto_raw.strip()

    if not texto:
        return JsonResponse({"error": "El campo texto no puede estar vacío."}, status=400)

    if len(texto) > 2000:
        return _json_error("El mensaje no puede exceder 2000 caracteres.", 400)

    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.tiene_acceso_a_sesion(request, sesion):
        return _json_error("Acceso denegado.", 403)

    try:
        services.validar_sesion_en_curso(sesion, "enviar mensajes")
    except services.TourServiceError as exc:
        return _service_error_response(exc)

    remitente_user, remitente_turista, nombre_remitente, error = (
        services.determinar_remitente(request, sesion)
    )
    if error:
        return _json_error(error, 403)

    mensaje = services.crear_mensaje(
        sesion,
        remitente_user,
        remitente_turista,
        nombre_remitente,
        texto,
    )

    return JsonResponse(
        {
            "status": "ok",
            "id": mensaje.id,
            "nombre_remitente": mensaje.nombre_remitente,
            "texto": mensaje.texto,
            "momento": mensaje.momento.isoformat(),
        },
        status=201,
    )


@require_GET
def obtener_mensajes(request, sesion_id):
    """Devuelve los mensajes de la sesión, con filtro opcional por `desde`."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.tiene_acceso_a_sesion(request, sesion):
        return _json_error("Acceso denegado.", 403)

    try:
        services.validar_sesion_en_curso(sesion, "consultar mensajes")
    except services.TourServiceError as exc:
        return _service_error_response(exc)

    desde_str = request.GET.get("desde")
    qs = sesion.mensajes.all().order_by("momento")

    if desde_str:
        desde_dt = parse_datetime(desde_str)
        if not desde_dt:
            return _json_error(
                "Parámetro 'desde' inválido. Usa formato ISO 8601.",
                400,
            )
        if timezone.is_naive(desde_dt):
            desde_dt = timezone.make_aware(
                desde_dt,
                timezone.get_current_timezone(),
            )
        qs = qs.filter(momento__gt=desde_dt)

    mensajes = [
        {
            "id":               m.id,
            "nombre_remitente": m.nombre_remitente,
            "texto":            m.texto,
            "momento":          m.momento.isoformat(),
        }
        for m in qs
    ]

    return JsonResponse({"mensajes": mensajes})