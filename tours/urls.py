"""tours/urls.py"""
from django.urls import path

from . import views

app_name = "tours"

urlpatterns = [
    # ------------------------------------------------------------------
    # Turistas anónimos — flujo único de entrada
    # ------------------------------------------------------------------
    path("live/code/<str:codigo>/", views.join_tour_by_code, name="join_tour_by_code"),
    path("live/<uuid:token>/", views.join_tour, name="join_tour"),
    path("live/<uuid:token>/mapa/", views.mapa_turista_anonimo, name="mapa_turista_anonimo"),
    # ------------------------------------------------------------------
    # Guías (requieren @login_required)
    # ------------------------------------------------------------------
    path("sesiones/crear/", views.crear_sesion, name="crear_sesion"),
    path("sesiones/<int:sesion_id>/guia/", views.guia_sesion, name="guia_sesion"),
    path("sesiones/<int:sesion_id>/iniciar/", views.iniciar_tour, name="iniciar_tour"),
    path("sesiones/<int:sesion_id>/mapa/guia/", views.mapa_guia, name="mapa_guia"),
    path("sesiones/<int:sesion_id>/regenerar_codigo/", views.regenerar_codigo, name="regenerar_codigo"),
    path("sesiones/<int:sesion_id>/cerrar_acceso/", views.cerrar_acceso, name="cerrar_acceso"),
    path("sesiones/<int:sesion_id>/participantes/", views.participantes_sesion, name="participantes_sesion"),
    # ------------------------------------------------------------------
    # API REST — ubicación y chat
    # ------------------------------------------------------------------
    path("ubicacion/", views.registrar_ubicacion, name="registrar_ubicacion"),
    path("sesiones/<int:sesion_id>/ubicacion_guia/", views.obtener_ubicacion_guia, name="ubicacion_guia"),
    path("sesiones/<int:sesion_id>/mensajes/", views.obtener_mensajes, name="obtener_mensajes"),
    path("sesiones/<int:sesion_id>/mensajes/enviar/", views.enviar_mensaje, name="enviar_mensaje"),
]
