from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from rutas.models import AuthUser, Guia

from .models import Subscription, WebhookEvent


class BillingModelsTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='billing-user', password='pass123')
        auth_user = AuthUser.objects.create(user=user)
        self.guia = Guia.objects.create(user=auth_user)

    def test_subscription_default_tier_freemium(self):
        subscription = Subscription.objects.create(
            guia=self.guia,
            status=Subscription.Status.ACTIVE,
        )
        self.assertEqual(subscription.tier, Guia.Suscripcion.FREEMIUM)

    def test_webhook_event_id_es_unico(self):
        WebhookEvent.objects.create(
            event_id='evt_123',
            event_type='customer.subscription.updated',
            payload={'id': 'evt_123', 'type': 'customer.subscription.updated'},
        )

        with self.assertRaises(IntegrityError):
            WebhookEvent.objects.create(
                event_id='evt_123',
                event_type='customer.subscription.updated',
                payload={'id': 'evt_123', 'type': 'customer.subscription.updated'},
            )
