from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path(
        'create-checkout-session/',
        views.create_checkout_session_view,
        name='create_checkout_session',
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
