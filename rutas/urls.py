from django.urls import path

from . import views

urlpatterns = [
    path("catalogo/", views.catalogo_view, name="catalogo"),
    path("catalogo/<int:ruta_id>/", views.ruta_detalle_view, name="ruta-detalle"),
    path("catalogo/<int:ruta_id>/eliminar/", views.eliminar_ruta_view, name="ruta-eliminar"),
    path("api/rutas/", views.rutas_catalogo, name="rutas-catalogo"),
    path('', views.catalogo_view, name='catalogo'),
]
