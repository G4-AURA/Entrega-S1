from django.contrib import admin
from .models import AuthUser, Guia, Ruta, Parada


@admin.register(AuthUser)
class AuthUserAdmin(admin.ModelAdmin):
	list_display = ("user",)
	search_fields = ("user__username",)


@admin.register(Guia)
class GuiaAdmin(admin.ModelAdmin):
	list_display = ("tipo_suscripcion", "user")
	search_fields = ("user__user__username",)


@admin.register(Ruta)
class RutaAdmin(admin.ModelAdmin):
	list_display = (
		"titulo",
		"descripcion",
		"duracion_horas",
		"num_personas",
		"nivel_exigencia",
			"mood_display",
		"es_generada_ia",
		"guia",
	)
	search_fields = ("titulo", "descripcion", "guia__user__user__username")
	def mood_display(self, obj):
		"""
		Return a human-readable representation of the mood list.
		"""
		if not obj.mood:
			return ""
		# Ensure all elements are strings before joining
		return ", ".join(str(m) for m in obj.mood)

	mood_display.short_description = "Mood"

@admin.register(Parada)
class ParadaAdmin(admin.ModelAdmin):
	list_display = ("orden", "nombre", "coordenadas", "ruta")
	search_fields = ("nombre", "ruta__titulo")