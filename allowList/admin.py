from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from .models import CityBoundary, POI

@admin.register(POI)
class POIAdmin(GISModelAdmin):
    list_display   = ('nombre', 'categoria', 'ciudad', 'fuente', 'google_rank_position')
    list_filter    = ('fuente', 'categoria', 'ciudad')
    search_fields  = ('nombre', 'ciudad', 'direccion', 'google_place_id')
    readonly_fields = ('osm_id', 'osm_type', 'fuente')
    ordering       = ('nombre',)
    fieldsets = (
        ('Identificación', {
            'fields': ('nombre', 'categoria'),
        }),
        ('Ubicación', {
            'fields': ('coordenadas', 'ciudad', 'direccion'),
        }),
        ('Origen', {
            'fields': ('fuente', 'osm_id', 'osm_type'),
        }),
        ('Google SearchText', {
            'fields': ('google_place_id', 'google_rank_position', 'google_search_query', 'google_last_seen_at'),
        }),
    )


@admin.register(CityBoundary)
class CityBoundaryAdmin(GISModelAdmin):
    list_display = ('city_name', 'active', 'updated_at')
    list_filter = ('active',)
    search_fields = ('city_name',)
    ordering = ('city_name',)
