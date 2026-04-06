from django.db import models

from rutas.models import Guia


class Subscription(models.Model):
    class Provider(models.TextChoices):
        STRIPE = 'stripe', 'Stripe'

    class Status(models.TextChoices):
        INCOMPLETE = 'incomplete', 'Incomplete'
        INCOMPLETE_EXPIRED = 'incomplete_expired', 'Incomplete Expired'
        TRIALING = 'trialing', 'Trialing'
        ACTIVE = 'active', 'Active'
        PAST_DUE = 'past_due', 'Past Due'
        CANCELED = 'canceled', 'Canceled'
        UNPAID = 'unpaid', 'Unpaid'

    guia = models.ForeignKey(
        Guia,
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )
    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        default=Provider.STRIPE,
    )
    tier = models.CharField(
        max_length=20,
        choices=Guia.Suscripcion.choices,
        default=Guia.Suscripcion.FREEMIUM,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.INCOMPLETE,
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True
    )
    stripe_price_id = models.CharField(max_length=255, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_subscription'
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
        indexes = [
            models.Index(fields=['guia', 'status']),
            models.Index(fields=['tier']),
            models.Index(fields=['stripe_customer_id']),
        ]

    def __str__(self) -> str:
        stripe_id = self.stripe_subscription_id or 'sin-stripe-id'
        return f'{self.guia_id} | {self.tier} | {self.status} | {stripe_id}'


class WebhookEvent(models.Model):
    provider = models.CharField(
        max_length=20,
        choices=Subscription.Provider.choices,
        default=Subscription.Provider.STRIPE,
    )
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=255)
    livemode = models.BooleanField(default=False)
    api_version = models.CharField(max_length=64, blank=True)
    payload = models.JSONField()
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events',
    )
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_webhook_event'
        verbose_name = 'Webhook Event'
        verbose_name_plural = 'Webhook Events'
        indexes = [
            models.Index(fields=['event_type']),
            models.Index(fields=['processed']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        return f'{self.event_type} ({self.event_id})'
