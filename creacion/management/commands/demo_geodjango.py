from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance

from creacion.models import GeoPuntoDemo


class Command(BaseCommand):
    help = "Demo GeoDjango (PointField): guarda puntos y consulta por distancia."

    def handle(self, *args, **options):
        # Limpia datos previos (para poder repetir la demo)
        GeoPuntoDemo.objects.all().delete()

        # OJO: Point(x, y) => Point(lon, lat)
        # Ejemplo: Sevilla centro aprox
        sevilla = Point(-5.9845, 37.3891, srid=4326)

        # Creamos 3 puntos cercanos/lejanos
        puntos = [
            ("Catedral de Sevilla", Point(-5.9926, 37.3861, srid=4326)),
            ("Plaza de España", Point(-5.9869, 37.3772, srid=4326)),
            ("Aeropuerto SVQ", Point(-5.8931, 37.4180, srid=4326)),
        ]

        for nombre, p in puntos:
            GeoPuntoDemo.objects.create(nombre=nombre, punto=p)

        self.stdout.write(self.style.SUCCESS("✅ Puntos creados en BD."))

        # Consulta 1: listar con distancia al centro
        self.stdout.write("\n📍 Distancias desde centro (Sevilla):")
        qs = GeoPuntoDemo.objects.annotate(dist=Distance("punto", sevilla)).order_by("dist")
        for obj in qs:
            # Distance devuelve en unidades del SRID; PostGIS suele convertir a metros con geography,
            # pero en 4326 puede salir en grados según config.
            # Para una demo clara, usamos la consulta de filtro por distancia (abajo).
            self.stdout.write(f" - {obj.nombre}: {obj.dist}")

        # Consulta 2 (la clave): puntos dentro de 5 km del centro
        cerca = GeoPuntoDemo.objects.filter(punto__distance_lte=(sevilla, D(km=5)))

        self.stdout.write(self.style.SUCCESS("\n✅ Puntos a <= 5km del centro:"))
        for obj in cerca:
            self.stdout.write(f" - {obj.nombre}")

        # Consulta 3: puntos dentro de 500 m (más estricta)
        muy_cerca = GeoPuntoDemo.objects.filter(punto__distance_lte=(sevilla, D(m=500)))

        self.stdout.write(self.style.SUCCESS("\n✅ Puntos a <= 500m del centro:"))
        if muy_cerca.exists():
            for obj in muy_cerca:
                self.stdout.write(f" - {obj.nombre}")
        else:
            self.stdout.write(" - (ninguno)")