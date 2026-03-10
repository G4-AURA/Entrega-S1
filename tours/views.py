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
from .models import MensajeChat, SesionTour, Turista, TuristaSesion, UbicacionVivo


# ===========================================================================
# TURISTAS ANÓNIMOS
# Flujo único: /live/code/<codigo>/ → alias → /live/<token>/mapa/
# ===========================================================================

def join_tour_by_code(request, codigo):
    """
    Punto de entrada para turistas. Resuelve el código legible al token UUID
    interno y redirige. El código es insensible a mayúsculas/minúsculas.
    """
    sesion = get_object_or_404(SesionTour, codigo_acceso=codigo.upper())

    if sesion.esta_finalizada:
        return render(
            request,
            "tours/join_error.html",
            {"error": "Esta sesión ya ha finalizado."},
            status=410,
        )

    return redirect("tours:join_tour", token=sesion.token)


def join_tour(request, token):
    """
    GET:  Formulario de alias.
    POST: Crea/reactiva el turista anónimo y redirige al mapa.
    """
    sesion = get_object_or_404(SesionTour, token=token)

    if sesion.esta_finalizada:
        return render(
            request,
            "tours/join_error.html",
            {"error": "Esta sesión ya ha finalizado."},
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
    Mapa en vivo para el turista anónimo verificado por cookie.
    """
    sesion = get_object_or_404(SesionTour, token=token)

    turista = services.obtener_turista_anonimo(request)
    if not turista:
        return redirect("tours:join_tour", token=token)

    if not TuristaSesion.objects.filter(turista=turista, sesion_tour=sesion).exists():
        return redirect("tours:join_tour", token=token)

    return render(
        request,
        "turista/turista_mapa.html",
        {
            "sesion":              sesion,
            "turista":             turista,
            "paradas":             sesion.ruta.paradas.all(),
            "paradas_json":        services.serializar_paradas(sesion),
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
    ruta_id = request.GET.get("ruta_id")
    if not ruta_id:
        return JsonResponse({"error": "Parámetro ruta_id requerido."}, status=400)

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
        return JsonResponse(
            {"error": "No autorizado para crear sesión para esta ruta."}, status=403
        )

    sesion = SesionTour.objects.create(
        codigo_acceso=services.generar_codigo_unico(),
        estado=SesionTour.EN_CURSO,
        fecha_inicio=timezone.now(),
        ruta=ruta,
    )
    return redirect("tours:guia_sesion", sesion_id=sesion.id)


@login_required
def guia_sesion(request, sesion_id):
    """Panel de control del guía para una sesión activa."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    return render(request, "tours/guia_sesion.html", {"sesion": sesion})


@login_required
@require_POST
def iniciar_tour(request, sesion_id):
    """Transiciona la sesión de PENDIENTE → EN_CURSO."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if sesion.esta_finalizada:
        return JsonResponse(
            {"error": "No se puede iniciar una sesión finalizada."}, status=400
        )

    services.iniciar_sesion(sesion)

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

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    sesion.codigo_acceso = services.generar_codigo_unico()
    sesion.save(update_fields=["codigo_acceso"])
    return JsonResponse({"codigo_acceso": sesion.codigo_acceso})


@login_required
@require_POST
def cerrar_acceso(request, sesion_id):
    """Finaliza la sesión y desactiva a todos los participantes."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    services.cerrar_sesion(sesion)
    return JsonResponse({"status": "cerrado"})


@login_required
@require_GET
def participantes_sesion(request, sesion_id):
    """Lista de turistas activos en la sesión (solo para el guía)."""
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
    Mapa en vivo para el guía autenticado.
    Ruta exclusiva del guía — omite el formulario de alias de turistas.
    """
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse({"error": "No autorizado."}, status=403)

    return render(
        request,
        "turista/turista_mapa.html",
        {
            "sesion":              sesion,
            "paradas":             sesion.ruta.paradas.all(),
            "paradas_json":        services.serializar_paradas(sesion),
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

    if not (-90 <= latitud <= 90) or not (-180 <= longitud <= 180):
        return JsonResponse({"error": "Coordenadas fuera de rango válido."}, status=400)

    sesion = get_object_or_404(SesionTour, id=sesion_id)

    if not services.es_guia_de_sesion(request.user, sesion):
        return JsonResponse(
            {"error": "Solo el guía puede registrar ubicaciones."}, status=403
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
    """Última posición GPS del guía (polling desde el mapa del turista)."""
    sesion = get_object_or_404(SesionTour, id=sesion_id)

    try:
        guia_user = sesion.ruta.guia.user.user
    except AttributeError:
        return JsonResponse(
            {"error": "No se pudo identificar al guía de esta ruta."}, status=404
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

    return JsonResponse({"error": "El guía aún no ha compartido su ubicación."}, status=404)


# ===========================================================================
# CHAT (accesible a turistas anónimos y al guía)
# ===========================================================================

@require_POST
def enviar_mensaje(request, sesion_id):
    """
    Envía un mensaje al chat de una sesión.
    
    Validaciones implementadas (S2.1-52):
    - Sesión debe existir (404 si no existe)
    - Sesión no debe estar finalizada (403)
    - Usuario debe tener acceso a la sesión (403)
    - Texto del mensaje no puede estar vacío (400)
    """
    # Validar JSON
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Formato JSON inválido en el cuerpo de la petición."},
            status=400
        )

    # Validar campo texto
    texto = body.get("texto", "").strip()
    if not texto:
        return JsonResponse(
            {"error": "El campo 'texto' es obligatorio y no puede estar vacío."},
            status=400
        )

    # Validar longitud del mensaje
    if len(texto) > 5000:
        return JsonResponse(
            {"error": "El mensaje es demasiado largo (máximo 5000 caracteres)."},
            status=400
        )

    # Validar que la sesión existe
    try:
        sesion = SesionTour.objects.get(id=sesion_id)
    except SesionTour.DoesNotExist:
        return JsonResponse(
            {"error": f"La sesión con ID {sesion_id} no existe."},
            status=404
        )

    # Validar que la sesión no está finalizada
    if sesion.esta_finalizada:
        return JsonResponse(
            {
                "error": "No se pueden enviar mensajes a una sesión finalizada.",
                "estado_sesion": sesion.estado
            },
            status=403
        )

    # Validar que el usuario tiene acceso a la sesión
    if not services.tiene_acceso_a_sesion(request, sesion):
        return JsonResponse(
            {
                "error": "No tienes permiso para enviar mensajes a esta sesión. "
                        "Debes ser un turista activo o el guía de esta sesión."
            },
            status=403
        )

    # Obtener nombre del remitente
    nombre_remitente = services.obtener_nombre_remitente(request, sesion)

    # Crear el mensaje
    try:
        mensaje = MensajeChat.objects.create(
            sesion_tour=sesion,
            nombre_remitente=nombre_remitente,
            texto=texto,
            momento=timezone.now(),
        )
        
        return JsonResponse(
            {
                "status": "ok",
                "mensaje_id": mensaje.id,
                "momento": mensaje.momento.isoformat()
            },
            status=201
        )
    except Exception as e:
        # Log del error para debugging (sin exponer detalles al cliente)
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error al crear mensaje en sesión {sesion_id}: {str(e)}")
        
        return JsonResponse(
            {"error": "Error interno al guardar el mensaje. Inténtalo de nuevo."},
            status=500
        )


@require_GET
def obtener_mensajes(request, sesion_id):
    """
    Devuelve los mensajes del chat de una sesión.
    
    Validaciones implementadas (S2.1-52):
    - Sesión debe existir (404 si no existe)
    - Usuario debe tener acceso a la sesión (403)
    - Parámetro 'desde' debe ser una fecha válida si se proporciona (400)
    
    Nota: Se permiten consultas a sesiones finalizadas para ver el historial.
    """
    # Validar que la sesión existe
    try:
        sesion = SesionTour.objects.get(id=sesion_id)
    except SesionTour.DoesNotExist:
        return JsonResponse(
            {"error": f"La sesión con ID {sesion_id} no existe."},
            status=404
        )

    # Validar que el usuario tiene acceso a la sesión
    if not services.tiene_acceso_a_sesion(request, sesion):
        return JsonResponse(
            {
                "error": "No tienes permiso para ver los mensajes de esta sesión. "
                        "Debes ser un turista activo o el guía de esta sesión."
            },
            status=403
        )

    # Construir query base
    qs = MensajeChat.objects.filter(sesion_tour=sesion).order_by("momento")

    # Filtro opcional por fecha 'desde'
    desde_str = request.GET.get("desde")
    if desde_str:
        desde_dt = parse_datetime(desde_str)
        if desde_dt is None:
            return JsonResponse(
                {
                    "error": "El parámetro 'desde' debe ser una fecha ISO válida "
                            "(formato: YYYY-MM-DDTHH:MM:SS)."
                },
                status=400
            )
        qs = qs.filter(momento__gt=desde_dt)

    # Serializar mensajes
    try:
        mensajes = [
            {
                "id":               m.id,
                "nombre_remitente": m.nombre_remitente,
                "texto":            m.texto,
                "momento":          m.momento.isoformat(),
            }
            for m in qs
        ]

        return JsonResponse(
            {
                "mensajes": mensajes,
                "total": len(mensajes),
                "estado_sesion": sesion.estado
            }
        )
    except Exception as e:
        # Log del error para debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error al obtener mensajes de sesión {sesion_id}: {str(e)}")
        
        return JsonResponse(
            {"error": "Error interno al recuperar los mensajes."},
            status=500
        )