from django.urls import path

from . import views

urlpatterns = [
    path("catalogo/", views.catalogo_view, name="catalogo"),
    path("api/rutas/", views.rutas_catalogo, name="rutas-catalogo"),
]
