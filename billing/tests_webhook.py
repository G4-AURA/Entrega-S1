import contextlib
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from billing.services import StripeSignatureVerificationError, verify_stripe_signature
from billing.views import stripe_webhook_view

TEST_WEBHOOK_SECRET = 'whsec_test_signature'  # nosec B105 - fixture de tests, no credencial real


def _build_signature(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(timestamp or time.time())
    signed_payload = f'{ts}.'.encode('utf-8') + payload
    digest = hmac.new(
        secret.encode('utf-8'),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f't={ts},v1={digest}'


class StripeSignatureVerificationTest(SimpleTestCase):
    def test_valid_signature(self):
        payload = b'{"id":"evt_ok"}'
        secret = TEST_WEBHOOK_SECRET
        header = _build_signature(payload, secret)

        verify_stripe_signature(
            payload=payload,
            signature_header=header,
            webhook_secret=secret,
            tolerance_seconds=300,
        )

    def test_invalid_signature_raises(self):
        payload = b'{"id":"evt_bad"}'
        secret = TEST_WEBHOOK_SECRET
        bad_header = 't=123,v1=deadbeef'

        with self.assertRaises(StripeSignatureVerificationError):
            verify_stripe_signature(
                payload=payload,
                signature_header=bad_header,
                webhook_secret=secret,
                tolerance_seconds=300,
            )

    def test_old_timestamp_raises(self):
        payload = b'{"id":"evt_old"}'
        secret = TEST_WEBHOOK_SECRET
        old_ts = int(time.time()) - 1000
        header = _build_signature(payload, secret, timestamp=old_ts)

        with self.assertRaises(StripeSignatureVerificationError):
            verify_stripe_signature(
                payload=payload,
                signature_header=header,
                webhook_secret=secret,
                tolerance_seconds=300,
            )


class BillingWebhookViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.secret = TEST_WEBHOOK_SECRET

    def _payload_bytes(self, event_id='evt_1'):
        payload = {
            'id': event_id,
            'type': 'checkout.session.completed',
            'livemode': False,
            'api_version': '2026-01-01',
            'data': {
                'object': {
                    'id': 'cs_test_123',
                    'mode': 'subscription',
                    'subscription': 'sub_test_123',
                    'customer': 'cus_test_123',
                    'payment_status': 'paid',
                    'metadata': {'guia_id': '1'},
                }
            },
        }
        return json.dumps(payload).encode('utf-8')

    def _request(self, payload: bytes, signature: str):
        return self.factory.post(
            '/billing/webhook',
            data=payload,
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE=signature,
        )

    @override_settings(STRIPE_ENABLED=True, STRIPE_WEBHOOK_SECRET=TEST_WEBHOOK_SECRET)
    def test_rechaza_firma_invalida(self):
        payload = self._payload_bytes()
        request = self._request(payload, 't=1,v1=bad')

        response = stripe_webhook_view(request)

        self.assertEqual(response.status_code, 400)

    @override_settings(STRIPE_ENABLED=True, STRIPE_WEBHOOK_SECRET=TEST_WEBHOOK_SECRET)
    def test_procesa_evento_valido(self):
        payload = self._payload_bytes(event_id='evt_ok')
        signature = _build_signature(payload, self.secret)
        request = self._request(payload, signature)

        webhook_event_mock = SimpleNamespace(
            subscription=None,
            processed=False,
            processed_at=None,
            processing_error='',
            save=MagicMock(),
        )
        with patch(
            'billing.views.transaction.atomic',
            return_value=contextlib.nullcontext(),
        ), patch(
            'billing.views.WebhookEvent.objects.get_or_create',
            return_value=(webhook_event_mock, True),
        ), patch('billing.views._procesar_evento_stripe', return_value=None) as mock_process:
            response = stripe_webhook_view(request)

        body = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['status'], 'OK')
        self.assertEqual(body['event_id'], 'evt_ok')
        mock_process.assert_called_once()
        webhook_event_mock.save.assert_called_once()

    @override_settings(STRIPE_ENABLED=True, STRIPE_WEBHOOK_SECRET=TEST_WEBHOOK_SECRET)
    def test_evento_duplicado_es_idempotente(self):
        payload = self._payload_bytes(event_id='evt_dup')
        signature = _build_signature(payload, self.secret)
        request = self._request(payload, signature)

        existing_event = SimpleNamespace(save=MagicMock())
        with patch(
            'billing.views.transaction.atomic',
            return_value=contextlib.nullcontext(),
        ), patch(
            'billing.views.WebhookEvent.objects.get_or_create',
            return_value=(existing_event, False),
        ), patch('billing.views._procesar_evento_stripe') as mock_process:
            response = stripe_webhook_view(request)

        body = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body['duplicated'])
        mock_process.assert_not_called()

    @override_settings(STRIPE_ENABLED=True, STRIPE_WEBHOOK_SECRET=TEST_WEBHOOK_SECRET)
    def test_error_procesando_evento_devuelve_500(self):
        payload = self._payload_bytes(event_id='evt_fail')
        signature = _build_signature(payload, self.secret)
        request = self._request(payload, signature)

        webhook_event_mock = SimpleNamespace(
            subscription=None,
            processed=False,
            processed_at=None,
            processing_error='',
            save=MagicMock(),
        )
        with patch(
            'billing.views.transaction.atomic',
            return_value=contextlib.nullcontext(),
        ), patch(
            'billing.views.WebhookEvent.objects.get_or_create',
            return_value=(webhook_event_mock, True),
        ), patch(
            'billing.views._procesar_evento_stripe',
            side_effect=RuntimeError('fallo de procesamiento'),
        ):
            response = stripe_webhook_view(request)

        self.assertEqual(response.status_code, 500)
        self.assertGreaterEqual(webhook_event_mock.save.call_count, 1)
