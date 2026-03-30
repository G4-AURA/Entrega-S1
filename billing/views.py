import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from rutas.models import Guia

from .models import Subscription
from .services import StripeAPIError, create_checkout_session

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
    success_url_default = f'{base_url}/catalogo/?billing=success'
    cancel_url_default = f'{base_url}/catalogo/?billing=cancel'

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
