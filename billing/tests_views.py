import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from billing.services import StripeAPIError
from billing.views import create_checkout_session_view
from billing.views import schedule_downgrade_view
from billing.views import sync_checkout_session_view
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
        self.assertIn(
            '{CHECKOUT_SESSION_ID}',
            str(mock_checkout.call_args.kwargs.get('success_url') or ''),
        )
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


class BillingSyncCheckoutSessionViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, body: str = '{}'):
        return self.factory.post(
            '/billing/sync-checkout-session/',
            data=body,
            content_type='application/json',
        )

    def _json(self, response):
        return json.loads(response.content.decode('utf-8'))

    def _auth_user(self):
        return SimpleNamespace(
            id=301,
            email='guia-sync@example.com',
            is_authenticated=True,
        )

    @override_settings(STRIPE_ENABLED=True)
    def test_rechaza_anonimo(self):
        request = self._request()
        request.user = SimpleNamespace(is_authenticated=False)

        response = sync_checkout_session_view(request)

        self.assertEqual(response.status_code, 401)

    @override_settings(STRIPE_ENABLED=False)
    def test_rechaza_si_stripe_esta_deshabilitado(self):
        request = self._request()
        request.user = self._auth_user()

        response = sync_checkout_session_view(request)

        self.assertEqual(response.status_code, 503)

    @override_settings(STRIPE_ENABLED=True)
    def test_rechaza_si_no_hay_checkout_pendiente(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=9, tipo_suscripcion=Guia.Suscripcion.FREEMIUM)
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch('billing.views._find_pending_checkout_subscription', return_value=None):
            response = sync_checkout_session_view(request)

        body = self._json(response)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(body.get('code'), 'BILLING_NOTHING_TO_SYNC')

    @override_settings(
        STRIPE_ENABLED=True,
        STRIPE_SECRET_KEY='sk_test_123',
    )
    def test_sincroniza_checkout_y_devuelve_estado_de_suscripcion(self):
        request = self._request(body='{"session_id":"cs_test_sync_123"}')
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=9, tipo_suscripcion=Guia.Suscripcion.FREEMIUM)
        pending_subscription = SimpleNamespace(
            metadata={'checkout_session_id': 'cs_test_sync_123'},
        )
        synced_subscription = SimpleNamespace(
            status='active',
            stripe_subscription_id='sub_test_sync_123',
            current_period_end=None,
        )

        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch('billing.views._find_pending_checkout_subscription', return_value=pending_subscription), \
             patch(
                 'billing.views.fetch_checkout_session',
                 return_value={
                     'id': 'cs_test_sync_123',
                     'mode': 'subscription',
                     'status': 'complete',
                     'payment_status': 'paid',
                     'customer': 'cus_test_sync_123',
                     'subscription': 'sub_test_sync_123',
                     'metadata': {},
                     'client_reference_id': '9',
                 },
             ), \
             patch('billing.views._procesar_checkout_completed', return_value=synced_subscription) as mock_process:
            response = sync_checkout_session_view(request)

        body = self._json(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body.get('status'), 'OK')
        self.assertEqual(body.get('subscription_status'), 'active')
        payload_checkout = mock_process.call_args.args[0]
        self.assertEqual(payload_checkout.get('metadata', {}).get('guia_id'), '9')


class BillingDowngradeViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self):
        return self.factory.post('/billing/schedule-downgrade/', data='{}', content_type='application/json')

    def _json(self, response):
        return json.loads(response.content.decode('utf-8'))

    def _auth_user(self):
        return SimpleNamespace(
            id=201,
            email='premium@example.com',
            is_authenticated=True,
        )

    @override_settings(STRIPE_ENABLED=True)
    def test_rechaza_anonimo(self):
        request = self._request()
        request.user = SimpleNamespace(is_authenticated=False)

        response = schedule_downgrade_view(request)

        self.assertEqual(response.status_code, 401)

    @override_settings(STRIPE_ENABLED=False)
    def test_rechaza_si_stripe_esta_deshabilitado(self):
        request = self._request()
        request.user = self._auth_user()

        response = schedule_downgrade_view(request)

        self.assertEqual(response.status_code, 503)

    @override_settings(STRIPE_ENABLED=True)
    def test_rechaza_si_ya_es_freemium(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=11, tipo_suscripcion=Guia.Suscripcion.FREEMIUM)
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock):
            response = schedule_downgrade_view(request)

        self.assertEqual(response.status_code, 409)

    @override_settings(STRIPE_ENABLED=True)
    def test_rechaza_sin_suscripcion_cancelable(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=11, tipo_suscripcion=Guia.Suscripcion.PREMIUM)
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch('billing.views._obtener_suscripcion_premium_cancelable', return_value=None):
            response = schedule_downgrade_view(request)

        self.assertEqual(response.status_code, 409)

    @override_settings(STRIPE_ENABLED=True)
    def test_devuelve_ok_si_ya_estaba_programada(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=11, tipo_suscripcion=Guia.Suscripcion.PREMIUM)
        subscription_mock = SimpleNamespace(
            stripe_subscription_id='sub_test_already_scheduled',
            cancel_at_period_end=True,
            current_period_end=None,
        )
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch('billing.views._obtener_suscripcion_premium_cancelable', return_value=subscription_mock):
            response = schedule_downgrade_view(request)

        self.assertEqual(response.status_code, 200)
        body = self._json(response)
        self.assertEqual(body.get('status'), 'OK')

    @override_settings(
        STRIPE_ENABLED=True,
        STRIPE_SECRET_KEY='sk_test_123',
    )
    def test_error_de_stripe_devuelve_502(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=11, tipo_suscripcion=Guia.Suscripcion.PREMIUM)
        subscription_mock = SimpleNamespace(
            stripe_subscription_id='sub_test_123',
            cancel_at_period_end=False,
            status='active',
            current_period_end=None,
            canceled_at=None,
            metadata={},
            save=MagicMock(),
        )
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch('billing.views._obtener_suscripcion_premium_cancelable', return_value=subscription_mock), \
             patch(
                 'billing.views.schedule_subscription_cancel_at_period_end',
                 side_effect=StripeAPIError('Stripe temporalmente no disponible'),
             ):
            response = schedule_downgrade_view(request)

        self.assertEqual(response.status_code, 502)

    @override_settings(
        STRIPE_ENABLED=True,
        STRIPE_SECRET_KEY='sk_test_123',
    )
    def test_programa_baja_con_exito(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=11, tipo_suscripcion=Guia.Suscripcion.PREMIUM)
        subscription_mock = SimpleNamespace(
            stripe_subscription_id='sub_test_123',
            cancel_at_period_end=False,
            status='active',
            current_period_end=None,
            canceled_at=None,
            metadata={},
            save=MagicMock(),
        )
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch('billing.views._obtener_suscripcion_premium_cancelable', return_value=subscription_mock), \
             patch(
                 'billing.views.schedule_subscription_cancel_at_period_end',
                 return_value={
                     'id': 'sub_test_123',
                     'status': 'active',
                     'cancel_at_period_end': True,
                     'current_period_end': 1714500000,
                     'canceled_at': None,
                 },
             ):
            response = schedule_downgrade_view(request)

        body = self._json(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body.get('status'), 'OK')
        self.assertTrue(subscription_mock.cancel_at_period_end)
        subscription_mock.save.assert_called_once()

    @override_settings(
        STRIPE_ENABLED=True,
        STRIPE_SECRET_KEY='sk_test_123',
    )
    def test_programa_baja_con_fallback_cancel_at(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=11, tipo_suscripcion=Guia.Suscripcion.PREMIUM)
        subscription_mock = SimpleNamespace(
            stripe_subscription_id='sub_test_456',
            cancel_at_period_end=False,
            status='active',
            current_period_end=None,
            canceled_at=None,
            metadata={},
            save=MagicMock(),
        )
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch('billing.views._obtener_suscripcion_premium_cancelable', return_value=subscription_mock), \
             patch(
                 'billing.views.schedule_subscription_cancel_at_period_end',
                 return_value={
                     'id': 'sub_test_456',
                     'status': 'active',
                     'cancel_at_period_end': True,
                     'current_period_end': None,
                     'cancel_at': 1714600000,
                     'canceled_at': None,
                 },
             ):
            response = schedule_downgrade_view(request)

        body = self._json(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body.get('status'), 'OK')
        self.assertIsNotNone(subscription_mock.current_period_end)

    @override_settings(
        STRIPE_ENABLED=True,
        STRIPE_SECRET_KEY='sk_test_123',
    )
    def test_ya_programada_refresca_period_end_si_falta(self):
        request = self._request()
        request.user = self._auth_user()

        guia_mock = SimpleNamespace(id=11, tipo_suscripcion=Guia.Suscripcion.PREMIUM)
        subscription_mock = SimpleNamespace(
            stripe_subscription_id='sub_test_789',
            cancel_at_period_end=True,
            status='active',
            current_period_end=None,
            canceled_at=None,
            metadata={},
            save=MagicMock(),
        )
        with patch('billing.views._obtener_guia_para_usuario', return_value=guia_mock), \
             patch('billing.views._obtener_suscripcion_premium_cancelable', return_value=subscription_mock), \
             patch(
                 'billing.views.fetch_subscription_snapshot',
                 return_value={
                     'id': 'sub_test_789',
                     'status': 'active',
                     'cancel_at_period_end': True,
                     'current_period_end': None,
                     'cancel_at': 1714700000,
                     'canceled_at': None,
                 },
             ):
            response = schedule_downgrade_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(subscription_mock.current_period_end)
        subscription_mock.save.assert_called_once()
