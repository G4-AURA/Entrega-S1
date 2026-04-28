"""
Seed de datos para entrega a clientes en despliegue limpio.

Uso:
  python manage.py seed_data_clientes
  python manage.py seed_data_clientes --clean
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction

from allowList.models import CategoriaOSM, POI
from billing.models import FeatureAccessSetting, Subscription, TierUsageEvent, WebhookEvent
from rutas.models import AuthUser, Curiosidad, Guia, Parada, Ruta, RutaAuditoria
from tours.models import MensajeChat, RecordatorioSesion, SESION_TOUR, TURISTA, TURISTASESION, UbicacionVivo


POIS_POR_CIUDAD = {
    "Sevilla": [
        ("Catedral de Sevilla", 37.3860, -5.9926, CategoriaOSM.IGLESIA),
        ("Real Alcazar", 37.3838, -5.9930, CategoriaOSM.MONUMENTO),
        ("Archivo de Indias", 37.3846, -5.9931, CategoriaOSM.MONUMENTO),
        ("Plaza de Espana", 37.3772, -5.9869, CategoriaOSM.PLAZA),
        ("Parque de Maria Luisa", 37.3750, -5.9870, CategoriaOSM.PARQUE),
        ("Setas de Sevilla", 37.3932, -5.9917, CategoriaOSM.MONUMENTO),
        ("Torre del Oro", 37.3824, -5.9963, CategoriaOSM.MONUMENTO),
        ("Plaza Nueva", 37.3891, -5.9923, CategoriaOSM.PLAZA),
        ("Palacio de las Duenas", 37.3964, -5.9895, CategoriaOSM.MONUMENTO),
        ("Museo de Bellas Artes de Sevilla", 37.3928, -6.0006, CategoriaOSM.MUSEO),
    ],
    "Malaga": [
        ("Alcazaba de Malaga", 36.7213, -4.4156, CategoriaOSM.MONUMENTO),
        ("Castillo de Gibralfaro", 36.7225, -4.4103, CategoriaOSM.CASTILLO),
        ("Catedral de Malaga", 36.7200, -4.4194, CategoriaOSM.IGLESIA),
        ("Teatro Romano de Malaga", 36.7214, -4.4173, CategoriaOSM.TEATRO),
        ("Museo Picasso Malaga", 36.7214, -4.4179, CategoriaOSM.MUSEO),
        ("Muelle Uno", 36.7186, -4.4132, CategoriaOSM.PLAZA),
        ("Mercado Central de Atarazanas", 36.7186, -4.4230, CategoriaOSM.MERCADO),
        ("Centre Pompidou Malaga", 36.7175, -4.4129, CategoriaOSM.MUSEO),
        ("Parque de Malaga", 36.7194, -4.4171, CategoriaOSM.PARQUE),
        ("Plaza de la Merced", 36.7240, -4.4176, CategoriaOSM.PLAZA),
    ],
    "Granada": [
        ("Alhambra", 37.1760, -3.5881, CategoriaOSM.MONUMENTO),
        ("Generalife", 37.1772, -3.5873, CategoriaOSM.PARQUE),
        ("Catedral de Granada", 37.1766, -3.5986, CategoriaOSM.IGLESIA),
        ("Capilla Real de Granada", 37.1764, -3.5991, CategoriaOSM.IGLESIA),
        ("Mirador de San Nicolas", 37.1815, -3.5924, CategoriaOSM.MIRADOR),
        ("Paseo de los Tristes", 37.1786, -3.5907, CategoriaOSM.PLAZA),
        ("Monasterio de San Jeronimo", 37.1811, -3.6030, CategoriaOSM.IGLESIA),
        ("Parque de las Ciencias", 37.1615, -3.6044, CategoriaOSM.MUSEO),
        ("Alcaiceria de Granada", 37.1758, -3.5993, CategoriaOSM.MERCADO),
        ("Plaza Bib-Rambla", 37.1756, -3.5990, CategoriaOSM.PLAZA),
    ],
    "Cordoba": [
        ("Mezquita-Catedral de Cordoba", 37.8789, -4.7794, CategoriaOSM.IGLESIA),
        ("Puente Romano de Cordoba", 37.8710, -4.7796, CategoriaOSM.MONUMENTO),
        ("Alcazar de los Reyes Cristianos", 37.8734, -4.7816, CategoriaOSM.CASTILLO),
        ("Torre de la Calahorra", 37.8696, -4.7764, CategoriaOSM.MONUMENTO),
        ("Juderia de Cordoba", 37.8784, -4.7818, CategoriaOSM.PLAZA),
        ("Palacio de Viana", 37.8855, -4.7764, CategoriaOSM.MONUMENTO),
        ("Plaza de la Corredera", 37.8831, -4.7732, CategoriaOSM.PLAZA),
        ("Templo Romano de Cordoba", 37.8840, -4.7780, CategoriaOSM.MONUMENTO),
        ("Medina Azahara", 37.8876, -4.8731, CategoriaOSM.RUINAS),
        ("Mercado Victoria", 37.8814, -4.7844, CategoriaOSM.MERCADO),
    ],
    "Cadiz": [
        ("Catedral de Cadiz", 36.5299, -6.2945, CategoriaOSM.IGLESIA),
        ("Torre Tavira", 36.5312, -6.2965, CategoriaOSM.MIRADOR),
        ("Castillo de Santa Catalina", 36.5348, -6.3032, CategoriaOSM.CASTILLO),
        ("Castillo de San Sebastian", 36.5315, -6.3128, CategoriaOSM.CASTILLO),
        ("Teatro Romano de Cadiz", 36.5295, -6.2940, CategoriaOSM.TEATRO),
        ("Playa de La Caleta", 36.5326, -6.3047, CategoriaOSM.PARQUE),
        ("Mercado Central de Abastos", 36.5321, -6.2970, CategoriaOSM.MERCADO),
        ("Parque Genoves", 36.5366, -6.3005, CategoriaOSM.PARQUE),
        ("Oratorio de San Felipe Neri", 36.5333, -6.3002, CategoriaOSM.IGLESIA),
        ("Plaza de San Juan de Dios", 36.5294, -6.2947, CategoriaOSM.PLAZA),
    ],
    "Huelva": [
        ("Muelle del Tinto", 37.2574, -6.9578, CategoriaOSM.MONUMENTO),
        ("Catedral de la Merced", 37.2615, -6.9475, CategoriaOSM.IGLESIA),
        ("Casa Colon", 37.2602, -6.9501, CategoriaOSM.MONUMENTO),
        ("Santuario de la Cinta", 37.2674, -6.9446, CategoriaOSM.IGLESIA),
        ("Parque Moret", 37.2712, -6.9538, CategoriaOSM.PARQUE),
        ("Barrio Reina Victoria", 37.2664, -6.9504, CategoriaOSM.MONUMENTO),
        ("Mercado del Carmen", 37.2588, -6.9494, CategoriaOSM.MERCADO),
        ("Plaza de las Monjas", 37.2604, -6.9499, CategoriaOSM.PLAZA),
        ("Museo de Huelva", 37.2617, -6.9471, CategoriaOSM.MUSEO),
        ("Muelle de las Carabelas", 37.2278, -6.9228, CategoriaOSM.MONUMENTO),
    ],
    "Jaen": [
        ("Catedral de Jaen", 37.7654, -3.7904, CategoriaOSM.IGLESIA),
        ("Castillo de Santa Catalina", 37.7798, -3.7892, CategoriaOSM.CASTILLO),
        ("Banos Arabes de Jaen", 37.7682, -3.7876, CategoriaOSM.MONUMENTO),
        ("Refugio Antiaereo de Santiago", 37.7662, -3.7897, CategoriaOSM.MONUMENTO),
        ("Museo de Jaen", 37.7749, -3.7885, CategoriaOSM.MUSEO),
        ("Parque del Bulevar", 37.7738, -3.7923, CategoriaOSM.PARQUE),
        ("Iglesia de San Ildefonso", 37.7668, -3.7890, CategoriaOSM.IGLESIA),
        ("Arco de San Lorenzo", 37.7680, -3.7898, CategoriaOSM.MONUMENTO),
        ("Plaza de Santa Maria", 37.7652, -3.7901, CategoriaOSM.PLAZA),
        ("Mercado de San Francisco", 37.7666, -3.7880, CategoriaOSM.MERCADO),
    ],
    "Almeria": [
        ("Alcazaba de Almeria", 36.8403, -2.4676, CategoriaOSM.CASTILLO),
        ("Catedral de la Encarnacion", 36.8378, -2.4660, CategoriaOSM.IGLESIA),
        ("Refugios de la Guerra Civil", 36.8400, -2.4637, CategoriaOSM.MONUMENTO),
        ("Cable Ingles", 36.8348, -2.4586, CategoriaOSM.MONUMENTO),
        ("Parque Nicolas Salmeron", 36.8365, -2.4686, CategoriaOSM.PARQUE),
        ("Mercado Central de Almeria", 36.8386, -2.4629, CategoriaOSM.MERCADO),
        ("Museo de Almeria", 36.8341, -2.4580, CategoriaOSM.MUSEO),
        ("Plaza Vieja", 36.8392, -2.4672, CategoriaOSM.PLAZA),
        ("Cerro de San Cristobal", 36.8444, -2.4672, CategoriaOSM.MIRADOR),
        ("Auditorio Maestro Padilla", 36.8264, -2.4477, CategoriaOSM.TEATRO),
    ],
}


class Command(BaseCommand):
    help = (
        "Seed para clientes: deja la BD sin usuarios de aplicacion y carga "
        "allowlist con ciudades grandes de Andalucia."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Limpia los datos funcionales antes de poblar la allowlist.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clean"]:
            self.stdout.write(self.style.WARNING("Limpiando datos existentes..."))
            self._clean_data()
            self.stdout.write(self.style.SUCCESS("✓ Limpieza completada"))

        created, updated = self._seed_allowlist()
        total = POI.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Seed completado. POIs creados: {created}, actualizados: {updated}, total allowlist: {total}"
            )
        )

    def _clean_data(self):
        """Limpieza para despliegue en entorno cliente."""
        # Datos de tours/rutas
        TURISTASESION.objects.all().delete()
        MensajeChat.objects.all().delete()
        RecordatorioSesion.objects.all().delete()
        UbicacionVivo.objects.all().delete()
        SESION_TOUR.objects.all().delete()
        TURISTA.objects.all().delete()
        Curiosidad.objects.all().delete()
        Parada.objects.all().delete()
        RutaAuditoria.objects.all().delete()
        Ruta.objects.all().delete()

        # Datos de billing
        TierUsageEvent.objects.all().delete()
        WebhookEvent.objects.all().delete()
        Subscription.objects.all().delete()
        FeatureAccessSetting.objects.all().delete()

        # Perfiles y usuarios
        Guia.objects.all().delete()
        AuthUser.objects.all().delete()
        User.objects.all().delete()

        # Allowlist previa
        POI.objects.all().delete()

    def _seed_allowlist(self) -> tuple[int, int]:
        created = 0
        updated = 0

        self.stdout.write("Poblando allowlist de ciudades andaluzas...")
        for ciudad, pois in POIS_POR_CIUDAD.items():
            self.stdout.write(f"  - {ciudad}: {len(pois)} POIs")
            for nombre, lat, lon, categoria in pois:
                poi, was_created = POI.objects.update_or_create(
                    nombre=nombre,
                    ciudad=ciudad,
                    defaults={
                        "categoria": categoria,
                        "coordenadas": Point(lon, lat, srid=4326),
                        "direccion": "",
                        "fuente": POI.Fuente.MANUAL,
                        "osm_id": None,
                        "osm_type": "",
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        return created, updated
