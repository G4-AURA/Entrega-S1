from django.contrib import admin

from .models import FeatureAccessSetting, Subscription, TierUsageEvent, WebhookEvent


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'guia',
        'tier',
        'status',
        'provider',
        'stripe_customer_id',
        'stripe_subscription_id',
        'updated_at',
    )
    list_filter = ('tier', 'status', 'provider', 'cancel_at_period_end')
    search_fields = (
        'guia__user__user__username',
        'stripe_customer_id',
        'stripe_subscription_id',
        'stripe_price_id',
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'event_id',
        'event_type',
        'provider',
        'processed',
        'livemode',
        'created_at',
        'processed_at',
    )
    list_filter = ('provider', 'processed', 'livemode', 'event_type')
    search_fields = ('event_id', 'event_type', 'processing_error')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TierUsageEvent)
class TierUsageEventAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'guia',
        'ruta',
        'action',
        'created_at',
    )
    list_filter = ('action', 'created_at')
    search_fields = ('guia__user__user__username', 'ruta__titulo')
    readonly_fields = ('created_at',)


@admin.register(FeatureAccessSetting)
class FeatureAccessSettingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'key',
        'enabled_freemium',
        'enabled_premium',
        'updated_at',
    )
    list_filter = ('enabled_freemium', 'enabled_premium')
    search_fields = ('key',)
    readonly_fields = ('created_at', 'updated_at')
