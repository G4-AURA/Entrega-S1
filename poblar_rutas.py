# -*- coding: utf-8 -*-
"""
Script para limpiar y recrear rutas con encoding correcto
Ejecutar con: python manage.py shell
Luego: exec(open('recrear_rutas.py', encoding='utf-8').read())
"""

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from rutas.models import AuthUser, Guia, Ruta, Parada

# Limpiar datos existentes
print("Limpiando datos existentes...")
Parada.objects.all().delete()
Ruta.objects.all().delete()
print("✓ Datos limpiados")

# Obtener o crear guía existente
try:
    user = User.objects.get(username='guia_demo')
    auth_user = AuthUser.objects.get(user=user)
    guia = Guia.objects.get(user=auth_user)
    print(f"✓ Usando guía existente: {guia.user.user.username}")
except:
    user = User.objects.create_user(username='guia_demo', email='guia@example.com', password='demo123')
    auth_user = AuthUser.objects.create(user=user)
    guia = Guia.objects.create(user=auth_user, tipo_suscripcion='Premium')
    print(f"✓ Guía creada: {guia.user.user.username}")

# Crear rutas con encoding correcto
print("\nCreando rutas...")

# Ruta 1
ruta1 = Ruta.objects.create(
    titulo='Tour Histórico por el Centro de Sevilla',
    descripcion='Descubre los monumentos más emblemáticos del centro histórico de Sevilla. Un recorrido fascinante por las calles que cuentan siglos de historia.',
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
ruta2 = Ruta.objects.create(
    titulo='Ruta de Tapas y Gastronomía',
    descripcion='Un viaje culinario por los mejores bares de tapas de Sevilla. Degusta los sabores auténticos de la cocina andaluza.',
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
ruta3 = Ruta.objects.create(
    titulo='Sevilla Verde: Parques y Jardines',
    descripcion='Explora los espacios verdes más bellos de Sevilla. Perfecta para desconectar y disfrutar de la naturaleza en la ciudad.',
    duracion_horas=2.5,
    num_personas=20,
    nivel_exigencia='Media',
    mood=['Naturaleza', 'Ocio/Cultural'],
    es_generada_ia=False,
    guia=guia
)
Parada.objects.create(orden=1, nombre='Parque de María Luisa', coordenadas=Point(-5.9871, 37.3740), ruta=ruta3)
Parada.objects.create(orden=2, nombre='Plaza de España', coordenadas=Point(-5.9863, 37.3771), ruta=ruta3)
Parada.objects.create(orden=3, nombre='Jardines de Murillo', coordenadas=Point(-5.9899, 37.3823), ruta=ruta3)
print(f"✓ {ruta3.titulo}")

# Ruta 4
ruta4 = Ruta.objects.create(
    titulo='Sevilla Completa en Un Día',
    descripcion='Una ruta intensiva que recorre los principales puntos de interés de Sevilla. Ideal para visitantes que disponen de poco tiempo.',
    duracion_horas=7.0,
    num_personas=12,
    nivel_exigencia='Alta',
    mood=['Historia', 'Arquitectura y Diseño', 'Ocio/Cultural'],
    es_generada_ia=True,
    guia=guia
)
Parada.objects.create(orden=1, nombre='Torre del Oro', coordenadas=Point(-5.9963, 37.3825), ruta=ruta4)
Parada.objects.create(orden=2, nombre='Plaza de Toros de la Maestranza', coordenadas=Point(-6.0001, 37.3864), ruta=ruta4)
Parada.objects.create(orden=3, nombre='Triana', coordenadas=Point(-6.0045, 37.3854), ruta=ruta4)
Parada.objects.create(orden=4, nombre='Metropol Parasol', coordenadas=Point(-5.9916, 37.3932), ruta=ruta4)
print(f"✓ {ruta4.titulo}")

print("\n" + "="*60)
print(f"✅ Proceso completado!")
print(f"Total de rutas: {Ruta.objects.count()}")
print(f"Total de paradas: {Parada.objects.count()}")
print("="*60)

# Verificar encoding
print("\nVerificación de encoding:")
for ruta in Ruta.objects.all():
    print(f"  - {ruta.titulo}")
