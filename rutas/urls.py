from django.urls import path

from . import views

urlpatterns = [
    path("api/rutas/", views.rutas_catalogo, name="rutas-catalogo"),
]
