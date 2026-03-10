# rutas/urls.py

from django.urls import path

from . import views

urlpatterns = [
    # ------------------------------------------------------------------
    # Gestión de rutas: listar (catálogo), visualizar y eliminar
    # ------------------------------------------------------------------
    path("catalogo/", views.catalogo_view, name="catalogo"),
    path("catalogo/<int:ruta_id>/", views.ruta_detalle_view, name="ruta-detalle"),
    path("catalogo/<int:ruta_id>/eliminar/", views.eliminar_ruta_view, name="ruta-eliminar"),
    # ------------------------------------------------------------------
    # API que se comunica con el backend para obtener las rutas
    # ------------------------------------------------------------------
    path("api/rutas/", views.rutas_catalogo, name="rutas-catalogo"),
    # ------------------------------------------------------------------
    # S2.1-32: Endpoint AJAX para recalcular geometría GraphHopper
    # sin recargar la página completa del detalle
    # ------------------------------------------------------------------
    path(
        "api/rutas/<int:ruta_id>/recalcular/",
        views.recalcular_ruta_api,
        name="ruta-recalcular",
    ),
]