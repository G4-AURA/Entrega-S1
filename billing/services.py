import hashlib
import hmac
import time

import requests


class StripeAPIError(Exception):
    """Error controlado al invocar Stripe Checkout."""


class StripeSignatureVerificationError(Exception):
    """Firma webhook Stripe inválida o no verificable."""


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
