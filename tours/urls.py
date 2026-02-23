from django.urls import path
from . import views

app_name = 'tours'

urlpatterns = [
	path('sesiones/<int:sesion_id>/iniciar/', views.iniciar_tour, name='iniciar_tour'),
	path('sesiones/unirse/', views.unirse_tour, name='unirse_tour'),
]
