import json
import logging
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from rutas.models import Guia

from .models import Subscription, WebhookEvent
from .services import (
    StripeAPIError,
    StripeSignatureVerificationError,
    create_checkout_session,
    fetch_subscription_snapshot,
    schedule_subscription_cancel_at_period_end,
    verify_stripe_signature,
)

logger = logging.getLogger(__name__)


def _obtener_guia_para_usuario(user):
    """
    Billing solo aplica a guías existentes.
    No creamos perfiles automáticamente desde este endpoint.
    """
    if not hasattr(user, 'auth_profile'):
        return None
    if not hasattr(user.auth_profile, 'guia'):
        return None
    return user.auth_profile.guia


def _resolver_urls_checkout(request, body: dict) -> tuple[str, str]:
    success_url_body = str(body.get('success_url') or '').strip()
    cancel_url_body = str(body.get('cancel_url') or '').strip()

    success_url_settings = str(getattr(settings, 'STRIPE_CHECKOUT_SUCCESS_URL', '') or '').strip()
    cancel_url_settings = str(getattr(settings, 'STRIPE_CHECKOUT_CANCEL_URL', '') or '').strip()

    base_url = request.build_absolute_uri('/').rstrip('/')
    success_url_default = f'{base_url}/perfil/plan/?billing=success'
    cancel_url_default = f'{base_url}/perfil/plan/?billing=cancel'

    success_url = success_url_body or success_url_settings or success_url_default
    cancel_url = cancel_url_body or cancel_url_settings or cancel_url_default
    return success_url, cancel_url


@csrf_exempt
@require_POST
def create_checkout_session_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Debes iniciar sesión para acceder al checkout.'},
            status=401,
        )

    if not getattr(settings, 'STRIPE_ENABLED', False):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Stripe no está habilitado en este entorno.'},
            status=503,
        )

    if hasattr(request.user, 'turista'):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Solo los guías pueden contratar el plan Premium.'},
            status=403,
        )

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'El cuerpo de la petición no es JSON válido.'},
            status=400,
        )

    guia = _obtener_guia_para_usuario(request.user)
    if guia is None:
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Solo los guías pueden cambiar de plan.'},
            status=403,
        )

    if guia.tipo_suscripcion == Guia.Suscripcion.PREMIUM:
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Ya tienes un plan Premium activo.'},
            status=409,
        )

    success_url, cancel_url = _resolver_urls_checkout(request, body)

    metadata = {
        'guia_id': str(guia.id),
        'user_id': str(request.user.id),
        'target_tier': Guia.Suscripcion.PREMIUM,
    }

    try:
        checkout = create_checkout_session(
            secret_key=getattr(settings, 'STRIPE_SECRET_KEY', ''),
            price_id=getattr(settings, 'STRIPE_PREMIUM_PRICE_ID', ''),
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=(request.user.email or None),
            client_reference_id=str(guia.id),
            metadata=metadata,
        )
    except StripeAPIError as exc:
        logger.warning('Error Stripe creando checkout session: %s', exc)
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': str(exc), 'code': 'BILLING_STRIPE_ERROR'},
            status=502,
        )
    except Exception:
        logger.exception('Error inesperado creando checkout session')
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'No se pudo iniciar el checkout.'},
            status=500,
        )

    Subscription.objects.create(
        guia=guia,
        provider=Subscription.Provider.STRIPE,
        tier=Guia.Suscripcion.PREMIUM,
        status=Subscription.Status.INCOMPLETE,
        stripe_price_id=getattr(settings, 'STRIPE_PREMIUM_PRICE_ID', ''),
        metadata={
            'checkout_session_id': checkout['id'],
            'checkout_url': checkout['url'],
        },
    )

    return JsonResponse(
        {
            'status': 'OK',
            'session_id': checkout['id'],
            'checkout_url': checkout['url'],
        },
        status=200,
    )


def _obtener_suscripcion_premium_cancelable(guia):
    return (
        Subscription.objects.filter(
            guia=guia,
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


@csrf_exempt
@require_POST
def schedule_downgrade_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Debes iniciar sesión para gestionar tu plan.'},
            status=401,
        )

    if not getattr(settings, 'STRIPE_ENABLED', False):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Stripe no está habilitado en este entorno.'},
            status=503,
        )

    if hasattr(request.user, 'turista'):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Solo los guías pueden gestionar su suscripción.'},
            status=403,
        )

    guia = _obtener_guia_para_usuario(request.user)
    if guia is None:
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Solo los guías pueden cambiar de plan.'},
            status=403,
        )

    if guia.tipo_suscripcion != Guia.Suscripcion.PREMIUM:
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Tu cuenta ya está en Freemium.'},
            status=409,
        )

    subscription = _obtener_suscripcion_premium_cancelable(guia)
    if subscription is None:
        return JsonResponse(
            {
                'status': 'ERROR',
                'mensaje': (
                    'No se encontró una suscripción Premium activa para programar la baja. '
                    'Revisa los webhooks de Stripe e inténtalo de nuevo.'
                ),
            },
            status=409,
        )

    if subscription.cancel_at_period_end:
        if subscription.current_period_end is None:
            try:
                stripe_subscription = fetch_subscription_snapshot(
                    secret_key=getattr(settings, 'STRIPE_SECRET_KEY', ''),
                    stripe_subscription_id=subscription.stripe_subscription_id,
                )
                period_end_dt = _epoch_to_datetime(
                    _resolver_period_end_epoch(stripe_subscription)
                )
                if period_end_dt is not None:
                    subscription.current_period_end = period_end_dt
                    subscription.save(update_fields=['current_period_end', 'updated_at'])
            except StripeAPIError:
                logger.warning(
                    'No se pudo refrescar current_period_end para suscripción %s',
                    subscription.stripe_subscription_id,
                )
            except Exception:
                logger.exception(
                    'Error inesperado refrescando current_period_end para suscripción %s',
                    subscription.stripe_subscription_id,
                )

        return JsonResponse(
            {
                'status': 'OK',
                'mensaje': 'La baja ya estaba programada para el final del periodo actual.',
                'current_period_end': (
                    subscription.current_period_end.isoformat()
                    if subscription.current_period_end
                    else None
                ),
            },
            status=200,
        )

    try:
        stripe_subscription = schedule_subscription_cancel_at_period_end(
            secret_key=getattr(settings, 'STRIPE_SECRET_KEY', ''),
            stripe_subscription_id=subscription.stripe_subscription_id,
        )
    except StripeAPIError as exc:
        logger.warning('Error Stripe programando downgrade: %s', exc)
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': str(exc), 'code': 'BILLING_STRIPE_ERROR'},
            status=502,
        )
    except Exception:
        logger.exception('Error inesperado programando downgrade Stripe')
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'No se pudo programar la baja de Premium.'},
            status=500,
        )

    updated_fields = ['cancel_at_period_end', 'status', 'metadata', 'updated_at']
    subscription.cancel_at_period_end = bool(stripe_subscription.get('cancel_at_period_end'))
    subscription.status = _normalizar_status(
        str(stripe_subscription.get('status') or subscription.status).strip()
    )

    period_end = _epoch_to_datetime(_resolver_period_end_epoch(stripe_subscription))
    if period_end is not None:
        subscription.current_period_end = period_end
        updated_fields.append('current_period_end')

    canceled_at = _epoch_to_datetime(stripe_subscription.get('canceled_at'))
    if canceled_at is not None:
        subscription.canceled_at = canceled_at
        updated_fields.append('canceled_at')

    existing_metadata = subscription.metadata if isinstance(subscription.metadata, dict) else {}
    subscription.metadata = {
        **existing_metadata,
        'downgrade_requested_at': timezone.now().isoformat(),
    }
    subscription.save(update_fields=updated_fields)

    return JsonResponse(
        {
            'status': 'OK',
            'mensaje': 'Baja programada. Mantendrás Premium hasta el fin de tu periodo actual.',
            'current_period_end': (
                subscription.current_period_end.isoformat()
                if subscription.current_period_end
                else None
            ),
        },
        status=200,
    )


def _epoch_to_datetime(value):
    try:
        if value is None:
            return None
        return timezone.datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _resolver_period_end_epoch(payload: dict) -> int | None:
    raw_current_period_end = payload.get('current_period_end')
    raw_cancel_at = payload.get('cancel_at')

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

    for candidate in (raw_current_period_end, raw_cancel_at, item_period_end):
        try:
            if candidate is None:
                continue
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _normalizar_status(raw_status: str) -> str:
    valid_statuses = {choice[0] for choice in Subscription.Status.choices}
    if raw_status in valid_statuses:
        return raw_status
    return Subscription.Status.INCOMPLETE


def _resolver_guia_por_metadata(metadata: dict):
    guia_id = str((metadata or {}).get('guia_id') or '').strip()
    if not guia_id.isdigit():
        return None
    return Guia.objects.filter(id=int(guia_id)).first()


def _sincronizar_tipo_suscripcion_guia(guia, status: str):
    if guia is None:
        return

    if status in {
        Subscription.Status.ACTIVE,
        Subscription.Status.TRIALING,
        Subscription.Status.PAST_DUE,
    }:
        target = Guia.Suscripcion.PREMIUM
    elif status in {
        Subscription.Status.CANCELED,
        Subscription.Status.UNPAID,
        Subscription.Status.INCOMPLETE_EXPIRED,
    }:
        target = Guia.Suscripcion.FREEMIUM
    else:
        return

    if guia.tipo_suscripcion != target:
        guia.tipo_suscripcion = target
        guia.save(update_fields=['tipo_suscripcion'])


def _procesar_checkout_completed(data_object: dict):
    if data_object.get('mode') != 'subscription':
        return None

    metadata = data_object.get('metadata') or {}
    guia = _resolver_guia_por_metadata(metadata)
    stripe_subscription_id = str(data_object.get('subscription') or '').strip()
    stripe_customer_id = str(data_object.get('customer') or '').strip()
    checkout_session_id = str(data_object.get('id') or '').strip()

    subscription = None
    if stripe_subscription_id:
        subscription = Subscription.objects.filter(
            stripe_subscription_id=stripe_subscription_id
        ).select_related('guia').first()

    if subscription is None and guia is not None:
        subscription = (
            Subscription.objects.filter(
                guia=guia,
                tier=Guia.Suscripcion.PREMIUM,
                status=Subscription.Status.INCOMPLETE,
            )
            .order_by('-created_at')
            .first()
        )

    if subscription is None and guia is not None:
        subscription = Subscription(guia=guia, tier=Guia.Suscripcion.PREMIUM)

    if subscription is None:
        return None

    payment_status = str(data_object.get('payment_status') or '').strip()
    status = Subscription.Status.ACTIVE if payment_status == 'paid' else Subscription.Status.INCOMPLETE
    existing_metadata = subscription.metadata if isinstance(subscription.metadata, dict) else {}

    if stripe_subscription_id and getattr(settings, 'STRIPE_ENABLED', False):
        try:
            snapshot = fetch_subscription_snapshot(
                secret_key=getattr(settings, 'STRIPE_SECRET_KEY', ''),
                stripe_subscription_id=stripe_subscription_id,
            )
            snapshot_status = str(snapshot.get('status') or '').strip()
            if snapshot_status:
                status = _normalizar_status(snapshot_status)
            subscription.current_period_end = _epoch_to_datetime(
                _resolver_period_end_epoch(snapshot)
            )
            subscription.cancel_at_period_end = bool(snapshot.get('cancel_at_period_end'))
            subscription.canceled_at = _epoch_to_datetime(snapshot.get('canceled_at'))
        except StripeAPIError:
            logger.warning(
                'No se pudo refrescar snapshot Stripe tras checkout para %s',
                stripe_subscription_id,
            )
        except Exception:
            logger.exception(
                'Error inesperado refrescando snapshot Stripe tras checkout para %s',
                stripe_subscription_id,
            )

    subscription.provider = Subscription.Provider.STRIPE
    subscription.status = status
    subscription.stripe_customer_id = stripe_customer_id or subscription.stripe_customer_id
    subscription.stripe_subscription_id = stripe_subscription_id or subscription.stripe_subscription_id
    subscription.metadata = {
        **existing_metadata,
        'checkout_session_id': checkout_session_id,
        'checkout_status': str(data_object.get('status') or ''),
    }
    subscription.save()

    _sincronizar_tipo_suscripcion_guia(subscription.guia, subscription.status)
    return subscription


def _procesar_subscription_event(data_object: dict):
    stripe_subscription_id = str(data_object.get('id') or '').strip()
    if not stripe_subscription_id:
        return None

    status = _normalizar_status(str(data_object.get('status') or '').strip())
    stripe_customer_id = str(data_object.get('customer') or '').strip()

    items = ((data_object.get('items') or {}).get('data') or [])
    stripe_price_id = ''
    if items and isinstance(items[0], dict):
        stripe_price_id = str(((items[0].get('price') or {}).get('id')) or '').strip()

    metadata = data_object.get('metadata') or {}
    subscription = Subscription.objects.filter(
        stripe_subscription_id=stripe_subscription_id
    ).select_related('guia').first()
    guia = subscription.guia if subscription else _resolver_guia_por_metadata(metadata)

    if subscription is None and guia is not None:
        subscription = Subscription(
            guia=guia,
            tier=Guia.Suscripcion.PREMIUM,
        )

    if subscription is None:
        return None

    existing_metadata = subscription.metadata if isinstance(subscription.metadata, dict) else {}
    subscription.provider = Subscription.Provider.STRIPE
    subscription.status = status
    subscription.stripe_customer_id = stripe_customer_id or subscription.stripe_customer_id
    subscription.stripe_subscription_id = stripe_subscription_id
    subscription.stripe_price_id = stripe_price_id or subscription.stripe_price_id
    subscription.current_period_start = _epoch_to_datetime(data_object.get('current_period_start'))
    subscription.current_period_end = _epoch_to_datetime(_resolver_period_end_epoch(data_object))
    subscription.cancel_at_period_end = bool(data_object.get('cancel_at_period_end'))
    subscription.canceled_at = _epoch_to_datetime(data_object.get('canceled_at'))
    subscription.metadata = {**existing_metadata, **metadata}
    subscription.save()

    _sincronizar_tipo_suscripcion_guia(subscription.guia, subscription.status)
    return subscription


def _procesar_evento_stripe(payload_evento: dict):
    event_type = str(payload_evento.get('type') or '').strip()
    data_object = ((payload_evento.get('data') or {}).get('object') or {})

    if event_type == 'checkout.session.completed':
        return _procesar_checkout_completed(data_object)

    if event_type.startswith('customer.subscription.'):
        return _procesar_subscription_event(data_object)

    return None


@csrf_exempt
@require_POST
def stripe_webhook_view(request):
    if not getattr(settings, 'STRIPE_ENABLED', False):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Stripe no está habilitado en este entorno.'},
            status=503,
        )

    raw_payload = request.body or b''
    signature_header = request.headers.get('Stripe-Signature', '')
    try:
        verify_stripe_signature(
            payload=raw_payload,
            signature_header=signature_header,
            webhook_secret=getattr(settings, 'STRIPE_WEBHOOK_SECRET', ''),
            tolerance_seconds=int(getattr(settings, 'STRIPE_WEBHOOK_TOLERANCE_SECONDS', 300)),
        )
    except (TypeError, ValueError):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Tolerancia de firma inválida en configuración.'},
            status=500,
        )
    except StripeSignatureVerificationError as exc:
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': str(exc), 'code': 'BILLING_INVALID_SIGNATURE'},
            status=400,
        )

    try:
        payload_evento = json.loads(raw_payload.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Payload webhook no es JSON válido.'},
            status=400,
        )

    event_id = str(payload_evento.get('id') or '').strip()
    event_type = str(payload_evento.get('type') or '').strip()
    if not event_id:
        return JsonResponse(
            {'status': 'ERROR', 'mensaje': 'Evento webhook sin id.'},
            status=400,
        )

    with transaction.atomic():
        webhook_event, created = WebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                'provider': Subscription.Provider.STRIPE,
                'event_type': event_type,
                'livemode': bool(payload_evento.get('livemode')),
                'api_version': str(payload_evento.get('api_version') or ''),
                'payload': payload_evento,
            },
        )

        if not created:
            return JsonResponse(
                {'status': 'OK', 'duplicated': True, 'event_id': event_id},
                status=200,
            )

        try:
            subscription = _procesar_evento_stripe(payload_evento)
            webhook_event.subscription = subscription
            webhook_event.processed = True
            webhook_event.processed_at = timezone.now()
            webhook_event.save(update_fields=['subscription', 'processed', 'processed_at', 'updated_at'])
        except Exception as exc:
            logger.exception('Error procesando webhook Stripe %s', event_id)
            webhook_event.processing_error = str(exc)
            webhook_event.save(update_fields=['processing_error', 'updated_at'])
            return JsonResponse(
                {'status': 'ERROR', 'mensaje': 'No se pudo procesar el evento webhook.'},
                status=500,
            )

    return JsonResponse(
        {'status': 'OK', 'event_id': event_id, 'event_type': event_type},
        status=200,
    )
