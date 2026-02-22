from django.contrib import admin
from .models import TURISTA


@admin.register(TURISTA)
class TuristaAdmin(admin.ModelAdmin):
    list_display = ('user', 'alias')
    search_fields = ('alias', 'user__username')
    readonly_fields = ('user',)
