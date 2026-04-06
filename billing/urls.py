from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path(
        'create-checkout-session/',
        views.create_checkout_session_view,
        name='create_checkout_session',
    ),
]
