import hashlib
import hmac
import time
import json
import requests


class StripeAPIError(Exception):
    """Error controlado al invocar Stripe Checkout."""


class StripeSignatureVerificationError(Exception):
    """Firma webhook Stripe inválida o no verificable."""


def _coerce_epoch(value) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_items_current_period_end(payload: dict) -> int | None:
    items = ((payload.get('items') or {}).get('data') or [])
    candidates: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        epoch = _coerce_epoch(item.get('current_period_end'))
        if epoch is not None:
            candidates.append(epoch)
    return max(candidates) if candidates else None


def _extract_invoice_period_end(payload: dict) -> int | None:
    lines = ((payload.get('lines') or {}).get('data') or [])
    candidates: list[int] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        epoch = _coerce_epoch((line.get('period') or {}).get('end'))
        if epoch is not None:
            candidates.append(epoch)
    return max(candidates) if candidates else None


def _resolve_period_end_epoch(payload: dict) -> int | None:
    for candidate in (
        _coerce_epoch(payload.get('current_period_end')),
        _coerce_epoch(payload.get('cancel_at')),
        _extract_items_current_period_end(payload),
    ):
        if candidate is not None:
            return candidate
    return None


def _fetch_upcoming_invoice_period_end(
    *,
    secret_key: str,
    stripe_subscription_id: str,
) -> int | None:
    try:
        response = requests.get(
            'https://api.stripe.com/v1/invoices/upcoming',
            headers={'Authorization': f'Bearer {secret_key}'},
            params={'subscription': stripe_subscription_id},
            timeout=30,
        )
    except requests.RequestException:
        return None

    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {}

    if response.status_code >= 400 or not isinstance(payload, dict):
        return None

    for candidate in (
        _coerce_epoch(payload.get('period_end')),
        _coerce_epoch(payload.get('next_payment_attempt')),
        _extract_invoice_period_end(payload),
    ):
        if candidate is not None:
            return candidate
    return None


def create_checkout_session(
    *,
    secret_key: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    customer_email: str | None = None,
    client_reference_id: str | None = None,
    metadata: dict[str, str] | None = None,
) -> dict:
    """
    Crea una sesión de Stripe Checkout (modo suscripción) usando la API HTTP.
    Devuelve al menos {'id': 'cs_...', 'url': 'https://checkout.stripe.com/...'}.
    """
    if not secret_key:
        raise StripeAPIError('Falta STRIPE_SECRET_KEY.')
    if not price_id:
        raise StripeAPIError('Falta STRIPE_PREMIUM_PRICE_ID.')

    data: dict[str, str] = {
        'mode': 'subscription',
        'success_url': success_url,
        'cancel_url': cancel_url,
        'line_items[0][price]': price_id,
        'line_items[0][quantity]': '1',
    }
    if customer_email:
        data['customer_email'] = customer_email
    if client_reference_id:
        data['client_reference_id'] = client_reference_id
    for key, value in (metadata or {}).items():
        data[f'metadata[{key}]'] = value
        data[f'subscription_data[metadata][{key}]'] = value

    try:
        response = requests.post(
            'https://api.stripe.com/v1/checkout/sessions',
            headers={'Authorization': f'Bearer {secret_key}'},
            data=data,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise StripeAPIError(f'No se pudo contactar con Stripe: {exc}') from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        stripe_error = (
            payload.get('error', {}).get('message')
            if isinstance(payload, dict)
            else None
        )
        raise StripeAPIError(stripe_error or 'Stripe devolvió un error al crear checkout.')

    session_id = payload.get('id') if isinstance(payload, dict) else None
    checkout_url = payload.get('url') if isinstance(payload, dict) else None
    if not session_id or not checkout_url:
        raise StripeAPIError('Stripe no devolvió id/url de la sesión de checkout.')

    return {'id': session_id, 'url': checkout_url}


def fetch_checkout_session(
    *,
    secret_key: str,
    checkout_session_id: str,
) -> dict:
    """
    Recupera una sesión de Stripe Checkout.

    Devuelve al menos:
      {
        'id': 'cs_...',
        'mode': 'subscription|...',
        'status': 'open|complete|expired',
        'payment_status': 'paid|unpaid|no_payment_required',
        'customer': 'cus_...' | '',
        'subscription': 'sub_...' | '',
        'client_reference_id': '...' | '',
        'metadata': {...},
      }
    """
    if not secret_key:
        raise StripeAPIError('Falta STRIPE_SECRET_KEY.')
    if not checkout_session_id:
        raise StripeAPIError('Falta checkout_session_id.')

    try:
        response = requests.get(
            f'https://api.stripe.com/v1/checkout/sessions/{checkout_session_id}',
            headers={'Authorization': f'Bearer {secret_key}'},
            params={'expand[]': 'subscription'},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise StripeAPIError(f'No se pudo contactar con Stripe: {exc}') from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        stripe_error = (
            payload.get('error', {}).get('message')
            if isinstance(payload, dict)
            else None
        )
        raise StripeAPIError(
            stripe_error or 'Stripe devolvió un error al recuperar la sesión de checkout.'
        )

    session_id = payload.get('id') if isinstance(payload, dict) else None
    if not session_id:
        raise StripeAPIError('Stripe no devolvió id de sesión de checkout.')

    subscription_raw = payload.get('subscription') if isinstance(payload, dict) else None
    if isinstance(subscription_raw, dict):
        subscription_id = str(subscription_raw.get('id') or '').strip()
    else:
        subscription_id = str(subscription_raw or '').strip()

    metadata_raw = payload.get('metadata') if isinstance(payload, dict) else None
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}

    return {
        'id': str(session_id).strip(),
        'mode': str(payload.get('mode') or '').strip() if isinstance(payload, dict) else '',
        'status': str(payload.get('status') or '').strip() if isinstance(payload, dict) else '',
        'payment_status': (
            str(payload.get('payment_status') or '').strip()
            if isinstance(payload, dict)
            else ''
        ),
        'customer': str(payload.get('customer') or '').strip() if isinstance(payload, dict) else '',
        'subscription': subscription_id,
        'client_reference_id': (
            str(payload.get('client_reference_id') or '').strip()
            if isinstance(payload, dict)
            else ''
        ),
        'metadata': metadata,
    }


def schedule_subscription_cancel_at_period_end(
    *,
    secret_key: str,
    stripe_subscription_id: str,
) -> dict:
    """
    Programa una suscripción de Stripe para no renovar al final del periodo.
    Devuelve al menos:
      {
        'id': 'sub_...',
        'status': 'active|...',
        'cancel_at_period_end': True,
        'current_period_end': 1714500000 | None,
        'canceled_at': 1714500000 | None,
      }
    """
    if not secret_key:
        raise StripeAPIError('Falta STRIPE_SECRET_KEY.')
    if not stripe_subscription_id:
        raise StripeAPIError('Falta stripe_subscription_id para programar la baja.')

    try:
        response = requests.post(
            f'https://api.stripe.com/v1/subscriptions/{stripe_subscription_id}',
            headers={'Authorization': f'Bearer {secret_key}'},
            data={'cancel_at_period_end': 'true'},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise StripeAPIError(f'No se pudo contactar con Stripe: {exc}') from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        stripe_error = (
            payload.get('error', {}).get('message')
            if isinstance(payload, dict)
            else None
        )
        raise StripeAPIError(stripe_error or 'Stripe devolvió un error al programar la baja.')

    subscription_id = payload.get('id') if isinstance(payload, dict) else None
    if not subscription_id:
        raise StripeAPIError('Stripe no devolvió id de suscripción tras programar la baja.')

    return {
        'id': subscription_id,
        'status': payload.get('status') if isinstance(payload, dict) else None,
        'cancel_at_period_end': bool(payload.get('cancel_at_period_end')) if isinstance(payload, dict) else True,
        'current_period_end': payload.get('current_period_end') if isinstance(payload, dict) else None,
        'cancel_at': payload.get('cancel_at') if isinstance(payload, dict) else None,
        'canceled_at': payload.get('canceled_at') if isinstance(payload, dict) else None,
    }


def fetch_subscription_snapshot(
    *,
    secret_key: str,
    stripe_subscription_id: str,
) -> dict:
    """
    Recupera una suscripción concreta de Stripe.
    """
    if not secret_key:
        raise StripeAPIError('Falta STRIPE_SECRET_KEY.')
    if not stripe_subscription_id:
        raise StripeAPIError('Falta stripe_subscription_id.')

    try:
        response = requests.get(
            f'https://api.stripe.com/v1/subscriptions/{stripe_subscription_id}',
            headers={'Authorization': f'Bearer {secret_key}'},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise StripeAPIError(f'No se pudo contactar con Stripe: {exc}') from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        stripe_error = (
            payload.get('error', {}).get('message')
            if isinstance(payload, dict)
            else None
        )
        raise StripeAPIError(stripe_error or 'Stripe devolvió un error al recuperar la suscripción.')

    subscription_id = payload.get('id') if isinstance(payload, dict) else None
    if not subscription_id:
        raise StripeAPIError('Stripe no devolvió id de suscripción.')

    resolved_period_end = _resolve_period_end_epoch(payload if isinstance(payload, dict) else {})
    if resolved_period_end is None:
        resolved_period_end = _fetch_upcoming_invoice_period_end(
            secret_key=secret_key,
            stripe_subscription_id=stripe_subscription_id,
        )

    return {
        'id': subscription_id,
        'status': payload.get('status') if isinstance(payload, dict) else None,
        'cancel_at_period_end': bool(payload.get('cancel_at_period_end')) if isinstance(payload, dict) else False,
        'current_period_end': resolved_period_end,
        'cancel_at': payload.get('cancel_at') if isinstance(payload, dict) else None,
        'canceled_at': payload.get('canceled_at') if isinstance(payload, dict) else None,
    }


def _parse_stripe_signature_header(signature_header: str) -> tuple[int, list[str]]:
    if not signature_header:
        raise StripeSignatureVerificationError('Falta cabecera Stripe-Signature.')

    timestamp = None
    signatures: list[str] = []
    for part in signature_header.split(','):
        key, _, value = part.strip().partition('=')
        if key == 't':
            try:
                timestamp = int(value)
            except (TypeError, ValueError) as exc:
                raise StripeSignatureVerificationError('Timestamp de firma inválido.') from exc
        elif key == 'v1' and value:
            signatures.append(value)

    if timestamp is None:
        raise StripeSignatureVerificationError('Falta timestamp en Stripe-Signature.')
    if not signatures:
        raise StripeSignatureVerificationError('Falta firma v1 en Stripe-Signature.')
    return timestamp, signatures


def verify_stripe_signature(
    *,
    payload: bytes,
    signature_header: str,
    webhook_secret: str,
    tolerance_seconds: int = 300,
) -> None:
    """
    Verifica firma Stripe según el esquema: t=<ts>,v1=<hmac_sha256>.
    Lanza StripeSignatureVerificationError si la firma no es válida.
    """
    if not webhook_secret:
        raise StripeSignatureVerificationError('Falta STRIPE_WEBHOOK_SECRET.')

    timestamp, signatures = _parse_stripe_signature_header(signature_header)

    now = int(time.time())
    if tolerance_seconds > 0 and abs(now - timestamp) > tolerance_seconds:
        raise StripeSignatureVerificationError('La firma webhook está fuera de ventana temporal.')

    signed_payload = f'{timestamp}.'.encode('utf-8') + payload
    expected = hmac.new(
        webhook_secret.encode('utf-8'),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise StripeSignatureVerificationError('Firma webhook inválida.')
