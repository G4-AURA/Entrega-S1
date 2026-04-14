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

from billing.tier_guard import (
    TierRuleViolation,
    ensure_chat_mode_allowed,
    ensure_curiosity_route_allowed,
    ensure_premium_for_quedada,
    is_feature_enabled_for_guia,
    ensure_session_capacity_available,
    ensure_session_creation_allowed,
    tier_error_response,
)
from rutas import services as rutas_services
from rutas.models import Curiosidad, Ruta

from . import services
from .models import (
    EntregaRecordatorioTurista,
    MensajeChat,
    RecordatorioSesion,
    SesionTour,
    Turista,
    TuristaSesion,
    UbicacionVivo,
)


logger = logging.getLogger(__name__)


def _is_private_chat_enabled_for_sesion(sesion: SesionTour) -> bool:
    try:
        return is_feature_enabled_for_guia(sesion.ruta.guia, 'chat_mode_separate')
    except Exception:
        return False


def _is_scheduled_meetup_enabled_for_sesion(sesion: SesionTour) -> bool:
    try:
        return is_feature_enabled_for_guia(sesion.ruta.guia, 'scheduled_meetup')
    except Exception:
        return False


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
            "imagen_url": curiosidad.imagen_public_url,
            "manual_url": curiosidad.manual_url,
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

def _serializar_mensaje(mensaje: MensajeChat, guia_user_id: int | None = None) -> dict:
    """Serialización canónica de un MensajeChat para las respuestas JSON."""
    def _build_sender_key(m: MensajeChat) -> str:
        if m.remitente_id:
            return f"user:{m.remitente_id}"
        if m.turista_id:
            return f"tourist:{m.turista_id}"
        return f"name:{m.nombre_remitente}"
 
    return {
        "id": mensaje.id,
        "nombre_remitente": mensaje.nombre_remitente,
        "remitente_key": _build_sender_key(mensaje),
        "es_guia": bool(guia_user_id and mensaje.remitente_id == guia_user_id),
        "texto": mensaje.texto,
        "imagen_url": mensaje.imagen.url if mensaje.imagen else None,
        "momento": mensaje.momento.isoformat(),
        "es_privado": mensaje.es_privado,
        "destinatario_turista_id": mensaje.destinatario_turista_id,
        "turista_id": mensaje.turista_id,
    }


def _serializar_recordatorio(recordatorio: RecordatorioSesion) -> dict:
    alerta_en = recordatorio.hora_objetivo - timedelta(minutes=recordatorio.avisar_minutos_antes)
    payload = {
        "id": recordatorio.id,
        "mensaje": recordatorio.mensaje,
        "hora_objetivo": recordatorio.hora_objetivo.isoformat(),
        "avisar_minutos_antes": recordatorio.avisar_minutos_antes,
        "alerta_en": alerta_en.isoformat(),
        "activo": recordatorio.activo,
        "creado_en": recordatorio.creado_en.isoformat(),
    }
    if recordatorio.ubicacion_quedada:
        payload["ubicacion_quedada"] = {
            "lat": recordatorio.ubicacion_quedada.y,
            "lng": recordatorio.ubicacion_quedada.x,
            "etiqueta": recordatorio.etiqueta_quedada,
        }
    else:
        payload["ubicacion_quedada"] = None
    return payload


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
        union_existente = (
            TuristaSesion.objects.filter(
                turista_id=turista_id_cookie,
                sesion_tour=sesion,
                activo=True,
            )
            .select_related("turista")
            .first()
            if turista_id_cookie
            else None
        )

        bypass_capacidad = bool(
            union_existente and union_existente.turista.alias == alias
        )
        if not bypass_capacidad:
            try:
                ensure_session_capacity_available(sesion)
            except TierRuleViolation as exc:
                return render(
                    request,
                    "tours/join_tour.html",
                    {"sesion": sesion, "error": exc.message},
                    status=exc.http_status,
                )

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
            "private_chat_enabled": _is_private_chat_enabled_for_sesion(sesion),
            "scheduled_meetup_enabled": _is_scheduled_meetup_enabled_for_sesion(sesion),
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

    sesion_activa = SesionTour.objects.filter(
        ruta=ruta,
        estado__in=[SesionTour.PENDIENTE, SesionTour.EN_CURSO]
    ).order_by("-id").first()

    if sesion_activa:
        return redirect("tours:guia_sesion", sesion_id=sesion_activa.id)

    try:
        ensure_session_creation_allowed(ruta)
    except TierRuleViolation as exc:
        return tier_error_response(exc)

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

    minutos_restantes = None
    duracion_horas = float(sesion.ruta.duracion_horas or 0)
    if (
        sesion.estado == SesionTour.EN_CURSO
        and sesion.fecha_inicio
        and math.isfinite(duracion_horas)
        and duracion_horas > 0
    ):
        fecha_fin = sesion.fecha_inicio + timedelta(hours=duracion_horas)
        segundos_restantes = max(0, int((fecha_fin - timezone.now()).total_seconds()))
        minutos_restantes = math.ceil(segundos_restantes / 60) if segundos_restantes else 0

    return JsonResponse(
        {
            "estado": sesion.estado,
            "fecha_inicio": sesion.fecha_inicio.isoformat() if sesion.fecha_inicio else None,
            "duracion_horas": duracion_horas,
            "minutos_restantes": minutos_restantes,
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
            "private_chat_enabled": _is_private_chat_enabled_for_sesion(sesion),
            "scheduled_meetup_enabled": _is_scheduled_meetup_enabled_for_sesion(sesion),
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

    try:
        ensure_curiosity_route_allowed(sesion.ruta)
    except TierRuleViolation as exc:
        return tier_error_response(exc)

    parada = sesion.ruta.paradas.filter(id=parada_id).first()
    if not parada:
        return JsonResponse({"error": "La parada no pertenece a la ruta de la sesión."}, status=404)

    try:
        curiosidad, _generada = rutas_services.obtener_o_generar_curiosidad_parada(
            parada=parada,
            ciudad="Sevilla",
        )
    except Exception:
        return JsonResponse({"error": "No se pudo obtener la curiosidad para esta parada."}, status=502)

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
                "imagen_url": curiosidad.imagen_public_url,
                "manual_url": curiosidad.manual_url,
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
# RECORDATORIOS / ALERTAS DE SESIÓN
# ===========================================================================

@require_http_methods(["GET", "POST"])
def recordatorios_sesion(request, sesion_id):
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response
    try:
        ensure_premium_for_quedada(sesion)
    except TierRuleViolation as exc:
        return tier_error_response(exc)

    if request.method == "GET":
        if not services.tiene_acceso_a_sesion(request, sesion):
            return JsonResponse({"error": "Acceso denegado."}, status=403)

        recordatorios = list(
            RecordatorioSesion.objects.filter(sesion_tour=sesion).order_by("hora_objetivo", "id")
        )
        return JsonResponse(
            {
                "recordatorios": [_serializar_recordatorio(r) for r in recordatorios],
                "total": len(recordatorios),
                "estado_sesion": sesion.estado,
            }
        )

    if not request.user.is_authenticated or not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "Solo el guía puede crear recordatorios."}, status=403)

    if sesion.esta_finalizada:
        return JsonResponse({"error": "No se pueden crear recordatorios en una sesión finalizada."}, status=410)

    if sesion.estado != SesionTour.EN_CURSO:
        return JsonResponse({"error": "Solo puedes crear recordatorios cuando el tour está en curso."}, status=409)

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)

    mensaje = str(body.get("mensaje") or "").strip()
    if not mensaje:
        return JsonResponse({"error": "El mensaje del recordatorio es obligatorio."}, status=400)
    if len(mensaje) > 5000:
        return JsonResponse({"error": "El mensaje es demasiado largo (máximo 5000 caracteres)."}, status=400)

    hora_objetivo_raw = body.get("hora_objetivo")
    hora_objetivo = parse_datetime(str(hora_objetivo_raw or ""))
    if not hora_objetivo:
        return JsonResponse({"error": "hora_objetivo debe ser una fecha ISO-8601 válida."}, status=400)
    if timezone.is_naive(hora_objetivo):
        hora_objetivo = timezone.make_aware(hora_objetivo, timezone.get_current_timezone())

    avisar_minutos_antes_raw = body.get("avisar_minutos_antes", 10)
    try:
        avisar_minutos_antes = int(avisar_minutos_antes_raw)
    except (TypeError, ValueError):
        return JsonResponse({"error": "avisar_minutos_antes debe ser un entero."}, status=400)
    if avisar_minutos_antes < 0 or avisar_minutos_antes > 240:
        return JsonResponse({"error": "avisar_minutos_antes debe estar entre 0 y 240."}, status=400)

    ahora = timezone.now()
    if hora_objetivo <= ahora:
        return JsonResponse({"error": "La hora objetivo debe ser futura."}, status=400)

    alerta_en = hora_objetivo - timedelta(minutes=avisar_minutos_antes)
    if alerta_en <= ahora:
        return JsonResponse(
            {"error": "Con esa antelación, la alerta ya habría ocurrido. Ajusta hora o minutos."},
            status=400,
        )

    meetup_lat = body.get("meetup_lat")
    meetup_lng = body.get("meetup_lng")
    etiqueta_quedada = str(body.get("etiqueta_quedada") or "").strip()
    ubicacion_quedada = None

    if meetup_lat is not None or meetup_lng is not None:
        if meetup_lat is None or meetup_lng is None:
            return JsonResponse({"error": "Debes enviar meetup_lat y meetup_lng juntos."}, status=400)
        try:
            lat = float(meetup_lat)
            lng = float(meetup_lng)
        except (TypeError, ValueError):
            return JsonResponse({"error": "meetup_lat y meetup_lng deben ser numéricos."}, status=400)
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return JsonResponse({"error": "Coordenadas de quedada fuera de rango válido."}, status=400)
        ubicacion_quedada = Point(lng, lat, srid=4326)

    recordatorio = RecordatorioSesion.objects.create(
        sesion_tour=sesion,
        creado_por=request.user,
        mensaje=mensaje,
        hora_objetivo=hora_objetivo,
        avisar_minutos_antes=avisar_minutos_antes,
        ubicacion_quedada=ubicacion_quedada,
        etiqueta_quedada=etiqueta_quedada,
    )

    return JsonResponse(
        {
            "status": "ok",
            "recordatorio": _serializar_recordatorio(recordatorio),
        },
        status=201,
    )


@require_GET
def alertas_recordatorios(request, sesion_id):
    sesion, error_response = _get_sesion_or_json_404(sesion_id)
    if error_response:
        return error_response
    try:
        ensure_premium_for_quedada(sesion)
    except TierRuleViolation as exc:
        return tier_error_response(exc)

    turista = services.obtener_turista_request(request)
    if not turista:
        return JsonResponse({"error": "Solo los turistas pueden consultar alertas."}, status=403)

    es_participante_activo = TuristaSesion.objects.filter(
        turista=turista,
        sesion_tour=sesion,
        activo=True,
    ).exists()
    if not es_participante_activo:
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    if sesion.esta_finalizada:
        return JsonResponse({"alertas": [], "total": 0, "estado_sesion": sesion.estado})

    ahora = timezone.now()
    ventana_pasado = ahora - timedelta(minutes=5)

    candidatos = list(
        RecordatorioSesion.objects.filter(
            sesion_tour=sesion,
            activo=True,
            hora_objetivo__gte=ventana_pasado,
        ).order_by("hora_objetivo", "id")
    )

    alertas = []
    for recordatorio in candidatos:
        alerta_en = recordatorio.hora_objetivo - timedelta(minutes=recordatorio.avisar_minutos_antes)
        if alerta_en > ahora:
            continue

        entrega, created = EntregaRecordatorioTurista.objects.get_or_create(
            recordatorio=recordatorio,
            turista=turista,
        )
        if not created:
            continue

        alertas.append(
            {
                **_serializar_recordatorio(recordatorio),
                "entregado_en": entrega.entregado_en.isoformat(),
            }
        )

    return JsonResponse(
        {
            "alertas": alertas,
            "total": len(alertas),
            "estado_sesion": sesion.estado,
        }
    )


# ===========================================================================
# CHAT COMÚN
# ===========================================================================

@require_POST
def enviar_mensaje(request, sesion_id):
    """
    Envía un mensaje. Acepta turistas anónimos (cookie) y el guía (auth).
 
    Parámetros adicionales en JSON / FormData:
      es_privado            — bool, opcional (default false)
      destinatario_turista_id — int, requerido si es_privado=true y el remitente es el guía
    """
    imagen = None
    modo_chat = ""
    es_privado = False
    destinatario_turista_id = None
 
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        texto = request.POST.get("texto", "").strip()
        imagen = request.FILES.get("imagen")
        modo_chat = request.POST.get("modo_chat", "").strip()
        es_privado = request.POST.get("es_privado", "").lower() in ("true", "1", "yes")
        destinatario_turista_id = request.POST.get("destinatario_turista_id") or None
    else:
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON inválido."}, status=400)
        texto = body.get("texto", "").strip()
        modo_chat = str(body.get("modo_chat") or "").strip()
        es_privado = bool(body.get("es_privado", False))
        destinatario_turista_id = body.get("destinatario_turista_id") or None
 
    # Validaciones básicas de contenido
    if not texto and not imagen:
        return JsonResponse({"error": "El mensaje no puede estar vacío. Debes enviar texto o una imagen."}, status=400)
    if len(texto) > 5000:
        return JsonResponse({"error": "El mensaje es demasiado largo (máximo 5000 caracteres)."}, status=400)
    if imagen:
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        if imagen.content_type not in allowed_types:
            return JsonResponse({"error": "Formato de imagen no permitido. Usa JPEG, PNG o WebP."}, status=400)
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

    # Validación de tier para chat:
    # - Público: usa el modo indicado por cliente.
    # - Privado: fuerza modo separado para impedir bypass por payload directo.
    try:
        chat_mode_to_validate = "separado" if es_privado else modo_chat
        ensure_chat_mode_allowed(sesion, chat_mode_to_validate)
    except TierRuleViolation as exc:
        return tier_error_response(exc)

    # Resolución del destinatario privado
    destinatario_turista = None
    if es_privado and remitente_user and not destinatario_turista_id:
        return JsonResponse(
            {"error": "Debes indicar destinatario_turista_id para enviar mensajes privados del guía."},
            status=400,
        )
    if es_privado and remitente_user and destinatario_turista_id:
        # El guía envía a un turista concreto
        try:
            destinatario_turista = Turista.objects.get(id=int(destinatario_turista_id))
            # Verificar que el turista pertenece a esta sesión
            if not TuristaSesion.objects.filter(turista=destinatario_turista, sesion_tour=sesion).exists():
                return JsonResponse({"error": "El turista destinatario no pertenece a esta sesión."}, status=400)
        except (Turista.DoesNotExist, ValueError):
            return JsonResponse({"error": "El turista destinatario no existe."}, status=400)
    elif es_privado and remitente_turista:
        # El turista responde al guía (sin destinatario explícito — el guía es implícito)
        destinatario_turista = None

    try:
        mensaje = services.crear_mensaje(
            sesion=sesion,
            remitente_user=remitente_user,
            remitente_turista=remitente_turista,
            nombre_remitente=nombre_remitente,
            texto=texto,
            imagen=imagen,
            es_privado=es_privado,
            destinatario_turista=destinatario_turista,
        )
    except Exception:
        logger.exception("Error creando mensaje en sesión %s", sesion.id)
        return _json_internal_error()

    guia_user_id = None
    try:
        guia_user_id = sesion.ruta.guia.user.user_id
    except AttributeError:
        pass

    return JsonResponse(
        {
            "status": "ok",
            "mensaje_id": mensaje.id,
            "id": mensaje.id,
            "nombre_remitente": mensaje.nombre_remitente,
            "texto": mensaje.texto,
            "imagen_url": mensaje.imagen.url if mensaje.imagen else None,
            "momento": mensaje.momento.isoformat(),
            "es_privado": mensaje.es_privado,
            "destinatario_turista_id": mensaje.destinatario_turista_id,
            "es_guia": bool(guia_user_id and mensaje.remitente_id == guia_user_id),
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
    """
    Devuelve los mensajes de la sesión con filtro opcional por `desde` y `limite`.

    Para turistas: solo mensajes públicos + mensajes privados propios.
    Para el guía:  todos los mensajes (públicos y privados de todos los turistas).
    """
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
 
    # ── Construir queryset base ────────────────────────────────────────────
    # El chat grupal SOLO debe devolver mensajes públicos para todos.
    # Los mensajes privados tienen su propio endpoint (mensajes_privados_hilo).
    qs = MensajeChat.objects.filter(sesion_tour=sesion, es_privado=False)
 
    if desde_str:
        parsed = parse_datetime(desde_str)
        if not parsed:
            return JsonResponse({"error": "El parámetro desde debe ser una fecha ISO-8601 válida."}, status=400)
        desde_dt = parsed
        primer_id_mismo_momento = qs.filter(momento=desde_dt).order_by("id").values_list("id", flat=True).first()
        if primer_id_mismo_momento is None:
            qs = qs.filter(momento__gt=desde_dt)
        else:
            qs = qs.filter(Q(momento__gt=desde_dt) | (Q(momento=desde_dt) & Q(id__gt=primer_id_mismo_momento)))
 
    mensajes_qs = qs.order_by("-momento", "-id")[:limite]
    mensajes_ordenados = list(reversed(list(mensajes_qs)))
 
    guia_user_id = None
    try:
        guia_user_id = sesion.ruta.guia.user.user_id
    except AttributeError:
        pass
 
    mensajes = []
    ultimo_momento_serializado = None
 
    for m in mensajes_ordenados:
        momento_serializado = m.momento
        if desde_dt is not None:
            desde_cmp = desde_dt
            from django.utils import timezone as tz
            if tz.is_naive(momento_serializado) and tz.is_aware(desde_cmp):
                desde_cmp = tz.make_naive(desde_cmp, tz.get_current_timezone())
            elif tz.is_aware(momento_serializado) and tz.is_naive(desde_cmp):
                desde_cmp = tz.make_aware(desde_cmp, tz.get_current_timezone())
            if momento_serializado <= desde_cmp:
                momento_serializado = desde_cmp + timedelta(microseconds=1)
 
        if ultimo_momento_serializado is not None and momento_serializado <= ultimo_momento_serializado:
            momento_serializado = ultimo_momento_serializado + timedelta(microseconds=1)
 
        def _sender_key(msg):
            if msg.remitente_id:
                return f"user:{msg.remitente_id}"
            if msg.turista_id:
                return f"tourist:{msg.turista_id}"
            return f"name:{msg.nombre_remitente}"
 
        mensajes.append({
            "id": m.id,
            "nombre_remitente": m.nombre_remitente,
            "remitente_key": _sender_key(m),
            "es_guia": bool(guia_user_id and m.remitente_id == guia_user_id),
            "texto": m.texto,
            "imagen_url": m.imagen.url if m.imagen else None,
            "momento": momento_serializado.isoformat(),
            "es_privado": m.es_privado,
            "destinatario_turista_id": m.destinatario_turista_id,
            "turista_id": m.turista_id,
        })
        ultimo_momento_serializado = momento_serializado
 
    return JsonResponse({
        "mensajes": mensajes,
        "total": len(mensajes),
        "estado_sesion": sesion.estado,
    })


# ===========================================================================
# CHAT PRIVADO
# ===========================================================================
 
@require_GET
def bandeja_privada_guia(request, sesion_id):
    """
    GET /tours/sesiones/<sesion_id>/chat-privado/bandeja/
 
    Devuelve la lista de turistas activos con el último mensaje del hilo privado.
    Solo accesible para el guía autenticado.
    """
    sesion = get_object_or_404(SesionTour, id=sesion_id)
    if not request.user.is_authenticated or not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    try:
        ensure_chat_mode_allowed(sesion, 'separado')
    except TierRuleViolation as exc:
        return tier_error_response(exc)
 
    bandeja = services.obtener_bandeja_privada_guia(sesion)
    return JsonResponse({"bandeja": bandeja})
 
 
@require_GET
def mensajes_privados_hilo(request, sesion_id, turista_id):
    """
    GET /tours/sesiones/<sesion_id>/chat-privado/<turista_id>/mensajes/
 
    Devuelve los mensajes del hilo privado entre el guía y el turista indicado.
    Accesible tanto por el guía autenticado como por el propio turista (cookie).
 
    Parámetros opcionales de query-string:
      desde  — ISO-8601 datetime
      limite — int (1-200, default 50)
    """
    sesion = get_object_or_404(SesionTour, id=sesion_id)
    turista = get_object_or_404(Turista, id=turista_id)
 
    pertenece_a_sesion = TuristaSesion.objects.filter(
        sesion_tour=sesion,
        turista=turista,
    ).exists()
    if not pertenece_a_sesion:
        return JsonResponse({"error": "El turista no pertenece a esta sesión."}, status=404)
 
    # Control de acceso: guía o el propio turista
    es_guia_req = request.user.is_authenticated and services.es_guia_de_sesion(request.user, sesion)
    turista_cookie = services.obtener_turista_request(request)
    turista_activo = TuristaSesion.objects.filter(
        sesion_tour=sesion,
        turista=turista,
        activo=True,
    ).exists()
    es_turista_propio = turista_cookie is not None and turista_cookie.id == turista.id and turista_activo
 
    if not es_guia_req and not es_turista_propio:
        return JsonResponse({"error": "Acceso denegado."}, status=403)

    try:
        ensure_chat_mode_allowed(sesion, 'separado')
    except TierRuleViolation as exc:
        return tier_error_response(exc)
 
    desde_str = request.GET.get("desde")
    limite_str = request.GET.get("limite", "50")
    desde_dt = None
 
    try:
        limite = int(limite_str)
    except (TypeError, ValueError):
        return JsonResponse({"error": "El parámetro limite debe ser un entero."}, status=400)
    if limite < 1 or limite > 200:
        return JsonResponse({"error": "El parámetro limite debe estar entre 1 y 200."}, status=400)
 
    if desde_str:
        desde_dt = parse_datetime(desde_str)
        if not desde_dt:
            return JsonResponse({"error": "El parámetro desde debe ser una fecha ISO-8601 válida."}, status=400)
 
    mensajes = services.obtener_mensajes_privados_turista(sesion, turista, desde=desde_dt, limite=limite)
 
    guia_user_id = None
    try:
        guia_user_id = sesion.ruta.guia.user.user_id
    except AttributeError:
        pass
 
    return JsonResponse({
        "mensajes": [_serializar_mensaje(m, guia_user_id) for m in mensajes],
        "total": len(mensajes),
        "turista_id": turista.id,
        "turista_alias": turista.alias,
        "estado_sesion": sesion.estado,
    })
