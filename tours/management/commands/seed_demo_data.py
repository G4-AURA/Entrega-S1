"""
Management command para crear datos de prueba en el despliegue.
Ejecutar con: python manage.py seed_demo_data
"""
import uuid
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta, Parada
from tours.models import TURISTA, SESION_TOUR, TURISTASESION


class Command(BaseCommand):
    help = 'Crea datos de prueba para el funcionamiento de la aplicación'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Limpia todos los datos existentes antes de crear nuevos'
        )

    def handle(self, *args, **options):
        if options['clean']:
            self.stdout.write(self.style.WARNING('⚠️  Eliminando datos existentes...'))
            self._clean_data()

        self.stdout.write(self.style.SUCCESS('✓ Iniciando creación de datos de prueba'))
        
        # Crear guías
        guias = self._create_guides()
        
        # Crear rutas
        rutas = self._create_routes(guias)
        
        # Crear paradas
        self._create_stops(rutas)
        
        # Crear turistas
        turistas = self._create_tourists()
        
        # Crear sesiones de tour
        self._create_sessions(rutas, turistas)
        
        self.stdout.write(self.style.SUCCESS('✓ Datos de prueba creados exitosamente'))

    def _clean_data(self):
        """Elimina todos los datos de la base de datos"""
        TURISTASESION.objects.all().delete()
        SESION_TOUR.objects.all().delete()
        TURISTA.objects.all().delete()
        Parada.objects.all().delete()
        Ruta.objects.all().delete()
        Guia.objects.all().delete()
        # No eliminar Users para no perder referencias
        self.stdout.write(self.style.SUCCESS('  ✓ Datos limpios'))

    def _create_guides(self):
        """Crea guías de prueba"""
        self.stdout.write('Creando guías...')
        
        guides_data = [
            {
                'username': 'guia_ana',
                'email': 'ana@example.com',
                'first_name': 'Ana',
                'last_name': 'García',
                'suscripcion': 'Premium'
            },
            {
                'username': 'guia_carlos',
                'email': 'carlos@example.com',
                'first_name': 'Carlos',
                'last_name': 'López',
                'suscripcion': 'Freemium'
            },
            {
                'username': 'guia_maria',
                'email': 'maria@example.com',
                'first_name': 'María',
                'last_name': 'Rodríguez',
                'suscripcion': 'Premium'
            }
        ]
        
        guias = []
        for data in guides_data:
            user, created = User.objects.get_or_create(
                username=data['username'],
                defaults={
                    'email': data['email'],
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                }
            )
            if created:
                user.set_password('demo123')
                user.save()
            
            auth_user, _ = AuthUser.objects.get_or_create(user=user)
            guia, _ = Guia.objects.get_or_create(
                user=auth_user,
                defaults={'tipo_suscripcion': data['suscripcion']}
            )
            guias.append(guia)
            status = '✓ Creado' if created else '∼ Existía'
            self.stdout.write(f"  {status}: {data['username']} ({data['suscripcion']})")
        
        return guias

    def _create_routes(self, guias):
        """Crea rutas de prueba"""
        self.stdout.write('Creando rutas...')
        
        routes_data = [
            {
                'titulo': 'Tour Histórico por el Centro de Sevilla',
                'descripcion': 'Descubre los monumentos más emblemáticos del centro histórico de Sevilla.',
                'duracion_horas': 3.5,
                'num_personas': 15,
                'nivel_exigencia': 'Baja',
                'mood': ['Historia', 'Arquitectura y Diseño'],
                'es_generada_ia': False,
                'guia_idx': 0
            },
            {
                'titulo': 'Ruta Gastronómica por Triana',
                'descripcion': 'Degusta los sabores más auténticos del barrio tradicional de Triana.',
                'duracion_horas': 2.5,
                'num_personas': 10,
                'nivel_exigencia': 'Baja',
                'mood': ['Gastronomía', 'Local'],
                'es_generada_ia': False,
                'guia_idx': 1
            },
            {
                'titulo': 'Misterios y Leyendas de Sevilla',
                'descripcion': 'Explora las historias oscuras y leyendas que rodean Sevilla.',
                'duracion_horas': 2.0,
                'num_personas': 12,
                'nivel_exigencia': 'Media',
                'mood': ['Misterio y Leyendas'],
                'es_generada_ia': False,
                'guia_idx': 2
            },
            {
                'titulo': 'Naturaleza y Parques de la Región',
                'descripcion': 'Un viaje por los espacios naturales protegidos de Andalucía.',
                'duracion_horas': 4.0,
                'num_personas': 20,
                'nivel_exigencia': 'Media',
                'mood': ['Naturaleza'],
                'es_generada_ia': False,
                'guia_idx': 0
            }
        ]
        
        rutas = []
        for data in routes_data:
            ruta, created = Ruta.objects.get_or_create(
                titulo=data['titulo'],
                defaults={
                    'descripcion': data['descripcion'],
                    'duracion_horas': data['duracion_horas'],
                    'num_personas': data['num_personas'],
                    'nivel_exigencia': data['nivel_exigencia'],
                    'mood': data['mood'],
                    'es_generada_ia': data['es_generada_ia'],
                    'guia': guias[data['guia_idx']]
                }
            )
            rutas.append(ruta)
            status = '✓ Creada' if created else '∼ Existía'
            self.stdout.write(f"  {status}: {data['titulo']}")
        
        return rutas

    def _create_stops(self, rutas):
        """Crea paradas para cada ruta"""
        self.stdout.write('Creando paradas...')
        
        stops_by_route = {
            0: [  # Tour Histórico
                {"nombre": "Plaza Nueva", "lat": 37.3891, "lng": -5.9923, "orden": 1},
                {"nombre": "Catedral de Sevilla", "lat": 37.3860, "lng": -5.9926, "orden": 2},
                {"nombre": "Barrio Santa Cruz", "lat": 37.3870, "lng": -5.9880, "orden": 3},
                {"nombre": "Real Alcázar", "lat": 37.3838, "lng": -5.9930, "orden": 4},
                {"nombre": "Torre del Oro", "lat": 37.3824, "lng": -5.9963, "orden": 5},
            ],
            1: [  # Ruta Gastronómica
                {"nombre": "Plaza de Castilla", "lat": 37.3752, "lng": -5.9982, "orden": 1},
                {"nombre": "Mercado de Triana", "lat": 37.3745, "lng": -6.0010, "orden": 2},
                {"nombre": "Taberna Tradicional", "lat": 37.3789, "lng": -6.0020, "orden": 3},
                {"nombre": "Cerámica de Triana", "lat": 37.3708, "lng": -6.0020, "orden": 4},
            ],
            2: [  # Misterios y Leyendas
                {"nombre": "Barrio de Santa Cruz", "lat": 37.3870, "lng": -5.9880, "orden": 1},
                {"nombre": "Callejones Oscuros", "lat": 37.3845, "lng": -5.9900, "orden": 2},
                {"nombre": "Iglesia de la Magdalena", "lat": 37.3882, "lng": -5.9853, "orden": 3},
            ],
            3: [  # Naturaleza
                {"nombre": "Parque Natural Doñana", "lat": 37.1761, "lng": -6.4400, "orden": 1},
                {"nombre": "Centro de Visitantes", "lat": 37.1950, "lng": -6.4500, "orden": 2},
                {"nombre": "Laguna de Santa Olalla", "lat": 37.1500, "lng": -6.4250, "orden": 3},
            ]
        }
        
        for idx, ruta in enumerate(rutas):
            # Eliminar paradas antiguas
            Parada.objects.filter(ruta=ruta).delete()
            
            for stop_data in stops_by_route.get(idx, []):
                Parada.objects.create(
                    nombre=stop_data['nombre'],
                    orden=stop_data['orden'],
                    coordenadas=Point(stop_data['lng'], stop_data['lat'], srid=4326),
                    ruta=ruta
                )
            self.stdout.write(f"  ✓ Paradas para: {ruta.titulo}")

    def _create_tourists(self):
        """Crea turistas de prueba"""
        self.stdout.write('Creando turistas...')
        
        tourists_data = [
            {'alias': 'turista_juan'},
            {'alias': 'turista_elena'},
            {'alias': 'turista_miguel'},
            {'alias': 'turista_sofia'},
            {'alias': 'turista_pedro'},
        ]
        
        turistas = []
        for data in tourists_data:
            turista, created = TURISTA.objects.get_or_create(
                alias=data['alias'],
                defaults={'user': None}
            )
            turistas.append(turista)
            status = '✓ Creado' if created else '∼ Existía'
            self.stdout.write(f"  {status}: {data['alias']}")
        
        return turistas

    def _create_sessions(self, rutas, turistas):
        """Crea sesiones de tour activas"""
        self.stdout.write('Creando sesiones de tour...')
        
        sessions_data = [
            {
                'ruta_idx': 0,
                'codigo_acceso': 'TOUR001',
                'estado': 'en_curso',
                'turistas_idx': [0, 1, 2],
                'parada_actual_orden': 2
            },
            {
                'ruta_idx': 1,
                'codigo_acceso': 'TOUR002',
                'estado': 'pendiente',
                'turistas_idx': [3, 4],
                'parada_actual_orden': 1
            },
            {
                'ruta_idx': 2,
                'codigo_acceso': 'TOUR003',
                'estado': 'pendiente',
                'turistas_idx': [0, 3],
                'parada_actual_orden': None
            },
        ]
        
        for data in sessions_data:
            # Evitar duplicados
            if SESION_TOUR.objects.filter(codigo_acceso=data['codigo_acceso']).exists():
                self.stdout.write(f"  ∼ Sesión existente: {data['codigo_acceso']}")
                continue
            
            ruta = rutas[data['ruta_idx']]
            ahora = timezone.now()
            
            sesion = SESION_TOUR.objects.create(
                codigo_acceso=data['codigo_acceso'],
                estado=data['estado'],
                fecha_inicio=ahora,
                ruta=ruta,
                token=uuid.uuid4()
            )
            
            # Asignar parada actual
            if data['parada_actual_orden'] is not None:
                parada_actual = Parada.objects.filter(
                    ruta=ruta,
                    orden=data['parada_actual_orden']
                ).first()
                if parada_actual:
                    sesion.parada_actual = parada_actual
                    sesion.save()
            
            # Agregar turistas
            for turista_idx in data['turistas_idx']:
                TURISTASESION.objects.get_or_create(
                    turista=turistas[turista_idx],
                    sesion_tour=sesion
                )
            
            self.stdout.write(
                f"  ✓ Sesión {data['codigo_acceso']} "
                f"({len(data['turistas_idx'])} turistas, estado: {data['estado']})"
            )
