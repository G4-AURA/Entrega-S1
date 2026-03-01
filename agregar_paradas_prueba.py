"""
Script para agregar paradas de prueba a la ruta
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.gis.geos import Point
from rutas.models import Ruta, Parada
from tours.models import SESION_TOUR

print("=" * 50)
print("Agregando paradas de prueba...")
print("=" * 50)

# Obtener la ruta de prueba
ruta = Ruta.objects.first()
if not ruta:
    print("❌ No hay rutas en la base de datos")
    exit()

print(f"✓ Ruta encontrada: {ruta.titulo}")

# Eliminar paradas existentes para empezar limpio
Parada.objects.filter(ruta=ruta).delete()

# Crear paradas de ejemplo en Sevilla
paradas_data = [
    {"nombre": "Plaza Nueva", "lat": 37.3891, "lng": -5.9923, "orden": 1},
    {"nombre": "Catedral de Sevilla", "lat": 37.3860, "lng": -5.9926, "orden": 2},
    {"nombre": "Barrio Santa Cruz", "lat": 37.3870, "lng": -5.9880, "orden": 3},
    {"nombre": "Alcázar", "lat": 37.3838, "lng": -5.9930, "orden": 4},
    {"nombre": "Torre del Oro", "lat": 37.3824, "lng": -5.9963, "orden": 5},
]

paradas = []
for data in paradas_data:
    parada = Parada.objects.create(
        nombre=data["nombre"],
        orden=data["orden"],
        coordenadas=Point(data["lng"], data["lat"], srid=4326),
        ruta=ruta
    )
    paradas.append(parada)
    print(f"  ✓ Parada {data['orden']}: {data['nombre']}")

# Configurar la sesión para que la parada actual sea la segunda
sesion = SESION_TOUR.objects.first()
if sesion:
    sesion.parada_actual = paradas[1]  # Catedral de Sevilla
    sesion.save()
    print(f"\n✓ Parada actual establecida: {paradas[1].nombre}")
else:
    print("\n⚠ No hay sesión para configurar parada actual")

print("\n" + "=" * 50)
print("¡Listo! Ahora recarga la página del tour")
print("=" * 50)
