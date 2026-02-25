from django.urls import path
from . import views

urlpatterns = [
    path('generar/', views.generar_ruta_ia, name='generar_ruta_ia'),
]