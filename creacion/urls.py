from django.urls import path
from . import views

app_name = 'creacion'

urlpatterns = [
    path('', views.seleccion_tipo_ruta, name='seleccion_tipo_ruta'),
    path('manual/', views.creacion_manual, name='creacion_manual'),
    path('generar/', views.generar_ruta, name='generar_ruta'),
    path('api/generar/', views.generar_ruta_ia, name='generar_ruta_ia'),
    path('api/guardar-manual/', views.guardar_ruta_manual, name='guardar_ruta_manual'),
    path('api/rutas/<int:ruta_id>/paradas-ia/', views.generar_paradas_ia, name='generar_paradas_ia'),
]
