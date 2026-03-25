"""tours/admin.py"""
from django.contrib import admin

from .models import MensajeChat, SesionTour, Turista, TuristaSesion, UbicacionVivo


@admin.register(Turista)
class TuristaAdmin(admin.ModelAdmin):
    list_display = ("id", "alias", "user")
    search_fields = ("alias", "user__username")


@admin.register(SesionTour)
class SesionTourAdmin(admin.ModelAdmin):
    list_display = ("codigo_acceso", "token", "estado", "fecha_inicio", "parada_actual")
    list_filter = ("estado", "fecha_inicio")
    search_fields = ("codigo_acceso",)
    readonly_fields = ("token",)


@admin.register(UbicacionVivo)
class UbicacionVivoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "sesion_tour", "timestamp", "coordenadas")
    list_filter = ("sesion_tour", "timestamp")
    search_fields = ("usuario__username",)


@admin.register(TuristaSesion)
class TuristaSesionAdmin(admin.ModelAdmin):
    list_display = ("turista", "sesion_tour", "fecha_union", "activo")
    list_filter = ("activo", "fecha_union", "sesion_tour")
    search_fields = ("turista__alias", "sesion_tour__codigo_acceso")
    readonly_fields = ("fecha_union",)


@admin.register(MensajeChat)
class MensajeChatAdmin(admin.ModelAdmin):
    list_display = ("nombre_remitente", "sesion_tour", "momento", "texto")
    list_filter = ("sesion_tour",)
    search_fields = ("nombre_remitente", "texto")