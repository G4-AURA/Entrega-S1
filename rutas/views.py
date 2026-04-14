"""
rutas/views.py

Vistas delgadas: validan HTTP y delegan al módulo rutas/services.

Roles:
  - Guía: autenticado con Django Auth (@login_required)

S2.1-32: endpoint AJAX para recalcular bajo demanda.
"""
import json
import logging

from datetime import timezone as dt_timezone
from urllib.parse import quote_plus, unquote_plus

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
import requests

from billing.models import Subscription, TierUsageEvent
from billing.services import StripeAPIError, fetch_subscription_snapshot
from billing.tier_guard import (
    TierRuleViolation,
    ensure_curiosity_route_allowed,
    ensure_moods_allowed,
    ensure_route_people_count_allowed,
    ensure_route_stop_add_allowed,
    get_allowed_moods_for_guia,
    get_session_capacity_limit,
    get_usage_cycle_window,
    normalize_mood_values,
    tier_error_response,
)
from creacion import services as creacion_services
from tours.models import SesionTour
from .forms import EditarPerfilForm
from . import services
from .models import Curiosidad, Guia, Parada, Ruta

logger = logging.getLogger(__name__)

MAX_RUTAS_PAGE_SIZE = 9

PLAN_LIMITS = {
    Guia.Suscripcion.FREEMIUM: [
        '1 ruta manual simultánea',
        '1 ruta IA simultánea',
        '3 generaciones IA al mes',
        '9 sustituciones IA al mes (máx. 3 por ruta IA)',
        'Hasta 15 turistas por sesión',
        '5 paradas por ruta',
    ],
    Guia.Suscripcion.PREMIUM: [
        'Hasta 10 rutas manuales simultáneas',
        'Hasta 10 rutas IA simultáneas',
        '10 generaciones IA al mes',
        '30 sustituciones IA al mes (sin límite por ruta)',
        'Hasta 50 turistas por sesión',
        '15 paradas por ruta',
    ],
}

PLAN_RULES = {
    Guia.Suscripcion.FREEMIUM: {
        'manual_routes_limit': 1,
        'ia_routes_limit': 1,
        'max_personas_por_sesion': 15,
        'max_paradas_por_ruta': 5,
        'max_generaciones_ia_mes': 3,
        'max_sustituciones_ia_mes': 9,
        'max_sustituciones_ia_ruta': 3,
        'max_rutas_curiosidades': 3,
    },
    Guia.Suscripcion.PREMIUM: {
        'manual_routes_limit': 10,
        'ia_routes_limit': 10,
        'max_personas_por_sesion': 50,
        'max_paradas_por_ruta': 15,
        'max_generaciones_ia_mes': 10,
        'max_sustituciones_ia_mes': 30,
        'max_sustituciones_ia_ruta': None,
        'max_rutas_curiosidades': None,  # ilimitado
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


def _redirect_con_error_tier(path: str, exc: TierRuleViolation):
    encoded_message = quote_plus(exc.message)
    return redirect(
        f"{path}?tier_code={exc.code}&tier_status={exc.http_status}&tier_message={encoded_message}"
    )


# ================================================
# Guardia de rol: solo guías autenticados
# ================================================

def es_guia(user):
    """
    Comprueba si el usuario autenticado tiene un perfil de Guia asociado.
    Ruta de modelos: User -> AuthUser (auth_profile) -> Guia (guia)
    """
    if user.is_superuser:
        return True
    if user.is_authenticated:
        if hasattr(user, 'auth_profile') and hasattr(user.auth_profile, 'guia'):
            if user.auth_profile.guia is not None:
                return True
    raise PermissionDenied("Acceso denegado: área exclusiva para guías.")


def _obtener_guia_usuario(user):
    if not hasattr(user, 'auth_profile'):
        return None
    if not hasattr(user.auth_profile, 'guia'):
        return None
    return user.auth_profile.guia


def _obtener_suscripcion_actual(guia):
    if guia is None:
        return None
    subscriptions = Subscription.objects.filter(guia=guia)

    if guia.tipo_suscripcion == Guia.Suscripcion.PREMIUM:
        activa = (
            subscriptions.filter(
                tier=Guia.Suscripcion.PREMIUM,
                status__in=[
                    Subscription.Status.ACTIVE,
                    Subscription.Status.TRIALING,
                    Subscription.Status.PAST_DUE,
                ],
                stripe_subscription_id__isnull=False,
            )
            .exclude(stripe_subscription_id='')
            .order_by('-updated_at', '-id')
            .first()
        )
        if activa is not None:
            return activa

        premium = subscriptions.filter(
            tier=Guia.Suscripcion.PREMIUM,
        ).order_by('-updated_at', '-id').first()
        if premium is not None:
            return premium

    return subscriptions.order_by('-updated_at', '-id').first()


def _calcular_usos_plan(guia):
    reglas = PLAN_RULES.get(guia.tipo_suscripcion, {})
    rutas_qs = Ruta.objects.filter(guia=guia)
    rutas_manual = rutas_qs.filter(es_generada_ia=False).count()
    rutas_ia = rutas_qs.filter(es_generada_ia=True).count()

    manual_limit = reglas.get('manual_routes_limit')
    ia_limit = reglas.get('ia_routes_limit')
    personas_limit = reglas.get('max_personas_por_sesion')
    paradas_limit = reglas.get('max_paradas_por_ruta')
    generaciones_limit = reglas.get('max_generaciones_ia_mes')
    sustituciones_mes_limit = reglas.get('max_sustituciones_ia_mes')
    sustituciones_ruta_limit = reglas.get('max_sustituciones_ia_ruta')
    curiosidades_limit = reglas.get('max_rutas_curiosidades')

    inicio_ciclo, fin_ciclo, _ancla_ciclo = get_usage_cycle_window(guia)

    sesiones_activas = (
        SesionTour.objects.filter(
            ruta__guia=guia,
            estado__in=[SesionTour.PENDIENTE, SesionTour.EN_CURSO],
        )
        .annotate(
            turistas_activos=Count(
                'turistasesion',
                filter=Q(turistasesion__activo=True),
                distinct=True,
            )
        )
        .order_by('-turistas_activos', 'id')
    )
    sesion_mas_ocupada = sesiones_activas.first()
    capacidad_consumida = int(getattr(sesion_mas_ocupada, 'turistas_activos', 0) or 0)
    capacidad_restante = (
        max(personas_limit - capacidad_consumida, 0)
        if personas_limit is not None
        else None
    )

    ruta_mas_cargada = rutas_qs.annotate(total_paradas=Count('paradas')).order_by('-total_paradas', 'id').first()
    paradas_consumidas = int(getattr(ruta_mas_cargada, 'total_paradas', 0) or 0)
    paradas_restantes = (
        max(paradas_limit - paradas_consumidas, 0)
        if paradas_limit is not None
        else None
    )

    generaciones_mes = TierUsageEvent.objects.filter(
        guia=guia,
        action=TierUsageEvent.Action.IA_ROUTE_GENERATION,
        created_at__gte=inicio_ciclo,
        created_at__lt=fin_ciclo,
    ).count()
    generaciones_restantes = (
        max(generaciones_limit - generaciones_mes, 0)
        if generaciones_limit is not None
        else None
    )

    sustituciones_mes_qs = TierUsageEvent.objects.filter(
        guia=guia,
        action=TierUsageEvent.Action.IA_STOP_REPLACEMENT,
        created_at__gte=inicio_ciclo,
        created_at__lt=fin_ciclo,
    )
    sustituciones_mes = sustituciones_mes_qs.count()
    sustituciones_mes_restantes = (
        max(sustituciones_mes_limit - sustituciones_mes, 0)
        if sustituciones_mes_limit is not None
        else None
    )

    sustituciones_ruta_top = (
        sustituciones_mes_qs
        .filter(ruta__isnull=False)
        .values('ruta_id', 'ruta__titulo')
        .annotate(total=Count('id'))
        .order_by('-total', 'ruta_id')
        .first()
    )
    sustituciones_ruta_consumidas = int((sustituciones_ruta_top or {}).get('total') or 0)

    rutas_con_curiosidad = rutas_qs.filter(paradas__curiosidad__isnull=False).distinct().count()
    curiosidades_restantes = (
        max(curiosidades_limit - rutas_con_curiosidad, 0)
        if curiosidades_limit is not None
        else 0
    )

    return [
        {
            'nombre': 'Rutas manuales simultáneas',
            'restantes': max((manual_limit or 0) - rutas_manual, 0),
            'limite': manual_limit,
            'consumidas': rutas_manual,
            'detalle': 'Calculado en tiempo real con tus rutas actuales.',
        },
        {
            'nombre': 'Rutas IA simultáneas',
            'restantes': max((ia_limit or 0) - rutas_ia, 0),
            'limite': ia_limit,
            'consumidas': rutas_ia,
            'detalle': 'Calculado en tiempo real con tus rutas IA actuales.',
        },
        {
            'nombre': 'Capacidad por sesión',
            'restantes': capacidad_restante,
            'limite': personas_limit,
            'consumidas': capacidad_consumida,
            'detalle': (
                f"Sesión más ocupada: {capacidad_consumida}/{personas_limit} turistas "
                f"({getattr(sesion_mas_ocupada, 'codigo_acceso', 'sin sesiones activas')})."
                if sesion_mas_ocupada and personas_limit is not None
                else 'No hay sesiones activas; capacidad completa disponible.'
            ),
        },
        {
            'nombre': 'Paradas por ruta',
            'restantes': paradas_restantes,
            'limite': paradas_limit,
            'consumidas': paradas_consumidas,
            'detalle': (
                f"Ruta con más paradas: {paradas_consumidas}/{paradas_limit} "
                f"en «{ruta_mas_cargada.titulo}»."
                if ruta_mas_cargada and paradas_limit is not None
                else 'Aún no tienes rutas; límite completo disponible.'
            ),
        },
        {
            'nombre': 'Generaciones IA al mes',
            'restantes': generaciones_restantes,
            'limite': generaciones_limit,
            'consumidas': generaciones_mes,
            'detalle': (
                f'Usadas en el ciclo actual: {generaciones_mes} de {generaciones_limit}. '
                f'Inicio del ciclo: {timezone.localtime(inicio_ciclo).strftime("%d/%m/%Y %H:%M")}.'
            ),
        },
        {
            'nombre': 'Sustituciones IA (mes/ruta)',
            'restantes': sustituciones_mes_restantes,
            'limite': sustituciones_mes_limit,
            'consumidas': sustituciones_mes,
            'detalle': (
                (
                    f"Ciclo: {sustituciones_mes}/{sustituciones_mes_limit}. "
                    f"Ruta más usada: {sustituciones_ruta_consumidas}/{sustituciones_ruta_limit} "
                    f"en «{(sustituciones_ruta_top or {}).get('ruta__titulo', 'sin ruta')}». "
                    f'Inicio del ciclo: {timezone.localtime(inicio_ciclo).strftime("%d/%m/%Y %H:%M")}.'
                )
                if sustituciones_ruta_limit is not None
                else (
                    f"Ciclo: {sustituciones_mes}/{sustituciones_mes_limit}. "
                    'Por ruta: ilimitado en Premium. '
                    f'Inicio del ciclo: {timezone.localtime(inicio_ciclo).strftime("%d/%m/%Y %H:%M")}.'
                )
            ),
        },
        {
            'nombre': 'Rutas con curiosidades manuales',
            'restantes': curiosidades_restantes,
            'limite': curiosidades_limit,
            'consumidas': rutas_con_curiosidad,
            'detalle': (
                f'Rutas con curiosidades en uso: {rutas_con_curiosidad}.'
            ),
        },
    ]


def _estado_plan_humano(guia, subscription):
    if guia.tipo_suscripcion == Guia.Suscripcion.FREEMIUM:
        return 'Freemium activo'

    if subscription and subscription.cancel_at_period_end:
        return 'Premium activo (baja programada)'

    return 'Premium activo'


def _periodo_plan(guia, subscription):
    if guia.tipo_suscripcion == Guia.Suscripcion.FREEMIUM:
        return ('Próxima renovación', None)

    if subscription and subscription.current_period_end:
        fecha = timezone.localtime(subscription.current_period_end)
        if subscription.cancel_at_period_end:
            return ('Fin del periodo actual', fecha)
        return ('Próxima renovación', fecha)

    return ('Próxima renovación', None)


def _resolver_period_end_epoch(payload: dict) -> int | None:
    item_period_end = None
    items = ((payload.get('items') or {}).get('data') or [])
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            maybe_epoch = item.get('current_period_end')
            if maybe_epoch is not None:
                item_period_end = int(maybe_epoch)
                break
        except (TypeError, ValueError):
            continue

    for candidate in (payload.get('current_period_end'), payload.get('cancel_at'), item_period_end):
        try:
            if candidate is None:
                continue
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _refrescar_periodo_desde_stripe_si_falta(subscription):
    if subscription is None:
        return subscription
    if subscription.current_period_end is not None:
        return subscription
    if not getattr(settings, 'STRIPE_ENABLED', False):
        return subscription
    if not subscription.stripe_subscription_id:
        return subscription

    try:
        snapshot = fetch_subscription_snapshot(
            secret_key=getattr(settings, 'STRIPE_SECRET_KEY', ''),
            stripe_subscription_id=subscription.stripe_subscription_id,
        )
    except StripeAPIError as exc:
        logger.warning(
            'No se pudo refrescar periodo Stripe para suscripción %s: %s',
            subscription.stripe_subscription_id, exc,
        )
        return subscription
    except (requests.RequestException, TimeoutError) as exc:
        logger.warning(
            'Error de red al refrescar periodo Stripe para suscripción %s: %s',
            subscription.stripe_subscription_id, exc,
        )
        return subscription
    except (ValueError, TypeError, OSError) as exc:
        logger.warning(
            'Error procesando respuesta Stripe para suscripción %s: %s',
            subscription.stripe_subscription_id, exc,
        )
        return subscription

    period_end_epoch = _resolver_period_end_epoch(snapshot)
    period_end_dt = None
    try:
        if period_end_epoch is not None:
            period_end_dt = timezone.datetime.fromtimestamp(period_end_epoch, tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        period_end_dt = None

    updated_fields = []
    if period_end_dt is not None:
        subscription.current_period_end = period_end_dt
        updated_fields.append('current_period_end')

    cancel_at_period_end = bool(snapshot.get('cancel_at_period_end'))
    if subscription.cancel_at_period_end != cancel_at_period_end:
        subscription.cancel_at_period_end = cancel_at_period_end
        updated_fields.append('cancel_at_period_end')

    snapshot_status = str(snapshot.get('status') or '').strip()
    valid_statuses = {choice[0] for choice in Subscription.Status.choices}
    if snapshot_status and snapshot_status in valid_statuses and subscription.status != snapshot_status:
        subscription.status = snapshot_status
        updated_fields.append('status')

    if updated_fields:
        updated_fields.append('updated_at')
        subscription.save(update_fields=updated_fields)

    return subscription


# ================================================
# CATÁLOGO
# ================================================

@require_GET
@login_required
@user_passes_test(es_guia)
def rutas_catalogo(request):
    try:
        limit = int(request.GET.get("limit", 3))
        if limit <= 0:
            limit = 3
        elif limit > MAX_RUTAS_PAGE_SIZE:
            limit = MAX_RUTAS_PAGE_SIZE
    except (TypeError, ValueError):
        limit = 3

    try:
        page_number = int(request.GET.get("page", 1))
        if page_number < 1:
            page_number = 1
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
    guia = _obtener_guia_usuario(request.user)
    context = {
        'guia': guia,
        'es_freemium': (
            guia is not None and guia.tipo_suscripcion == Guia.Suscripcion.FREEMIUM
        ),
    }
    return render(request, 'rutas/catalogo.html', context)


@login_required
@require_http_methods(["GET", "POST"])
@user_passes_test(es_guia)
def editar_perfil_view(request):
    guia = _obtener_guia_usuario(request.user)
    if guia is None:
        raise PermissionDenied('No se encontró un perfil de guía para este usuario.')

    if request.method == "POST":
        form = EditarPerfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect(f"{request.path}?updated=1")
    else:
        form = EditarPerfilForm(instance=request.user)

    context = {
        'form': form,
        'guia': guia,
        'updated': request.GET.get("updated") == "1",
    }
    return render(request, 'rutas/perfil_editar.html', context)


@require_GET
@login_required
@user_passes_test(es_guia)
def plan_view(request):
    guia = _obtener_guia_usuario(request.user)
    if guia is None:
        raise PermissionDenied('No se encontró un perfil de guía para este usuario.')

    subscription = _obtener_suscripcion_actual(guia)
    subscription = _refrescar_periodo_desde_stripe_si_falta(subscription)
    es_freemium = guia.tipo_suscripcion == Guia.Suscripcion.FREEMIUM
    checkout_enabled = bool(getattr(settings, 'STRIPE_ENABLED', False))
    billing_state = (request.GET.get('billing') or '').strip()
    downgrade_state = (request.GET.get('downgrade') or '').strip()
    periodo_label, periodo_fecha = _periodo_plan(guia, subscription)

    mostrar_cta_downgrade = (
        not es_freemium
        and checkout_enabled
        and subscription is not None
        and bool(subscription.stripe_subscription_id)
        and not subscription.cancel_at_period_end
        and subscription.status in {
            Subscription.Status.ACTIVE,
            Subscription.Status.TRIALING,
            Subscription.Status.PAST_DUE,
        }
    )
    downgrade_programado = bool(
        subscription is not None and subscription.cancel_at_period_end
    )

    context = {
        'guia': guia,
        'subscription': subscription,
        'es_freemium': es_freemium,
        'checkout_enabled': checkout_enabled,
        'mostrar_cta_upgrade': es_freemium and checkout_enabled,
        'mostrar_cta_downgrade': mostrar_cta_downgrade,
        'downgrade_programado': downgrade_programado,
        'estado_plan': _estado_plan_humano(guia, subscription),
        'periodo_label': periodo_label,
        'periodo_fecha': periodo_fecha,
        'plan_usage_items': _calcular_usos_plan(guia),
        'plan_limits_actual': PLAN_LIMITS.get(guia.tipo_suscripcion, []),
        'plan_limits_premium': PLAN_LIMITS.get(Guia.Suscripcion.PREMIUM, []),
        'billing_success': billing_state == 'success',
        'billing_cancel': billing_state == 'cancel',
        'downgrade_scheduled': downgrade_state == 'scheduled',
    }
    return render(request, 'rutas/plan.html', context)


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
# DETALLE Y EDICIÓN DE RUTA
# ================================================

@login_required
@require_http_methods(["GET", "POST"])
@user_passes_test(es_guia)
def ruta_detalle_view(request, ruta_id):
    ruta = get_object_or_404(
        Ruta.objects.select_related("guia").prefetch_related("paradas"),
        id=ruta_id,
    )

    try:
        es_propietario = ruta.guia.user.user == request.user
    except AttributeError:
        es_propietario = False

    if not es_propietario:
        return _render_ruta_no_autorizada(request)

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
                # Validamos y aplicamos cambios de forma atómica para evitar
                # actualizaciones parciales cuando falla una regla de tier.
                with transaction.atomic():
                    services.actualizar_duracion_ruta(ruta, request.POST.get("duracion_horas"))
                    services.actualizar_personas_ruta(ruta, request.POST.get("num_personas"))
                    ensure_route_people_count_allowed(ruta.guia, ruta.num_personas)
                    services.actualizar_exigencia_ruta(ruta, request.POST.get("nivel_exigencia"))
                return redirect(f"{request.path}?meta_updated=1")
            except TierRuleViolation as exc:
                return _redirect_con_error_tier(request.path, exc)
            except ValueError:
                return redirect(f"{request.path}?meta_error=1")

        # ── Eliminar parada ───────────────────────────────────────────────────
        if form_type == "stop_delete":
            parada_id = request.POST.get("parada_id")
            parada = get_object_or_404(Parada, id=parada_id, ruta=ruta)
            try:
                services.eliminar_parada_y_reordenar(ruta, parada)
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")
            return redirect(f"{request.path}?stop_deleted=1")

        # ── Editar parada ─────────────────────────────────────────────────────
        if form_type == "stop_edit":
            parada_id = request.POST.get("parada_id")
            parada = get_object_or_404(Parada, id=parada_id, ruta=ruta)
            try:
                services.editar_parada(
                    parada,
                    request.POST.get("nombre"),
                    request.POST.get("lat"),
                    request.POST.get("lon"),
                    descripcion=request.POST.get("descripcion", ""),
                )
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

            return redirect(f"{request.path}?stop_updated=1")

        # ── Añadir parada ─────────────────────────────────────────────────────
        if form_type == "stop_add":
            try:
                ensure_route_stop_add_allowed(ruta)
            except TierRuleViolation as exc:
                return _redirect_con_error_tier(request.path, exc)

            try:
                services.añadir_parada(
                    ruta,
                    request.POST.get("nombre"),
                    request.POST.get("lat"),
                    request.POST.get("lon"),
                    descripcion=request.POST.get("descripcion", ""),
                )
            except ValueError:
                return redirect(f"{request.path}?stop_error=1")

            return redirect(f"{request.path}?stop_added=1")

        # ── Reordenar paradas ─────────────────────────────────────────────────
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

            return redirect(f"{request.path}?stop_reordered=1")

        # ── Etiquetas mood (sin efecto en la geometría) ───────────────────────
        if form_type == "mood":
            selected_moods = request.POST.getlist("mood")
            try:
                ensure_moods_allowed(ruta.guia, selected_moods)
            except TierRuleViolation as exc:
                return _redirect_con_error_tier(request.path, exc)

            services.actualizar_moods(ruta, selected_moods)
            return redirect(f"{request.path}?mood_updated=1")

        return redirect(request.path)

    # ── GET: construir contexto ────────────────────────────────────────────────
    ruta.refresh_from_db()
    paradas = sorted(ruta.paradas.all(), key=lambda p: p.orden)
    paradas_json = services.obtener_paradas_json(paradas)

    mood_choices_disponibles = get_allowed_moods_for_guia(ruta.guia)
    mood_choices_disponibles_set = set(mood_choices_disponibles)
    moods_actuales_norm, _unknown_moods = normalize_mood_values(ruta.mood or [])
    moods_actuales_visibles = [m for m in (ruta.mood or []) if m in mood_choices_disponibles_set]
    if not moods_actuales_visibles and moods_actuales_norm:
        moods_actuales_visibles = [m for m in moods_actuales_norm if m in mood_choices_disponibles_set]

    # Obtener IDs de paradas que ya tienen curiosidad
    paradas_con_curiosidad = set(
        Curiosidad.objects.filter(parada__ruta_id=ruta_id).values_list("parada_id", flat=True)
    )

    context = {
        "ruta": ruta,
        "paradas": paradas,
        "paradas_json": paradas_json,
        "paradas_con_curiosidad": paradas_con_curiosidad,
        # Geometría en formato Leaflet [[lat, lon], ...] (S2.1-31)
        "geometria_ruta_json": ruta.geometria_ruta_coords,
        # Métricas totales para el panel (S2.1-29)
        "distancia_total_km": ruta.distancia_total_km,
        "duracion_total_min": ruta.duracion_total_min,
        "mood_choices": [(v, l) for v, l in Ruta.Mood.choices if v in mood_choices_disponibles_set],
        "moods_actuales_visibles": moods_actuales_visibles,
        "tier_max_personas": get_session_capacity_limit(ruta.guia),
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
        "tier_code": request.GET.get("tier_code"),
        "tier_status": request.GET.get("tier_status"),
        "tier_message": unquote_plus(request.GET.get("tier_message", "")),
        "exigencia_choices": Ruta.Exigencia.choices,
        "ia_checkpoint_contexto": creacion_services.obtener_contexto_checkpoint_por_ruta(ruta.id),
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


@login_required
@require_GET
@user_passes_test(es_guia)
def obtener_curiosidad_parada_api(request, parada_id):
    """
        Obtiene la curiosidad de una parada.

        Modo por defecto:
            - Si existe en BD, se devuelve.
            - Si no existe, se genera con IA, se persiste y se devuelve.

        Modo preview (?preview=1):
            - Si existe en BD, se devuelve.
            - Si no existe, se genera con IA sin persistir.
    """
    paradas_qs = Parada.objects.select_related("ruta", "ruta__guia", "ruta__guia__user", "ruta__guia__user__user")

    if request.user.is_superuser:
        parada = get_object_or_404(paradas_qs, id=parada_id)
    else:
        parada = get_object_or_404(
            paradas_qs,
            id=parada_id,
            ruta__guia__user__user=request.user,
        )

    try:
        ensure_curiosity_route_allowed(parada.ruta)
    except TierRuleViolation as exc:
        return tier_error_response(exc)

    ciudad = (request.GET.get("ciudad") or "Sevilla").strip() or "Sevilla"
    preview_mode = str(request.GET.get("preview") or "").strip().lower() in {"1", "true", "yes"}

    if preview_mode:
        curiosidad_existente = Curiosidad.objects.filter(parada=parada).first()
        if curiosidad_existente:
            return JsonResponse(
                {
                    "status": "ok",
                    "generada": False,
                    "persistida": True,
                    "curiosidad": {
                        "id": curiosidad_existente.id,
                        "parada_id": curiosidad_existente.parada_id,
                        "ciudad": curiosidad_existente.ciudad,
                        "titulo": curiosidad_existente.titulo,
                        "texto": curiosidad_existente.texto,
                        "tipo": curiosidad_existente.tipo,
                        "imagen_url": curiosidad_existente.imagen_url,
                        "fecha_generacion": curiosidad_existente.fecha_generacion.isoformat(),
                    },
                },
                json_dumps_params={"ensure_ascii": False},
            )

        try:
            curiosidad_preview = services.generar_curiosidad_parada_preview(
                parada=parada,
                ciudad=ciudad,
            )
        except Exception as exc:
            return JsonResponse(
                {
                    "status": "error",
                    "mensaje": f"No se pudo generar la curiosidad: {exc}",
                },
                status=502,
            )

        return JsonResponse(
            {
                "status": "ok",
                "generada": True,
                "persistida": False,
                "curiosidad": {
                    "id": None,
                    "parada_id": curiosidad_preview["parada_id"],
                    "ciudad": curiosidad_preview["ciudad"],
                    "titulo": curiosidad_preview["titulo"],
                    "texto": curiosidad_preview["texto"],
                    "tipo": curiosidad_preview["tipo"],
                    "imagen_url": curiosidad_preview["imagen_url"],
                    "fecha_generacion": None,
                },
            },
            json_dumps_params={"ensure_ascii": False},
        )

    try:
        curiosidad, generada = services.obtener_o_generar_curiosidad_parada(
            parada=parada,
            ciudad=ciudad,
        )
    except Exception as exc:
        return JsonResponse(
            {
                "status": "error",
                "mensaje": f"No se pudo obtener la curiosidad: {exc}",
            },
            status=502,
        )

    return JsonResponse(
        {
            "status": "ok",
            "generada": generada,
            "persistida": True,
            "curiosidad": {
                "id": curiosidad.id,
                "parada_id": curiosidad.parada_id,
                "ciudad": curiosidad.ciudad,
                "titulo": curiosidad.titulo,
                "texto": curiosidad.texto,
                "tipo": curiosidad.tipo,
                "imagen_url": curiosidad.imagen_url,
                "fecha_generacion": curiosidad.fecha_generacion.isoformat(),
            },
        },
        json_dumps_params={"ensure_ascii": False},
    )


@login_required
@require_http_methods(["POST", "PUT"])
@user_passes_test(es_guia)
def guardar_curiosidad_parada_api(request, parada_id):
    """Guarda/actualiza una curiosidad manual por parada."""
    try:
        body = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"status": "error", "mensaje": "JSON inválido."},
            status=400,
        )

    texto = (body.get("texto") or "").strip()
    tipo = (body.get("tipo") or "").strip()
    if not texto:
        return JsonResponse(
            {"status": "error", "mensaje": "El campo 'texto' es obligatorio."},
            status=400,
        )
    if not tipo:
        return JsonResponse(
            {"status": "error", "mensaje": "El campo 'tipo' es obligatorio."},
            status=400,
        )

    tipos_validos = {choice[0] for choice in Curiosidad.TipoCuriosidad.choices}
    if tipo not in tipos_validos:
        return JsonResponse(
            {
                "status": "error",
                "mensaje": "Tipo inválido. Valores permitidos: "
                + ", ".join(sorted(tipos_validos)),
            },
            status=400,
        )

    parada_qs = Parada.objects.select_related(
        "ruta", "ruta__guia", "ruta__guia__user", "ruta__guia__user__user"
    )
    try:
        parada = parada_qs.get(id=parada_id)
    except Parada.DoesNotExist:
        return JsonResponse(
            {"status": "error", "mensaje": "Parada no encontrada."},
            status=404,
        )

    if not request.user.is_superuser and parada.ruta.guia.user.user != request.user:
        return JsonResponse(
            {"status": "error", "mensaje": "No tienes permisos para editar esta parada."},
            status=403,
        )

    try:
        ensure_curiosity_route_allowed(parada.ruta)
    except TierRuleViolation as exc:
        return tier_error_response(exc)

    titulo = (body.get("titulo") or "").strip() or f"Curiosidad: {parada.nombre}"
    imagen_url = (body.get("imagen_url") or "").strip() or None

    ciudad = (
        Curiosidad.objects.filter(parada=parada).values_list("ciudad", flat=True).first()
        or "Sevilla"
    )

    curiosidad, creada = Curiosidad.objects.get_or_create(
        parada=parada,
        defaults={
            "ciudad": ciudad,
            "titulo": titulo,
            "texto": texto,
            "tipo": tipo,
            "imagen_url": imagen_url,
        },
    )

    if not creada:
        curiosidad.titulo = titulo
        curiosidad.texto = texto
        curiosidad.tipo = tipo
        curiosidad.imagen_url = imagen_url
        curiosidad.save(update_fields=["titulo", "texto", "tipo", "imagen_url"])

    return JsonResponse(
        {
            "status": "ok",
            "creada": creada,
            "curiosidad": {
                "id": curiosidad.id,
                "parada_id": curiosidad.parada_id,
                "titulo": curiosidad.titulo,
                "texto": curiosidad.texto,
                "tipo": curiosidad.tipo,
                "ciudad": curiosidad.ciudad,
                "imagen_url": curiosidad.imagen_url,
                "fecha_generacion": curiosidad.fecha_generacion.isoformat(),
            },
        },
        json_dumps_params={"ensure_ascii": False},
    )


@login_required
@require_http_methods(["DELETE"])
@user_passes_test(es_guia)
def eliminar_curiosidad_parada_api(request, parada_id):
    """Elimina la curiosidad asociada a una parada."""
    parada_qs = Parada.objects.select_related(
        "ruta", "ruta__guia", "ruta__guia__user", "ruta__guia__user__user"
    )
    try:
        parada = parada_qs.get(id=parada_id)
    except Parada.DoesNotExist:
        return JsonResponse(
            {"status": "error", "mensaje": "Parada no encontrada."},
            status=404,
        )

    if not request.user.is_superuser and parada.ruta.guia.user.user != request.user:
        return JsonResponse(
            {"status": "error", "mensaje": "No tienes permisos para editar esta parada."},
            status=403,
        )

    curiosidad = Curiosidad.objects.filter(parada=parada).first()
    if not curiosidad:
        return JsonResponse(
            {"status": "error", "mensaje": "No existe curiosidad para esta parada."},
            status=404,
        )

    curiosidad_id = curiosidad.id
    curiosidad.delete()

    return JsonResponse(
        {
            "status": "ok",
            "mensaje": "Curiosidad eliminada correctamente.",
            "curiosidad_id": curiosidad_id,
        },
        json_dumps_params={"ensure_ascii": False},
    )
