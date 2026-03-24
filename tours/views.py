"""
tours/views.py

Vistas delgadas: validan HTTP y delegan al mÃ³dulo services.

Roles:
  - GuÃ­a    â†’ autenticado con Django Auth (@login_required)
  - Turista â†’ siempre anÃ³nimo, identificado por alias + cookie de sesiÃ³n Django
"""
import json
import logging
import math
import os
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from rutas.models import Curiosidad, Ruta

from . import services
from .models import MensajeChat, SesionTour, Turista, TuristaSesion, UbicacionVivo


logger = logging.getLogger(__name__)


def _distancia_haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c


def _resolver_curiosidad_cercana(sesion: SesionTour, latitud: float, longitud: float, radio_m: float = 75.0) -> dict | None:
    parada_mas_cercana = None
    distancia_minima = None

    for parada in sesion.ruta.paradas.all():
        if not parada.coordenadas:
            continue

        distancia_m = _distancia_haversine_m(
            latitud,
            longitud,
            parada.coordenadas.y,
            parada.coordenadas.x,
        )

        if distancia_m > radio_m:
            continue

        if distancia_minima is None or distancia_m < distancia_minima:
            distancia_minima = distancia_m
            parada_mas_cercana = parada

    if not parada_mas_cercana:
        return None

    curiosidad = Curiosidad.objects.filter(parada=parada_mas_cercana).first()
    if not curiosidad:
        return None

    return {
        "parada": {
            "id": parada_mas_cercana.id,
            "nombre": parada_mas_cercana.nombre,
            "orden": parada_mas_cercana.orden,
            "distancia_m": round(distancia_minima or 0.0, 2),
        },
        "curiosidad": {
            "id": curiosidad.id,
            "titulo": curiosidad.titulo,
            "texto": curiosidad.texto,
            "tipo": curiosidad.tipo,
            "ciudad": curiosidad.ciudad,
            "imagen_url": curiosidad.imagen_url,
        },
    }


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


def _render_join_error(request, mensaje: str, status: int = 400):
    return render(
        request,
        "tours/join_error.html",
        {
            "error": mensaje,
            "show_contact_hint": False,
        },
        status=status,
    )


def _json_error(mensaje: str, status: int = 400, **extra):
    payload = {"error": mensaje}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _json_internal_error():
    return _json_error("Ha ocurrido un error interno. Inténtalo de nuevo en unos minutos.", status=500)


def _get_sesion_or_json_404(sesion_id):
    sesion = SesionTour.objects.filter(id=sesion_id).first()
    if not sesion:
        return None, _json_error(f"La sesión con ID {sesion_id} no existe.", status=404)
    return sesion, None


def _render_sesion_no_activa_para_union(request):
    return _render_join_error(
        request,
        "Esta sesión aún no está activa. Espera a que el guía inicie el tour.",
        status=409,
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
    sesion = SesionTour.objects.filter(codigo_acceso=codigo.upper()).first()

    if not sesion:
        return _render_join_error(
            request,
            "El código introducido no es válido. Comprueba que lo has escrito correctamente.",
            status=404,
        )

    if sesion.esta_finalizada:
        return _render_join_error(request, "Esta sesión ya ha finalizado.", status=410)

    if not sesion.esta_activa:
        return _render_sesion_no_activa_para_union(request)

    return redirect("tours:join_tour", token=sesion.token)


def join_tour(request, token):
    """
    GET:  Formulario de alias.
    POST: Crea/reactiva el turista anÃ³nimo y redirige al mapa.
    """
    sesion = SesionTour.objects.filter(token=token).first()
    if not sesion:
        return _render_join_error(request, "La sesión no existe o el token no es válido.", status=404)

    if sesion.esta_finalizada:
        return _render_join_error(request, "Esta sesión ya ha finalizado.", status=410)

    if not sesion.esta_activa:
        return _render_sesion_no_activa_para_union(request)

    if request.method == "GET":
        turista = services.obtener_turista_anonimo(request)
        if turista and TuristaSesion.objects.filter(
            turista=turista, sesion_tour=sesion, activo=True
        ).exists():
            return redirect("tours:sala_espera", token=token)

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
        return redirect("tours:sala_espera", token=token)

    return render(request, "tours/join_tour.html", {"sesion": sesion})


def sala_espera(request, token):
    """
    Sala de espera para el turista tras unirse al tour.
 
    - Si el tour está PENDIENTE: botón deshabilitado.
    - Si el tour está EN_CURSO:  botón habilitado → redirige al mapa.
 
    El turista debe estar registrado en la sesión; si no, lo mandamos
    de vuelta al formulario de alias.
    """
    sesion = SesionTour.objects.filter(token=token).first()
    if not sesion:
        return _render_join_error(request, "La sesión no existe o el token no es válido.", status=404)
 
    if sesion.esta_finalizada:
        return _render_join_error(request, "Esta sesión ya ha finalizado.", status=410)
 
    turista = services.obtener_turista_anonimo(request)
    if not turista or not TuristaSesion.objects.filter(
        turista=turista, sesion_tour=sesion, activo=True
    ).exists():
        return redirect("tours:join_tour", token=token)
 
    return render(
        request,
        "turista/sala_espera.html",
        {
            "sesion": sesion,
            "turista": turista,
        },
    )


def mapa_turista_anonimo(request, token):
    """
    Mapa en vivo para el turista anÃ³nimo verificado por cookie.
    """
    sesion = SesionTour.objects.filter(token=token).first()
    if not sesion:
        return _render_join_error(request, "La sesión no existe o el token no es válido.", status=404)

    if sesion.esta_finalizada:
        return _render_join_error(request, "Esta sesión ya ha finalizado.", status=410)

    if not sesion.esta_activa:
        return redirect("tours:sala_espera", token=token)

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

    ruta = Ruta.objects.filter(id=ruta_id).first()
    if not ruta:
        return _json_error("La ruta indicada no existe.", status=404)

    try:
        es_guia = ruta.guia.user.user == request.user
    except AttributeError:
        es_guia = False

    if not es_guia:
        return _render_ruta_no_autorizada(request)

    try:
        sesion = SesionTour.objects.create(
            codigo_acceso=services.generar_codigo_unico(),
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )
        services.set_route_snapshot(sesion)
    except Exception:
        logger.exception("Error creando sesión para ruta %s", ruta.id)
        return _json_internal_error()

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
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    if sesion.esta_finalizada:
        return JsonResponse(
            {"error": "No se puede iniciar una sesiÃ³n finalizada."}, status=400
        )

    if sesion.estado != SesionTour.PENDIENTE:
        return JsonResponse(
            {"error": "Solo se pueden iniciar sesiones en estado pendiente."},
            status=409,
        )

    try:
        services.iniciar_sesion(sesion)
    except Exception:
        logger.exception("Error iniciando sesión %s", sesion.id)
        return _json_internal_error()

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
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

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
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

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

    try:
        sesion.parada_actual = parada
        sesion.save(update_fields=["parada_actual"])
        services.set_route_snapshot(sesion)
    except Exception:
        logger.exception("Error actualizando parada actual en sesión %s", sesion.id)
        return _json_internal_error()

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
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    try:
        sesion.codigo_acceso = services.generar_codigo_unico()
        sesion.save(update_fields=["codigo_acceso"])
    except Exception:
        logger.exception("Error regenerando código en sesión %s", sesion.id)
        return _json_internal_error()

    return JsonResponse({"codigo_acceso": sesion.codigo_acceso})


@login_required
@require_POST
def cerrar_acceso(request, sesion_id):
    """Finaliza la sesiÃ³n y desactiva a todos los participantes."""
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    if sesion.esta_finalizada:
        return JsonResponse({"error": "La sesión ya está finalizada."}, status=409)

    try:
        services.cerrar_sesion(sesion)
    except Exception:
        logger.exception("Error cerrando sesión %s", sesion.id)
        return _json_internal_error()

    return JsonResponse({"status": "cerrado"})


@login_required
@require_GET
def participantes_sesion(request, sesion_id):
    """Lista de turistas activos en la sesiÃ³n (solo para el guÃ­a)."""
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

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
    if sesion.esta_finalizada:
        return redirect("tours:guia_sesion", sesion_id=sesion.id)

    if sesion.esta_finalizada:
        return _render_join_error(request, "La sesión ya ha finalizado.", status=410)

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

    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse(
            {"error": "Solo el guÃ­a puede registrar ubicaciones."}, status=403
        )

    if sesion.esta_finalizada:
        return JsonResponse(
            {"error": "No se puede registrar ubicación en una sesión finalizada."},
            status=410,
        )

    if not sesion.esta_activa:
        return _json_error("La sesión no está activa.", status=409)

    try:
        ubicacion = UbicacionVivo.objects.create(
            coordenadas=Point(longitud, latitud, srid=4326),
            timestamp=timezone.now(),
            sesion_tour=sesion,
            usuario=request.user,
        )
    except Exception:
        logger.exception("Error registrando ubicación del guía en sesión %s", sesion.id)
        return _json_internal_error()

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
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if not services.tiene_acceso_a_sesion(request, sesion):
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    if sesion.esta_finalizada:
        return JsonResponse({"error": "La sesión está finalizada."}, status=410)

    if not sesion.esta_activa:
        return _json_error("La sesión no está activa.", status=409)

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


@require_POST
def registrar_ubicacion_turista(request, sesion_id):
    """Registra la posición GPS del turista anónimo activo en la sesión."""
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if sesion.esta_finalizada:
        return JsonResponse({"error": "La sesión está finalizada."}, status=410)

    if not sesion.esta_activa:
        return JsonResponse({"error": "La sesión no está activa."}, status=409)

    turista = services.obtener_turista_request(request)
    if not turista:
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    es_participante_activo = TuristaSesion.objects.filter(
        turista=turista,
        sesion_tour=sesion,
        activo=True,
    ).exists()
    if not es_participante_activo:
        return JsonResponse({"error": "Acceso denegado."}, status=403)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)

    latitud = body.get("latitud")
    longitud = body.get("longitud")
    if any(v is None for v in (latitud, longitud)):
        return JsonResponse(
            {"error": "Los campos latitud y longitud son obligatorios."},
            status=400,
        )

    try:
        latitud, longitud = float(latitud), float(longitud)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Latitud/longitud deben ser numéricas."}, status=400)

    if not (-90 <= latitud <= 90) or not (-180 <= longitud <= 180):
        return JsonResponse({"error": "Coordenadas fuera de rango válido."}, status=400)

    try:
        ubicacion = UbicacionVivo.objects.create(
            coordenadas=Point(longitud, latitud, srid=4326),
            timestamp=timezone.now(),
            sesion_tour=sesion,
            usuario=None,
            turista=turista,
        )
    except Exception:
        logger.exception("Error registrando ubicación de turista en sesión %s", sesion.id)
        return _json_internal_error()

    curiosidad_cercana = None
    if sesion.estado == SesionTour.EN_CURSO:
        curiosidad_cercana = _resolver_curiosidad_cercana(sesion, latitud, longitud)

    return JsonResponse(
        {
            "ubicacion_id": ubicacion.id,
            "sesion_id": sesion.id,
            "turista_id": turista.id,
            "latitud": latitud,
            "longitud": longitud,
            "timestamp": ubicacion.timestamp.isoformat(),
            "curiosidad_cercana": curiosidad_cercana,
        },
        status=201,
    )


@require_GET
def obtener_curiosidad_parada(request, sesion_id, parada_id):
    """Devuelve la curiosidad asociada a una parada de la ruta en sesión."""
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if not services.tiene_acceso_a_sesion(request, sesion):
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    if sesion.estado != SesionTour.EN_CURSO:
        return JsonResponse({"error": "La sesión no está en curso."}, status=409)

    parada = sesion.ruta.paradas.filter(id=parada_id).first()
    if not parada:
        return JsonResponse({"error": "La parada no pertenece a la ruta de la sesión."}, status=404)

    curiosidad = Curiosidad.objects.filter(parada=parada).first()
    if not curiosidad:
        return JsonResponse({"error": "No hay curiosidad asociada a esta parada."}, status=404)

    return JsonResponse(
        {
            "status": "ok",
            "parada": {
                "id": parada.id,
                "nombre": parada.nombre,
                "orden": parada.orden,
            },
            "curiosidad": {
                "id": curiosidad.id,
                "titulo": curiosidad.titulo,
                "texto": curiosidad.texto,
                "tipo": curiosidad.tipo,
                "ciudad": curiosidad.ciudad,
                "imagen_url": curiosidad.imagen_url,
            },
        }
    )


@require_GET
def obtener_ubicaciones_turistas(request, sesion_id):
    """Devuelve la última ubicación de turistas activos de la sesión (solo guía)."""
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if not request.user.is_authenticated or not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    if sesion.esta_finalizada:
        return _json_error("La sesión está finalizada.", status=410)

    if not sesion.esta_activa:
        return _json_error("La sesión no está activa.", status=409)

    turistas_activos_ids = list(
        TuristaSesion.objects.filter(sesion_tour=sesion, activo=True).values_list(
            "turista_id", flat=True
        )
    )

    if not turistas_activos_ids:
        return JsonResponse({"turistas": []})

    ubicaciones = (
        UbicacionVivo.objects.filter(
            sesion_tour=sesion,
            turista_id__in=turistas_activos_ids,
            coordenadas__isnull=False,
        )
        .select_related("turista")
        .order_by("turista_id", "-timestamp")
    )

    resultados = []
    vistos = set()
    for ubicacion in ubicaciones:
        turista_id = ubicacion.turista_id
        if not turista_id or turista_id in vistos:
            continue
        vistos.add(turista_id)

        resultados.append(
            {
                "turista_id": turista_id,
                "alias": ubicacion.turista.alias,
                "lat": ubicacion.coordenadas.y,
                "lng": ubicacion.coordenadas.x,
                "timestamp": ubicacion.timestamp.isoformat(),
            }
        )

    return JsonResponse({"turistas": resultados})


# ===========================================================================
# CHAT (accesible a turistas anÃ³nimos y al guÃ­a)
# ===========================================================================

@require_POST
def enviar_mensaje(request, sesion_id):
    """EnvÃ­a un mensaje. Acepta turistas anÃ³nimos (cookie) y el guÃ­a (auth)."""
    imagen = None
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        texto = request.POST.get("texto", "").strip()
        imagen = request.FILES.get("imagen")
    else:
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON invÃ¡lido."}, status=400)
        texto = body.get("texto", "").strip()

    if not texto and not imagen:
        return JsonResponse(
            {"error": "El mensaje no puede estar vacío. Debes enviar texto o una imagen."},
            status=400,
        )

    if len(texto) > 5000:
        return JsonResponse({"error": "El mensaje es demasiado largo (máximo 5000 caracteres)."}, status=400)

    if imagen:
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        if imagen.content_type not in allowed_types:
            return JsonResponse(
                {"error": "Formato de imagen no permitido. Usa JPEG, PNG o WebP."},
                status=400,
            )
        if imagen.size > 5 * 1024 * 1024:
            return JsonResponse(
                {"error": "La imagen supera el tamaño máximo de 5MB."},
                status=400,
            )

    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if sesion.esta_finalizada:
        return _json_error(
            "No se pueden enviar mensajes a una sesión finalizada.",
            status=403,
            estado_sesion=sesion.estado,
        )

    if not sesion.esta_activa:
        return _json_error(
            "No se pueden enviar mensajes si la sesión no está en curso.",
            status=409,
            estado_sesion=sesion.estado,
        )


    remitente_user, remitente_turista, nombre_remitente, error = services.determinar_remitente(
        request, sesion
    )
    if error:
        return JsonResponse({"error": error}, status=403)

    try:
        mensaje = services.crear_mensaje(
            sesion=sesion,
            remitente_user=remitente_user,
            remitente_turista=remitente_turista,
            nombre_remitente=nombre_remitente,
            texto=texto,
            imagen=imagen,
        )
    except Exception:
        logger.exception("Error creando mensaje en sesión %s", sesion.id)
        return _json_internal_error()

    return JsonResponse(
        {
            "status": "ok",
            "mensaje_id": mensaje.id,
            "id": mensaje.id,

            "nombre_remitente": mensaje.nombre_remitente,
            "texto": mensaje.texto,
            "imagen_url": mensaje.imagen.url if mensaje.imagen else None,
            "momento": mensaje.momento.isoformat(),
        },
        status=201,
    )


@require_GET
def descargar_imagen_mensaje(request, sesion_id, mensaje_id):
    """Descarga la imagen adjunta de un mensaje, si el usuario pertenece a la sesión."""
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if not services.tiene_acceso_a_sesion(request, sesion):
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    try:
        mensaje = MensajeChat.objects.get(id=mensaje_id, sesion_tour=sesion)
    except MensajeChat.DoesNotExist:
        return JsonResponse({"error": "Mensaje no encontrado en la sesión."}, status=404)

    if not mensaje.imagen:
        return JsonResponse({"error": "El mensaje no tiene imagen adjunta."}, status=404)

    ext = os.path.splitext(mensaje.imagen.name)[1] or ".bin"
    filename = f"mensaje_{mensaje.id}{ext}"

    try:
        response = FileResponse(mensaje.imagen.open("rb"), as_attachment=True, filename=filename)
    except (OSError, FileNotFoundError):
        logger.exception("No se pudo abrir imagen de mensaje %s en sesión %s", mensaje.id, sesion.id)
        return _json_error("No se pudo recuperar la imagen adjunta.", status=404)

    return response


@require_GET
def obtener_mensajes(request, sesion_id):
    """Devuelve los mensajes de la sesión con filtro opcional por `desde` y `limite`."""
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response

    if not services.tiene_acceso_a_sesion(request, sesion):
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    desde_str = request.GET.get("desde")
    limite_str = request.GET.get("limite", "50")
    desde_dt = None

    try:
        limite = int(limite_str)
    except (TypeError, ValueError):
        return JsonResponse({"error": "El parámetro limite debe ser un entero."}, status=400)

    if limite < 1 or limite > 200:
        return JsonResponse({"error": "El parámetro limite debe estar entre 1 y 200."}, status=400)

    qs = MensajeChat.objects.filter(sesion_tour=sesion)

    if desde_str:
        parsed_desde_dt = parse_datetime(desde_str)
        if not parsed_desde_dt:
            return JsonResponse(
                {"error": "El parámetro desde debe ser una fecha ISO-8601 válida."},
                status=400,
            )

        desde_dt = parsed_desde_dt

        # Evita perder mensajes cuando varios comparten exactamente el mismo timestamp.
        primer_id_mismo_momento = (
            qs.filter(momento=desde_dt).order_by("id").values_list("id", flat=True).first()
        )
        if primer_id_mismo_momento is None:
            qs = qs.filter(momento__gt=desde_dt)
        else:
            qs = qs.filter(
                Q(momento__gt=desde_dt)
                | (Q(momento=desde_dt) & Q(id__gt=primer_id_mismo_momento))
            )

    mensajes_qs = qs.order_by("-momento", "-id")[:limite]
    mensajes_ordenados = list(reversed(list(mensajes_qs)))

    guia_user_id = None
    try:
        guia_user_id = sesion.ruta.guia.user.user_id
    except AttributeError:
        guia_user_id = None

    def _build_sender_key(mensaje: MensajeChat) -> str:
        if mensaje.remitente_id:
            return f"user:{mensaje.remitente_id}"
        if mensaje.turista_id:
            return f"tourist:{mensaje.turista_id}"
        return f"name:{mensaje.nombre_remitente}"

    mensajes = []
    ultimo_momento_serializado = None

    for m in mensajes_ordenados:
        momento_serializado = m.momento

        if desde_dt is not None:
            desde_cmp = desde_dt
            if timezone.is_naive(momento_serializado) and timezone.is_aware(desde_cmp):
                desde_cmp = timezone.make_naive(desde_cmp, timezone.get_current_timezone())
            elif timezone.is_aware(momento_serializado) and timezone.is_naive(desde_cmp):
                desde_cmp = timezone.make_aware(desde_cmp, timezone.get_current_timezone())

            if momento_serializado <= desde_cmp:
                momento_serializado = desde_cmp + timedelta(microseconds=1)

        if ultimo_momento_serializado is not None and momento_serializado <= ultimo_momento_serializado:
            momento_serializado = ultimo_momento_serializado + timedelta(microseconds=1)

        mensajes.append(
            {
                "id":               m.id,
                "nombre_remitente": m.nombre_remitente,
                "remitente_key":    _build_sender_key(m),
                "es_guia":          bool(guia_user_id and m.remitente_id == guia_user_id),
                "texto":            m.texto,
                "imagen_url":       m.imagen.url if m.imagen else None,
                "momento":          momento_serializado.isoformat(),
            }
        )
        ultimo_momento_serializado = momento_serializado

    return JsonResponse(
        {
            "mensajes": mensajes,
            "total": len(mensajes),
            "estado_sesion": sesion.estado,
        }
    )
