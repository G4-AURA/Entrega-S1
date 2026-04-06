import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from billing.services import StripeAPIError
from billing.views import create_checkout_session_view
from rutas.models import Guia


class BillingCheckoutSessionViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, body: str = '{}'):
        request = self.factory.post(
            '/billing/create-checkout-session/',
            data=body,
            content_type='application/json',
        )
        return request

    def _json(self, response):
        return json.loads(response.content.decode('utf-8'))

    def _auth_user(self):
        return SimpleNamespace(
            id=101,
            email='guia@example.com',
            is_authenticated=True,
        )

    def test_rechaza_anonimo(self):
        request = self._request()
        request.user = SimpleNamespace(is_authenticated=False)

        response = create_checkout_session_view(request)

        self.assertEqual(response.status_code, 401)

    @override_settings(STRIPE_ENABLED=False)
    def test_rechaza_si_stripe_esta_deshabilitado(self):
        request = self._request()
        request.user = self._auth_user()

        response = create_checkout_session_view(request)

        self.assertEqual(response.status_code, 503)

    @override_settings(STRIPE_ENABLED=True)
    def test_rechaza_usuario_autenticado_sin_guia(self):
        request = self._request()
        request.user = self._auth_user()

        with patch('billing.views._obtener_guia_para_usuario', return_value=None):
            response = create_checkout_session_view(request)

        self.assertEqual(response.status_code, 403)

    @override_settings(STRIPE_ENABLED=True)
    def test_rechaza_json_invalido(self):
        request = self._request(body='{invalid')
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=9, tipo_suscripcion=Guia.Suscripcion.FREEMIUM)
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock):
            response = create_checkout_session_view(request)

        self.assertEqual(response.status_code, 400)

    @override_settings(STRIPE_ENABLED=True)
    def test_rechaza_si_ya_es_premium(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=9, tipo_suscripcion=Guia.Suscripcion.PREMIUM)
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock):
            response = create_checkout_session_view(request)

        self.assertEqual(response.status_code, 409)

    @override_settings(
        STRIPE_ENABLED=True,
        STRIPE_SECRET_KEY='sk_test_123',
        STRIPE_PREMIUM_PRICE_ID='price_123',
    )
    def test_devuelve_checkout_url_en_exito(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=9, tipo_suscripcion=Guia.Suscripcion.FREEMIUM)
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch(
                 'billing.views.create_checkout_session',
                 return_value={'id': 'cs_test_123', 'url': 'https://checkout.stripe.com/c/pay/cs_test_123'},
             ) as mock_checkout, \
             patch('billing.views.Subscription.objects.create') as mock_subscription_create:
            response = create_checkout_session_view(request)

        body = self._json(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['status'], 'OK')
        self.assertEqual(body['session_id'], 'cs_test_123')
        self.assertIn('checkout_url', body)
        self.assertTrue(body['checkout_url'].startswith('https://checkout.stripe.com/'))
        mock_checkout.assert_called_once()
        mock_subscription_create.assert_called_once()

    @override_settings(
        STRIPE_ENABLED=True,
        STRIPE_SECRET_KEY='sk_test_123',
        STRIPE_PREMIUM_PRICE_ID='price_123',
    )
    def test_error_de_stripe_devuelve_502(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=9, tipo_suscripcion=Guia.Suscripcion.FREEMIUM)
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch(
                 'billing.views.create_checkout_session',
                 side_effect=StripeAPIError('Stripe temporalmente no disponible'),
             ):
            response = create_checkout_session_view(request)

        body = self._json(response)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(body.get('code'), 'BILLING_STRIPE_ERROR')
