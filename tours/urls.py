from django.urls import path
from . import views

app_name = 'tours'

urlpatterns = [
    # =======================================================================
    # Rutas para TURISTAS REGISTRADOS (requieren @login_required)
    # =======================================================================
    path('turista', views.pantalla_unirse_tour, name='pantalla_unirse'),
    path('sesiones/<int:sesion_id>/mapa/', views.mapa_turista, name='mapa_turista'),
	path('sesiones/unirse/', views.unirse_tour, name='unirse_tour'),	
    # =======================================================================
    # Rutas para GUÍAS (requieren @login_required)
    # =======================================================================
	path('sesiones/<int:sesion_id>/iniciar/', views.iniciar_tour, name='iniciar_tour'),
	path('ubicacion/', views.registrar_ubicacion, name='registrar_ubicacion'),
	
    # =======================================================================
    # Rutas /live/ para TURISTAS ANÓNIMOS (solo requieren token/cookie)
    # =======================================================================
	path('live/<uuid:token>/', views.join_tour, name='join_tour'),
	path('live/<uuid:token>/mapa/', views.mapa_turista_anonimo, name='mapa_turista_anonimo'),
	path('live/code/<str:codigo>/', views.join_tour_by_code, name='join_tour_by_code'),

	# Endpoints REST para chat
	path('sesiones/<int:sesion_id>/mensajes/enviar/', views.enviar_mensaje, name='enviar_mensaje'),
	path('sesiones/<int:sesion_id>/mensajes/', views.obtener_mensajes, name='obtener_mensajes'),

]
