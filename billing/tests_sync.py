from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from rutas.models import Guia

from billing.views import _epoch_to_datetime
from billing.views import _procesar_checkout_completed
from billing.views import _procesar_subscription_event


class BillingStripeSyncTest(SimpleTestCase):
    def _make_guia(self, tier):
        return SimpleNamespace(
            tipo_suscripcion=tier,
            save=MagicMock(),
        )

    def _make_subscription(self, guia):
        return SimpleNamespace(
            guia=guia,
            metadata={},
            stripe_customer_id='',
            stripe_subscription_id='',
            stripe_price_id='',
            cancel_at_period_end=False,
            canceled_at=None,
            current_period_start=None,
            current_period_end=None,
            provider='stripe',
            status='incomplete',
            save=MagicMock(),
        )

    def _mock_subscription_filter_returning(self, subscription):
        qs = MagicMock()
        qs.select_related.return_value.first.return_value = subscription
        return patch('billing.views.Subscription.objects.filter', return_value=qs)

    def test_epoch_to_datetime_devuelve_utc_aware(self):
        value = _epoch_to_datetime(1711900000)
        self.assertIsNotNone(value)
        self.assertTrue(timezone.is_aware(value))

    def test_customer_subscription_active_sube_a_premium(self):
        guia = self._make_guia(Guia.Suscripcion.FREEMIUM)
        subscription = self._make_subscription(guia)
        payload = {
            'id': 'sub_test_123',
            'status': 'active',
            'customer': 'cus_test_123',
            'items': {'data': [{'price': {'id': 'price_test_123'}}]},
            'current_period_start': 1711900000,
            'current_period_end': 1714500000,
            'cancel_at_period_end': False,
            'canceled_at': None,
            'metadata': {},
        }

        with self._mock_subscription_filter_returning(subscription):
            result = _procesar_subscription_event(payload)

        self.assertIs(result, subscription)
        self.assertEqual(guia.tipo_suscripcion, Guia.Suscripcion.PREMIUM)
        guia.save.assert_called_once_with(update_fields=['tipo_suscripcion'])
        subscription.save.assert_called_once()

    def test_customer_subscription_canceled_baja_a_freemium(self):
        guia = self._make_guia(Guia.Suscripcion.PREMIUM)
        subscription = self._make_subscription(guia)
        payload = {
            'id': 'sub_test_999',
            'status': 'canceled',
            'customer': 'cus_test_999',
            'items': {'data': [{'price': {'id': 'price_test_123'}}]},
            'current_period_start': 1711900000,
            'current_period_end': 1714500000,
            'cancel_at_period_end': True,
            'canceled_at': 1714500000,
            'metadata': {},
        }

        with self._mock_subscription_filter_returning(subscription):
            result = _procesar_subscription_event(payload)

        self.assertIs(result, subscription)
        self.assertEqual(guia.tipo_suscripcion, Guia.Suscripcion.FREEMIUM)
        guia.save.assert_called_once_with(update_fields=['tipo_suscripcion'])
        subscription.save.assert_called_once()

    def test_customer_subscription_usa_cancel_at_si_period_end_es_null(self):
        guia = self._make_guia(Guia.Suscripcion.PREMIUM)
        subscription = self._make_subscription(guia)
        payload = {
            'id': 'sub_test_cancel_at',
            'status': 'active',
            'customer': 'cus_test_cancel_at',
            'items': {'data': [{'price': {'id': 'price_test_123'}}]},
            'current_period_start': 1711900000,
            'current_period_end': None,
            'cancel_at': 1714600000,
            'cancel_at_period_end': True,
            'canceled_at': None,
            'metadata': {},
        }

        with self._mock_subscription_filter_returning(subscription):
            result = _procesar_subscription_event(payload)

        self.assertIs(result, subscription)
        self.assertIsNotNone(subscription.current_period_end)
        subscription.save.assert_called_once()

    @override_settings(STRIPE_ENABLED=False)
    def test_checkout_completed_paid_sube_a_premium(self):
        guia = self._make_guia(Guia.Suscripcion.FREEMIUM)
        subscription = self._make_subscription(guia)
        payload = {
            'id': 'cs_test_123',
            'mode': 'subscription',
            'subscription': 'sub_test_123',
            'customer': 'cus_test_123',
            'payment_status': 'paid',
            'status': 'complete',
            'metadata': {},
        }

        with self._mock_subscription_filter_returning(subscription):
            result = _procesar_checkout_completed(payload)

        self.assertIs(result, subscription)
        self.assertEqual(guia.tipo_suscripcion, Guia.Suscripcion.PREMIUM)
        guia.save.assert_called_once_with(update_fields=['tipo_suscripcion'])
        subscription.save.assert_called_once()

    @override_settings(STRIPE_ENABLED=True, STRIPE_SECRET_KEY='sk_test_123')
    def test_checkout_completed_refresca_period_end_desde_snapshot(self):
        guia = self._make_guia(Guia.Suscripcion.FREEMIUM)
        subscription = self._make_subscription(guia)
        payload = {
            'id': 'cs_test_456',
            'mode': 'subscription',
            'subscription': 'sub_test_456',
            'customer': 'cus_test_456',
            'payment_status': 'paid',
            'status': 'complete',
            'metadata': {},
        }

        with self._mock_subscription_filter_returning(subscription), \
             patch(
                 'billing.views.fetch_subscription_snapshot',
                 return_value={
                     'id': 'sub_test_456',
                     'status': 'active',
                     'cancel_at_period_end': False,
                     'current_period_end': 1777590764,
                     'cancel_at': None,
                     'canceled_at': None,
                 },
             ) as mock_snapshot:
            result = _procesar_checkout_completed(payload)

        self.assertIs(result, subscription)
        self.assertIsNotNone(subscription.current_period_end)
        self.assertFalse(subscription.cancel_at_period_end)
        mock_snapshot.assert_called_once()
