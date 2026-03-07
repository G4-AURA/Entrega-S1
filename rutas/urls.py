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
]
