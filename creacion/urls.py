from django.urls import path
from . import views

app_name = 'creacion'

urlpatterns = [
    path('', views.seleccion_tipo_ruta, name='seleccion_tipo_ruta'),
    path('manual/', views.creacion_manual, name='creacion_manual'),
]
