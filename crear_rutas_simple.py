# -*- coding: utf-8 -*-
"""
Script simple para crear rutas (sin eliminar existentes)
Ejecutar con: python manage.py shell
Luego: exec(open('crear_rutas_simple.py', encoding='utf-8').read())
"""

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from rutas.models import AuthUser, Guia, Ruta, Parada

print("Creando/obteniendo usuario y guía...")

# Obtener o crear guía
user, _ = User.objects.get_or_create(
    username='guia_demo',
    defaults={
        'email': 'guia@example.com',
        'first_name': 'Ana',
        'last_name': 'García'
    }
)
if not user.has_usable_password():
    user.set_password('demo123')
    user.save()

auth_user, _ = AuthUser.objects.get_or_create(user=user)
guia, _ = Guia.objects.get_or_create(
    user=auth_user,
    defaults={'tipo_suscripcion': 'Premium'}
)
print(f"✓ Guía: {user.username}")

print("\nCreando rutas...")

# Ruta 1
if not Ruta.objects.filter(titulo='Tour Histórico por el Centro de Sevilla').exists():
    ruta1 = Ruta.objects.create(
        titulo='Tour Histórico por el Centro de Sevilla',
        descripcion='Descubre los monumentos más emblemáticos del centro histórico de Sevilla.',
        duracion_horas=3.5,
        num_personas=15,
        nivel_exigencia='Baja',
        mood=['Historia', 'Arquitectura y Diseño'],
        es_generada_ia=False,
        guia=guia
    )
    Parada.objects.create(orden=1, nombre='Catedral de Sevilla', coordenadas=Point(-5.9932, 37.3858), ruta=ruta1)
    Parada.objects.create(orden=2, nombre='Real Alcázar', coordenadas=Point(-5.9931, 37.3836), ruta=ruta1)
    Parada.objects.create(orden=3, nombre='Archivo de Indias', coordenadas=Point(-5.9927, 37.3845), ruta=ruta1)
    print(f"✓ {ruta1.titulo}")

# Ruta 2
if not Ruta.objects.filter(titulo='Ruta de Tapas y Gastronomía').exists():
    ruta2 = Ruta.objects.create(
        titulo='Ruta de Tapas y Gastronomía',
        descripcion='Un viaje culinario por los mejores bares de tapas de Sevilla.',
        duracion_horas=2.0,
        num_personas=8,
        nivel_exigencia='Baja',
        mood=['Gastronomía', 'Local'],
        es_generada_ia=False,
        guia=guia
    )
    Parada.objects.create(orden=1, nombre='Bar El Rinconcillo', coordenadas=Point(-5.9890, 37.3950), ruta=ruta2)
    Parada.objects.create(orden=2, nombre='Bodega Santa Cruz', coordenadas=Point(-5.9885, 37.3865), ruta=ruta2)
    print(f"✓ {ruta2.titulo}")

# Ruta 3
if not Ruta.objects.filter(titulo='Sevilla Verde: Parques y Jardines').exists():
    ruta3 = Ruta.objects.create(
        titulo='Sevilla Verde: Parques y Jardines',
        descripcion='Explora los espacios verdes más bellos de Sevilla.',
        duracion_horas=2.5,
        num_personas=20,
        nivel_exigencia='Media',
        mood=['Naturaleza', 'Ocio/Cultural'],
        es_generada_ia=False,
        guia=guia
    )
    Parada.objects.create(orden=1, nombre='Parque de María Luisa', coordenadas=Point(-5.9871, 37.3740), ruta=ruta3)
    Parada.objects.create(orden=2, nombre='Plaza de España', coordenadas=Point(-5.9863, 37.3771), ruta=ruta3)
    print(f"✓ {ruta3.titulo}")

print("\n" + "="*50)
print(f"✅ Total rutas: {Ruta.objects.count()}")
print(f"✅ Total paradas: {Parada.objects.count()}")
print("="*50)
