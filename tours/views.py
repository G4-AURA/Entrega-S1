"""
tours/views.py

Vistas delgadas: validan HTTP y delegan al mÃ³dulo services.

Roles:
  - GuÃ­a    â†’ autenticado con Django Auth (@login_required)
  - Turista â†’ siempre anÃ³nimo, identificado por alias + cookie de sesiÃ³n Django
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
from .models import MensajeChat, SesionTour, Turista, TuristaSesion, UbicacionVivo


def _render_ruta_no_autorizada(request):
    return render(
        request,
        "tours/join_error.html",
        {
            "error": "Estas accediendo a una ruta que no es tuya.",
            "show_contact_hint": False,
        },
        status=403,
    )


# ===========================================================================
# TURISTAS ANÃ“NIMOS
# Flujo Ãºnico: /live/code/<codigo>/ â†’ alias â†’ /live/<token>/mapa/
# ===========================================================================

def join_tour_by_code(request, codigo):
    """
    Punto de entrada para turistas. Resuelve el cÃ³digo legible al token UUID
    interno y redirige. El cÃ³digo es insensible a mayÃºsculas/minÃºsculas.
    """
    sesion = get_object_or_404(SesionTour, codigo_acceso=codigo.upper())

    if sesion.esta_finalizada:
        return render(
            request,
            "tours/join_error.html",
            {"error": "Esta sesiÃ³n ya ha finalizado."},
            status=410,
        )

    return redirect("tours:join_tour", token=sesion.token)


def join_tour(request, token):
    """
    GET:  Formulario de alias.
    POST: Crea/reactiva el turista anÃ³nimo y redirige al mapa.
    """
    sesion = get_object_or_404(SesionTour, token=token)

    if sesion.esta_finalizada:
        return render(
            request,
            "tours/join_error.html",
            {"error": "Esta sesiÃ³n ya ha finalizado."},
            status=410,
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
            )
        if len(alias) > 50:
            return render(
                request,
                "tours/join_tour.html",
                {"sesion": sesion, "error": "El alias no puede exceder 50 caracteres."},
            )

        turista_id_cookie = request.session.get("turista_id")
        turista, error = services.unir_turista_anonimo(sesion, alias, turista_id_cookie)

        if error:
            return render(
                request, "tours/join_tour.html", {"sesion": sesion, "error": error}
            )

        request.session["turista_id"] = turista.id
        request.session["turista_alias"] = turista.alias
        return redirect("tours:mapa_turista_anonimo", token=token)

    return render(request, "tours/join_tour.html", {"sesion": sesion})


def mapa_turista_anonimo(request, token):
    """
    Mapa en vivo para el turista anÃ³nimo verificado por cookie.
    """
    sesion = get_object_or_404(SesionTour, token=token)

    turista = services.obtener_turista_anonimo(request)
    if not turista:
        return redirect("tours:join_tour", token=token)

    if not TuristaSesion.objects.filter(turista=turista, sesion_tour=sesion).exists():
        return redirect("tours:join_tour", token=token)

    snapshot = services.get_route_snapshot(sesion)

    return render(
        request,
        "turista/turista_mapa.html",
        {
            "sesion":              sesion,
            "turista":             turista,
            "paradas":             snapshot["paradas"],
            "paradas_json":        json.dumps(snapshot["paradas"]),
            "geometria_ruta_json": snapshot["geometria_ruta"],
            "current_user_name":   turista.alias,
        },
    )


# ===========================================================================
# GUÃAS (requieren @login_required)
# ===========================================================================

@login_required
@require_http_methods(["GET"])
def crear_sesion(request):
    """
    Crea una SesionTour para la ruta indicada en ?ruta_id=X.
    """
    ruta_id = request.GET.get("ruta_id")
    if not ruta_id:
        return JsonResponse({"error": "ParÃ¡metro ruta_id requerido."}, status=400)

    ruta = get_object_or_404(Ruta, id=ruta_id)

    class _RutaProxy:
        pass
    proxy = _RutaProxy()
    proxy.ruta = ruta  # type: ignore

    try:
        es_guia = ruta.guia.user.user == request.user
    except AttributeError:
        es_guia = False

    if not es_guia:
        return _render_ruta_no_autorizada(request)

    sesion = SesionTour.objects.create(
        codigo_acceso=services.generar_codigo_unico(),
        estado=SesionTour.PENDIENTE,
        fecha_inicio=timezone.now(),
        ruta=ruta,
    )
    services.set_route_snapshot(sesion)
    return redirect("tours:guia_sesion", sesion_id=sesion.id)


@login_required
def guia_sesion(request, sesion_id):
    """Panel de control del guÃ­a para una sesiÃ³n activa."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return _render_ruta_no_autorizada(request)

    return render(request, "tours/guia_sesion.html", {"sesion": sesion})


@login_required
@require_POST
def iniciar_tour(request, sesion_id):
    """Transiciona la sesiÃ³n de PENDIENTE â†’ EN_CURSO."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if sesion.esta_finalizada:
        return JsonResponse(
            {"error": "No se puede iniciar una sesiÃ³n finalizada."}, status=400
        )

    services.iniciar_sesion(sesion)

    return JsonResponse(
        {
            "message": "Tour iniciado correctamente.",
            "sesion_id": sesion.id,
            "estado": sesion.estado,
            "codigo_acceso": sesion.codigo_acceso,
            "fecha_inicio": sesion.fecha_inicio.isoformat(),
        }
    )


@require_GET
def estado_cronometro(request, sesion_id):
    """Estado compartido del cronómetro para guía y turistas de la sesión."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.tiene_acceso_a_sesion(request, sesion):
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    return JsonResponse(
        {
            "estado": sesion.estado,
            "fecha_inicio": sesion.fecha_inicio.isoformat() if sesion.fecha_inicio else None,
            "duracion_horas": sesion.ruta.duracion_horas,
            "parada_actual_id": sesion.parada_actual_id,
        }
    )


@login_required
@require_POST
def seleccionar_parada_actual(request, sesion_id):
    """Permite al guía fijar la parada actual de la sesión."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)

    parada_id = body.get("parada_id")
    if parada_id is None:
        return JsonResponse({"error": "El campo parada_id es obligatorio."}, status=400)

    try:
        parada_id = int(parada_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "parada_id debe ser un entero."}, status=400)

    parada = sesion.ruta.paradas.filter(id=parada_id).first()
    if not parada:
        return JsonResponse({"error": "La parada no pertenece a la ruta de la sesión."}, status=400)

    sesion.parada_actual = parada
    sesion.save(update_fields=["parada_actual"])
    services.set_route_snapshot(sesion)

    return JsonResponse(
        {
            "status": "ok",
            "sesion_id": sesion.id,
            "parada_actual_id": sesion.parada_actual_id,
        }
    )
@login_required
@require_POST
def regenerar_codigo(request, sesion_id):
    """Genera un nuevo codigo_acceso para que el guÃ­a lo comparta."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    sesion.codigo_acceso = services.generar_codigo_unico()
    sesion.save(update_fields=["codigo_acceso"])
    return JsonResponse({"codigo_acceso": sesion.codigo_acceso})


@login_required
@require_POST
def cerrar_acceso(request, sesion_id):
    """Finaliza la sesiÃ³n y desactiva a todos los participantes."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    services.cerrar_sesion(sesion)
    return JsonResponse({"status": "cerrado"})


@login_required
@require_GET
def participantes_sesion(request, sesion_id):
    """Lista de turistas activos en la sesiÃ³n (solo para el guÃ­a)."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

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
    Mapa en vivo para el guÃ­a autenticado.
    Ruta exclusiva del guÃ­a â€” omite el formulario de alias de turistas.
    """
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return _render_ruta_no_autorizada(request)

    snapshot = services.get_route_snapshot(sesion)

    return render(
        request,
        "turista/turista_mapa.html",
        {
            "sesion":              sesion,
            "paradas":             snapshot["paradas"],
            "paradas_json":        json.dumps(snapshot["paradas"]),
            "geometria_ruta_json": snapshot["geometria_ruta"],
            "es_guia":             True,
            "current_user_name":   request.user.username,
        },
    )


# ===========================================================================
# UBICACIÃ“N (exclusivo del guÃ­a)
# ===========================================================================

@login_required
@require_POST
def registrar_ubicacion(request):
    """Registra la posiciÃ³n GPS del guÃ­a autenticado."""
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invÃ¡lido."}, status=400)

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
        return JsonResponse({"error": "Latitud/longitud deben ser numÃ©ricas."}, status=400)

    if not (-90 <= latitud <= 90) or not (-180 <= longitud <= 180):
        return JsonResponse({"error": "Coordenadas fuera de rango vÃ¡lido."}, status=400)

    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse(
            {"error": "Solo el guÃ­a puede registrar ubicaciones."}, status=403
        )

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
    """Ãšltima posiciÃ³n GPS del guÃ­a (polling desde el mapa del turista)."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    try:
        guia_user = sesion.ruta.guia.user.user
    except AttributeError:
        return JsonResponse(
            {"error": "No se pudo identificar al guÃ­a de esta ruta."}, status=404
        )

    ultima_ubi = (
        UbicacionVivo.objects.filter(sesion_tour=sesion, usuario=guia_user)
        .order_by("-timestamp")
        .first()
    )

    if ultima_ubi and ultima_ubi.coordenadas:
        return JsonResponse(
            {
                "lat":       ultima_ubi.coordenadas.y,
                "lng":       ultima_ubi.coordenadas.x,
                "timestamp": ultima_ubi.timestamp.isoformat(),
            }
        )

    return JsonResponse({"error": "El guÃ­a aÃºn no ha compartido su ubicaciÃ³n."}, status=404)


# ===========================================================================
# CHAT (accesible a turistas anÃ³nimos y al guÃ­a)
# ===========================================================================

@require_POST
def enviar_mensaje(request, sesion_id):
    """EnvÃ­a un mensaje. Acepta turistas anÃ³nimos (cookie) y el guÃ­a (auth)."""
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invÃ¡lido."}, status=400)

    texto = body.get("texto", "").strip()
    if not texto:
        return JsonResponse({"error": "El campo texto no puede estar vacÃ­o."}, status=400)

    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.tiene_acceso_a_sesion(request, sesion):
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    remitente_user, remitente_turista, nombre_remitente, error_remitente = services.determinar_remitente(
        request, sesion
    )
    if error_remitente:
        return JsonResponse({"error": error_remitente}, status=403)

    mensaje = services.crear_mensaje(
        sesion=sesion,
        remitente_user=remitente_user,
        remitente_turista=remitente_turista,
        nombre_remitente=nombre_remitente,
        texto=texto,
    )

    return JsonResponse(
        {
            "id": mensaje.id,
            "status": "ok",
            "nombre_remitente": mensaje.nombre_remitente,
            "texto": mensaje.texto,
            "momento": mensaje.momento.isoformat(),
        },
        status=201,
    )


@require_GET
def obtener_mensajes(request, sesion_id):
    """Devuelve los mensajes de la sesiÃ³n, con filtro opcional por `desde`."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.tiene_acceso_a_sesion(request, sesion):
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    desde_str = request.GET.get("desde")
    qs = MensajeChat.objects.filter(sesion_tour=sesion).order_by("momento")

    if desde_str:
        desde_dt = parse_datetime(desde_str)
        if desde_dt:
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

    return JsonResponse({"mensajes": mensajes, "total": len(mensajes)})



