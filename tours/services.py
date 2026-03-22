"""
tours/services.py

Capa de servicios: lógica de negocio desacoplada de HTTP.
Turistas: siempre anónimos, identificados por cookie de sesión Django.
Guías: siempre autenticados via Django Auth.
"""
import json
import secrets
import string
from typing import Optional, Tuple

from django.core.cache import cache
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone

from .models import MensajeChat, SesionTour, Turista, TuristaSesion, UbicacionVivo


class TourServiceError(Exception):
    status_code = 400

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class AccesoSesionDenegadoError(TourServiceError):
    status_code = 403


class EstadoSesionInvalidoError(TourServiceError):
    status_code = 409


class SesionFinalizadaError(TourServiceError):
    status_code = 410


# ---------------------------------------------------------------------------
# Autorización
# ---------------------------------------------------------------------------

def es_guia_de_sesion(user: User, sesion: SesionTour) -> bool:
    """
    Verifica si `user` es el guía de la ruta de esta sesión.
    La cadena sesion.ruta.guia.user.user refleja el doble OneToOne del modelo
    Guia → AuthUser → User. Centralizar aquí evita repetirlo en cada vista.
    """
    try:
        return sesion.ruta.guia.user.user == user
    except AttributeError:
        return False


def validar_guia_de_sesion(
    user: User,
    sesion: SesionTour,
    accion: str = "realizar esta acción",
) -> None:
    if not es_guia_de_sesion(user, sesion):
        raise AccesoSesionDenegadoError(f"Solo el guía puede {accion}.")


def validar_sesion_no_finalizada(
    sesion: SesionTour,
    accion: str = "continuar",
) -> None:
    if sesion.esta_finalizada:
        raise SesionFinalizadaError(f"No se puede {accion}: la sesión está finalizada.")


def validar_sesion_en_curso(
    sesion: SesionTour,
    accion: str = "realizar esta acción",
) -> None:
    if sesion.esta_finalizada:
        raise SesionFinalizadaError(
            f"No se puede {accion}: la sesión está finalizada."
        )
    if sesion.estado != SesionTour.EN_CURSO:
        raise EstadoSesionInvalidoError(
            f"No se puede {accion}: la sesión debe estar en curso."
        )


def validar_sesion_iniciable(sesion: SesionTour) -> None:
    if sesion.esta_finalizada:
        raise SesionFinalizadaError(
            "No se puede iniciar una sesión finalizada."
        )
    if sesion.estado != SesionTour.PENDIENTE:
        raise EstadoSesionInvalidoError(
            "La sesión ya está iniciada o no admite esta transición."
        )


def validar_sesion_activa_para_union(sesion: SesionTour) -> None:
    if sesion.esta_finalizada:
        raise SesionFinalizadaError(
            "No se puede unir a la sesión: ya está finalizada."
        )
    if sesion.estado != SesionTour.EN_CURSO:
        raise EstadoSesionInvalidoError(
            "No se puede unir a la sesión: aún no está activa."
        )


def obtener_turista_anonimo(request) -> Optional[Turista]:
    """
    Resuelve el Turista anónimo desde la cookie de sesión Django.
    Retorna None si no hay sesión activa o el turista fue eliminado.
    """
    turista_id = request.session.get("turista_id")
    if not turista_id:
        return None
    return Turista.objects.filter(id=turista_id).first()


def obtener_turista_request(request) -> Optional[Turista]:
    """
    Resuelve el turista asociado al request.
    Prioriza cookie de turista anónimo y, como fallback, el vínculo histórico
    Turista.user para compatibilidad con datos/tests antiguos.
    """
    turista_cookie = obtener_turista_anonimo(request)
    if turista_cookie:
        return turista_cookie

    if request.user.is_authenticated:
        return Turista.objects.filter(user=request.user).first()

    return None


def tiene_acceso_a_sesion(request, sesion: SesionTour) -> bool:
    """
    Devuelve True si el request pertenece a:
    - Un turista anónimo activo en esta sesión (cookie), o
    - El guía autenticado de la ruta.
    """
    if request.user.is_authenticated and es_guia_de_sesion(request.user, sesion):
        return True

    turista = obtener_turista_request(request)
    return turista is not None and TuristaSesion.objects.filter(
        turista=turista, sesion_tour=sesion, activo=True
    ).exists()


# ---------------------------------------------------------------------------
# Códigos de acceso
# ---------------------------------------------------------------------------

def generar_codigo_unico(length: int = 6) -> str:
    """
    Genera un código alfanumérico en mayúsculas único en BD.
    El espacio de 36^6 ≈ 2.2B hace que la colisión sea despreciable.
    """
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        if not SesionTour.objects.filter(codigo_acceso=code).exists():
            return code


# ---------------------------------------------------------------------------
# Serialización geográfica
# ---------------------------------------------------------------------------

ROUTE_SNAPSHOT_CACHE_PREFIX = "tour:session"


def route_snapshot_cache_key(sesion_id: int) -> str:
    return f"{ROUTE_SNAPSHOT_CACHE_PREFIX}:{sesion_id}:route_snapshot"


def _build_route_snapshot(sesion: SesionTour) -> dict:
    paradas = list(sesion.ruta.paradas.all())
    data_paradas = [
        {
            "id": p.id,
            "nombre": p.nombre,
            "orden": p.orden,
            "lat": p.coordenadas.y if p.coordenadas else None,
            "lng": p.coordenadas.x if p.coordenadas else None,
            "es_actual": (
                sesion.parada_actual_id == p.id if sesion.parada_actual_id else False
            ),
        }
        for p in paradas
    ]
    return {
        "sesion_id": sesion.id,
        "ruta_id": sesion.ruta_id,
        "estado": sesion.estado,
        "generated_at": timezone.now().isoformat(),
        "paradas": data_paradas,
        "geometria_ruta": sesion.ruta.geometria_ruta_coords,
    }


def set_route_snapshot(sesion: SesionTour) -> dict:
    snapshot = _build_route_snapshot(sesion)
    cache.set(
        route_snapshot_cache_key(sesion.id),
        snapshot,
        timeout=getattr(settings, "ROUTE_SNAPSHOT_CACHE_TTL", 180),
    )
    return snapshot


def get_route_snapshot(sesion: SesionTour) -> dict:
    key = route_snapshot_cache_key(sesion.id)
    snapshot = cache.get(key)
    if snapshot:
        return snapshot
    return set_route_snapshot(sesion)


def invalidate_route_snapshot(sesion_id: int) -> None:
    cache.delete(route_snapshot_cache_key(sesion_id))


def invalidate_route_snapshots_for_route(ruta_id: int) -> None:
    sesion_ids = SesionTour.objects.filter(ruta_id=ruta_id).values_list("id", flat=True)
    keys = [route_snapshot_cache_key(sesion_id) for sesion_id in sesion_ids]
    if keys:
        cache.delete_many(keys)

def serializar_paradas(sesion: SesionTour) -> str:
    """
    JSON con las paradas de la ruta listo para inyectar en el template.
    Centralizado aquí porque join_tour y mapa_turista_anonimo necesitan
    exactamente la misma estructura.
    """
    data = [
        {
            "id": p.id,
            "nombre": p.nombre,
            "orden": p.orden,
            "lat": p.coordenadas.y if p.coordenadas else None,
            "lng": p.coordenadas.x if p.coordenadas else None,
            "es_actual": (
                sesion.parada_actual_id == p.id if sesion.parada_actual_id else False
            ),
        }
        for p in sesion.ruta.paradas.all()
    ]
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Unión de turistas anónimos
# ---------------------------------------------------------------------------

def unir_turista_anonimo(
    sesion: SesionTour,
    alias: str,
    turista_id_cookie: Optional[int],
) -> Tuple[Optional[Turista], Optional[str]]:
    """
    Gestiona el flujo de unión anónima a una sesión.
    Retorna (turista, None) en éxito o (None, mensaje_error) en fallo.

    Casos:
    1. Alias activo de otro usuario → error.
    2. Alias inactivo del mismo usuario (misma cookie) → reactivar.
    3. Cualquier otro caso → crear turista nuevo.
    """
    validar_sesion_activa_para_union(sesion)

    alias_activo_qs = TuristaSesion.objects.filter(
        sesion_tour=sesion, turista__alias=alias, activo=True
    ).select_related("turista")

    ts_activo = alias_activo_qs.first()

    if ts_activo:
        # ¿Es el mismo usuario reconectando con su cookie?
        if turista_id_cookie and ts_activo.turista.id == turista_id_cookie:
            return ts_activo.turista, None
        return None, f'El alias "{alias}" ya está en uso. Por favor elige otro nombre.'

    # Buscar sesión inactiva para reutilizar en vez de duplicar filas
    ts_inactivo = TuristaSesion.objects.filter(
        sesion_tour=sesion, turista__alias=alias, activo=False
    ).select_related("turista").first()

    if ts_inactivo and turista_id_cookie and ts_inactivo.turista.id == turista_id_cookie:
        ts_inactivo.activo = True
        ts_inactivo.save(update_fields=["activo"])
        return ts_inactivo.turista, None

    turista = Turista.objects.create(alias=alias, user=None)
    TuristaSesion.objects.create(turista=turista, sesion_tour=sesion, activo=True)
    return turista, None


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def determinar_remitente(
    request, sesion: SesionTour
) -> Tuple[Optional[User], Optional[Turista], str, Optional[str]]:
    """
    Resuelve quién envía un mensaje y valida sus permisos.
    Retorna (user, turista, nombre_remitente, error_msg).

    Dos caminos posibles:
    - Guía autenticado → user=request.user, turista=None
    - Turista anónimo  → user=None, turista=<Turista desde cookie>
    """
    if request.user.is_authenticated:
        if not es_guia_de_sesion(request.user, sesion):
            return None, None, "", "No tienes permiso para enviar mensajes en esta sesión."
        return request.user, None, request.user.username, None

    # Turista anónimo
    turista = obtener_turista_request(request)
    if not turista:
        return None, None, "", "Debes unirte al tour para enviar mensajes."

    if not TuristaSesion.objects.filter(
        turista=turista, sesion_tour=sesion, activo=True
    ).exists():
        return None, None, "", "No perteneces a esta sesión."

    return None, turista, turista.alias, None


def crear_mensaje(
    sesion: SesionTour,
    remitente_user: Optional[User],
    remitente_turista: Optional[Turista],
    nombre_remitente: str,
    texto: str,
    imagen=None,
) -> MensajeChat:
    return MensajeChat.objects.create(
        sesion_tour=sesion,
        remitente=remitente_user,
        turista=remitente_turista,
        nombre_remitente=nombre_remitente,
        texto=texto,
        imagen=imagen,
    )


def obtener_nombre_remitente(request, sesion: SesionTour) -> str:
    _, _, nombre_remitente, error = determinar_remitente(request, sesion)
    if error:
        raise AccesoSesionDenegadoError(error)
    return nombre_remitente


# ---------------------------------------------------------------------------
# Gestión de sesiones
# ---------------------------------------------------------------------------

def iniciar_sesion(sesion: SesionTour) -> None:
    validar_sesion_iniciable(sesion)
    sesion.estado = SesionTour.EN_CURSO
    sesion.fecha_inicio = timezone.now()
    sesion.codigo_acceso = generar_codigo_unico()
    sesion.save(update_fields=["estado", "fecha_inicio", "codigo_acceso"])
    set_route_snapshot(sesion)


def cerrar_sesion(sesion: SesionTour) -> None:
    if sesion.esta_finalizada:
        raise EstadoSesionInvalidoError("La sesión ya está finalizada.")
    sesion.estado = SesionTour.FINALIZADO
    sesion.save(update_fields=["estado"])
    TuristaSesion.objects.filter(sesion_tour=sesion, activo=True).update(activo=False)
    set_route_snapshot(sesion)
