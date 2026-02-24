from django.contrib import admin
from .models import SESION_TOUR, TURISTA


from django.contrib import admin
# Importamos todos los modelos que queremos ver en el panel
from .models import TURISTA, SESION_TOUR, UBICACION_VIVO

@admin.register(TURISTA)
class TuristaAdmin(admin.ModelAdmin):
    list_display = ('user', 'alias')
    search_fields = ('alias', 'user__username')

@admin.register(SESION_TOUR)
class SesionTourAdmin(admin.ModelAdmin):
    list_display = (
        #'ruta',
        'codigo_acceso', 'estado', 'fecha_inicio')
    list_filter = ('estado', 'fecha_inicio')
    search_fields = ('codigo_acceso',
                     # ruta__nombre
    )
    filter_horizontal = ('turistas',)

@admin.register(UBICACION_VIVO)
class UbicacionVivoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'sesion_tour', 'timestamp', 'coordenadas')
    list_filter = ('sesion_tour', 'timestamp')
    search_fields = ('usuario__username',)