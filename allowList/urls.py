"""allowlist/urls.py"""
from django.urls import path
from . import views

app_name = 'allowlist'

urlpatterns = [
    # ── Vistas HTML ───────────────────────────────────────────────────────────
    path('',            views.panel_allowlist,    name='panel'),
    path('buscar-osm/', views.vista_buscar_osm,   name='buscar_osm'),
    path('nuevo/',      views.vista_crear_manual,  name='crear_manual'),
    # ── API JSON ──────────────────────────────────────────────────────────────
    path('api/buscar-osm/',            views.api_buscar_osm,   name='api_buscar_osm'),
    path('api/importar-osm/',          views.api_importar_osm, name='api_importar_osm'),
    path('api/crear-manual/',          views.api_crear_manual, name='api_crear_manual'),
    path('api/listar/',                views.api_listar_pois,  name='api_listar'),
    path('api/eliminar/<int:poi_id>/', views.api_eliminar_poi, name='api_eliminar'),
]