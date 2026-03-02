"""
Script para desactivar todos los turistas activos (útil para testing)
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tours.models import TURISTASESION

count = TURISTASESION.objects.filter(activo=True).update(activo=False)
print(f"✓ {count} turistas marcados como inactivos")
print("Ahora puedes volver a usar cualquier alias sin problemas")
