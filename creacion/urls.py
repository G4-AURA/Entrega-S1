from django.urls import path
from . import views

app_name = 'creacion'

urlpatterns = [
    path('', views.seleccion_tipo_ruta, name='seleccion_tipo_ruta'),
    path('manual/', views.creacion_manual, name='creacion_manual'),
    path('generar/', views.generar_ruta, name='generar_ruta'),
    path('api/generar/', views.generar_ruta_ia, name='generar_ruta_ia'),
    path('api/generar/confirmar/', views.confirmar_ruta_ia, name='confirmar_ruta_ia'),
    path('api/generar/adicionales/', views.generar_paradas_adicionales_ia, name='generar_paradas_adicionales_ia'),
    path('api/guardar-manual/', views.guardar_ruta_manual, name='guardar_ruta_manual'),
    path('api/rutas/<int:ruta_id>/paradas-ia/', views.generar_paradas_ia, name='generar_paradas_ia'),
    path(
        'api/sesiones-generacion/<str:session_id>/',
        views.obtener_sesion_generacion_ia,
        name='obtener_sesion_generacion_ia',
    ),
    path(
        'api/sesiones-generacion/<str:session_id>/checkpoint/',
        views.actualizar_checkpoint_sesion_generacion,
        name='actualizar_checkpoint_sesion_generacion',
    ),
]
