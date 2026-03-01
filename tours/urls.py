from django.urls import path
from . import views

app_name = 'tours'

urlpatterns = [
    path('turista', views.pantalla_unirse_tour, name='pantalla_unirse'),
    path('sesiones/<int:sesion_id>/mapa/', views.mapa_turista, name='mapa_turista'),
	path('sesiones/<int:sesion_id>/iniciar/', views.iniciar_tour, name='iniciar_tour'),
	path('sesiones/unirse/', views.unirse_tour, name='unirse_tour'),
	# Endpoints REST para chat
	path('sesiones/<int:sesion_id>/mensajes/enviar/', views.enviar_mensaje, name='enviar_mensaje'),
	path('sesiones/<int:sesion_id>/mensajes/', views.obtener_mensajes, name='obtener_mensajes'),
]
