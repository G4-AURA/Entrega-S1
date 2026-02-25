"""
Script para poblar la base de datos con rutas de ejemplo
Ejecutar con: python manage.py shell < poblar_rutas.py
O copiar y pegar en: python manage.py shell
"""

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from rutas.models import AuthUser, Guia, Ruta, Parada

# Crear usuario de Django si no existe
user, created = User.objects.get_or_create(
    username='guia_demo',
    defaults={
        'email': 'guia@example.com',
        'first_name': 'Ana',
        'last_name': 'García'
    }
)
if created:
    user.set_password('demo123')
    user.save()
    print(f"✓ Usuario creado: {user.username}")
else:
    print(f"✓ Usuario existente: {user.username}")

# Crear AuthUser
auth_user, created = AuthUser.objects.get_or_create(
    user=user
)
print(f"✓ AuthUser {'creado' if created else 'existente'}")

# Crear Guia
guia, created = Guia.objects.get_or_create(
    user=auth_user,
    defaults={'tipo_suscripcion': Guia.Suscripcion.PREMIUM}
)
print(f"✓ Guía {'creada' if created else 'existente'}: {guia.tipo_suscripcion}")

# Crear Ruta 1: Tour Histórico de Sevilla
ruta1, created = Ruta.objects.get_or_create(
    titulo='Tour Histórico por el Centro de Sevilla',
    defaults={
        'descripcion': 'Descubre los monumentos más emblemáticos del centro histórico de Sevilla. Un recorrido fascinante por las calles que cuentan siglos de historia.',
        'duracion_horas': 3.5,
        'num_personas': 15,
        'nivel_exigencia': 'Baja',
        'mood': ['Historia', 'Arquitectura y Diseño'],
        'es_generada_ia': False,
        'guia': guia
    }
)
if created:
    print(f"✓ Ruta 1 creada: {ruta1.titulo}")
    
    # Paradas de la Ruta 1
    Parada.objects.create(
        orden=1,
        nombre='Catedral de Sevilla',
        coordenadas=Point(-5.9932, 37.3858),  # lon, lat
        ruta=ruta1
    )
    Parada.objects.create(
        orden=2,
        nombre='Real Alcázar',
        coordenadas=Point(-5.9931, 37.3836),
        ruta=ruta1
    )
    Parada.objects.create(
        orden=3,
        nombre='Archivo de Indias',
        coordenadas=Point(-5.9927, 37.3845),
        ruta=ruta1
    )
    print("  ✓ 3 paradas añadidas")

# Crear Ruta 2: Gastronomía Sevillana
ruta2, created = Ruta.objects.get_or_create(
    titulo='Ruta de Tapas y Gastronomía',
    defaults={
        'descripcion': 'Un viaje culinario por los mejores bares de tapas de Sevilla. Degusta los sabores auténticos de la cocina andaluza.',
        'duracion_horas': 2.0,
        'num_personas': 8,
        'nivel_exigencia': 'Baja',
        'mood': ['Gastronomía', 'Local'],
        'es_generada_ia': False,
        'guia': guia
    }
)
if created:
    print(f"✓ Ruta 2 creada: {ruta2.titulo}")
    
    Parada.objects.create(
        orden=1,
        nombre='Bar El Rinconcillo',
        coordenadas=Point(-5.9890, 37.3950),
        ruta=ruta2
    )
    Parada.objects.create(
        orden=2,
        nombre='Bodega Santa Cruz',
        coordenadas=Point(-5.9885, 37.3865),
        ruta=ruta2
    )
    print("  ✓ 2 paradas añadidas")

# Crear Ruta 3: Parques y Naturaleza
ruta3, created = Ruta.objects.get_or_create(
    titulo='Sevilla Verde: Parques y Jardines',
    defaults={
        'descripcion': 'Explora los espacios verdes más bellos de Sevilla. Perfecta para desconectar y disfrutar de la naturaleza en la ciudad.',
        'duracion_horas': 2.5,
        'num_personas': 20,
        'nivel_exigencia': 'Media',
        'mood': ['Naturaleza', 'Ocio/Cultural'],
        'es_generada_ia': False,
        'guia': guia
    }
)
if created:
    print(f"✓ Ruta 3 creada: {ruta3.titulo}")
    
    Parada.objects.create(
        orden=1,
        nombre='Parque de María Luisa',
        coordenadas=Point(-5.9871, 37.3740),
        ruta=ruta3
    )
    Parada.objects.create(
        orden=2,
        nombre='Plaza de España',
        coordenadas=Point(-5.9863, 37.3771),
        ruta=ruta3
    )
    Parada.objects.create(
        orden=3,
        nombre='Jardines de Murillo',
        coordenadas=Point(-5.9899, 37.3823),
        ruta=ruta3
    )
    print("  ✓ 3 paradas añadidas")

# Crear Ruta 4: Ruta Intensa
ruta4, created = Ruta.objects.get_or_create(
    titulo='Sevilla Completa en Un Día',
    defaults={
        'descripcion': 'Una ruta intensiva que recorre los principales puntos de interés de Sevilla. Ideal para visitantes que disponen de poco tiempo.',
        'duracion_horas': 7.0,
        'num_personas': 12,
        'nivel_exigencia': 'Alta',
        'mood': ['Historia', 'Arquitectura y Diseño', 'Ocio/Cultural'],
        'es_generada_ia': True,
        'guia': guia
    }
)
if created:
    print(f"✓ Ruta 4 creada: {ruta4.titulo}")
    
    Parada.objects.create(
        orden=1,
        nombre='Torre del Oro',
        coordenadas=Point(-5.9963, 37.3825),
        ruta=ruta4
    )
    Parada.objects.create(
        orden=2,
        nombre='Plaza de Toros de la Maestranza',
        coordenadas=Point(-6.0001, 37.3864),
        ruta=ruta4
    )
    Parada.objects.create(
        orden=3,
        nombre='Triana',
        coordenadas=Point(-6.0045, 37.3854),
        ruta=ruta4
    )
    Parada.objects.create(
        orden=4,
        nombre='Metropol Parasol',
        coordenadas=Point(-5.9916, 37.3932),
        ruta=ruta4
    )
    print("  ✓ 4 paradas añadidas")

print("\n" + "="*50)
print(f"✅ Proceso completado!")
print(f"Total de rutas en la BD: {Ruta.objects.count()}")
print(f"Total de paradas en la BD: {Parada.objects.count()}")
print("="*50)
