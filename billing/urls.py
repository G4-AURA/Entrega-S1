from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path(
        'admin/feature-access/',
        views.feature_access_panel_view,
        name='feature_access_panel',
    ),
    path(
        'admin/feature-access/update/',
        views.update_feature_access_view,
        name='feature_access_update',
    ),
    path(
        'create-checkout-session/',
        views.create_checkout_session_view,
        name='create_checkout_session',
    ),
    path(
        'schedule-downgrade/',
        views.schedule_downgrade_view,
        name='schedule_downgrade',
    ),
    path(
        'webhook',
        views.stripe_webhook_view,
        name='stripe_webhook',
    ),
    path(
        'webhook/',
        views.stripe_webhook_view,
        name='stripe_webhook_slash',
    ),
]
