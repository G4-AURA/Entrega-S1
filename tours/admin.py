from django.contrib import admin
# Importamos todos los modelos que queremos ver en el panel
from .models import TURISTA, SESION_TOUR, UBICACION_VIVO, TURISTASESION

@admin.register(TURISTA)
class TuristaAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'alias')
    search_fields = ('alias', 'user__username')

@admin.register(SESION_TOUR)
class SesionTourAdmin(admin.ModelAdmin):
    list_display = (
        #'ruta',
        'codigo_acceso', 'token', 'estado', 'fecha_inicio', 'parada_actual')
    list_filter = ('estado', 'fecha_inicio')
    search_fields = ('codigo_acceso',
                     # ruta__nombre
    )
    readonly_fields = ('token',)

@admin.register(UBICACION_VIVO)
class UbicacionVivoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'sesion_tour', 'timestamp', 'coordenadas')
    list_filter = ('sesion_tour', 'timestamp')
    search_fields = ('usuario__username',)

@admin.register(TURISTASESION)
class TuristaSesionAdmin(admin.ModelAdmin):
    list_display = ('turista', 'sesion_tour', 'fecha_union', 'activo')
    list_filter = ('activo', 'fecha_union', 'sesion_tour')
    search_fields = ('turista__alias', 'sesion_tour__codigo_acceso')
    readonly_fields = ('fecha_union',)