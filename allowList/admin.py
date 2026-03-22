from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from .models import POI

@admin.register(POI)
class POIAdmin(GISModelAdmin):
    list_display   = ('nombre', 'categoria', 'ciudad', 'fuente')
    list_filter    = ('fuente', 'categoria')
    search_fields  = ('nombre', 'ciudad', 'direccion')
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
    )