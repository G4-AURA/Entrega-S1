"""
Script para crear una sesión de tour de prueba
Ejecutar con: python manage.py shell < crear_sesion_prueba.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from rutas.models import Ruta, Guia, AuthUser
from tours.models import SESION_TOUR

print("=" * 50)
print("Creando datos de prueba para Tours...")
print("=" * 50)

# 1. Crear o obtener usuario y guía
user, created = User.objects.get_or_create(
    username='guia_prueba',
    defaults={
        'email': 'guia@example.com',
        'first_name': 'Guía',
        'last_name': 'Prueba'
    }
)
if created:
    user.set_password('password123')
    user.save()
    print(f"✓ Usuario creado: {user.username}")
else:
    print(f"✓ Usuario existente: {user.username}")

# Crear AuthUser
auth_user, _ = AuthUser.objects.get_or_create(user=user)

# Crear Guía
guia, created = Guia.objects.get_or_create(
    user=auth_user,
    defaults={'tipo_suscripcion': Guia.Suscripcion.PREMIUM}
)
if created:
    print(f"✓ Guía creado: {guia}")
else:
    print(f"✓ Guía existente: {guia}")

# 2. Crear Ruta
ruta, created = Ruta.objects.get_or_create(
    titulo="Tour Centro Histórico de Sevilla",
    defaults={
        'descripcion': 'Un recorrido fascinante por el corazón de Sevilla',
        'duracion_horas': 2.5,
        'num_personas': 15,
        'nivel_exigencia': Ruta.Exigencia.BAJA,
        'mood': [Ruta.Mood.HISTORIA, Ruta.Mood.ARQUITECTURA_Y_DISEÑO],
        'es_generada_ia': False,
        'guia': guia
    }
)
if created:
    print(f"✓ Ruta creada: {ruta.titulo}")
else:
    print(f"✓ Ruta existente: {ruta.titulo}")

# 3. Crear SESION_TOUR
sesion, created = SESION_TOUR.objects.get_or_create(
    codigo_acceso='DEMO123',
    defaults={
        'estado': 'en_curso',
        'fecha_inicio': timezone.now(),
        'ruta': ruta
    }
)
if created:
    print(f"✓ Sesión creada: {sesion.codigo_acceso}")
else:
    print(f"✓ Sesión existente: {sesion.codigo_acceso}")

print("\n" + "=" * 50)
print("INFORMACIÓN PARA PROBAR:")
print("=" * 50)
print(f"Token de la sesión: {sesion.token}")
print(f"Código de acceso: {sesion.codigo_acceso}")
print(f"\nURL para unirse:")
print(f"http://127.0.0.1:8000/tours/join/{sesion.token}/")
print("\n" + "=" * 50)
