"""
Seed de despliegue v3.

Uso:
  python manage.py seed_demo_data_despliegue3
  python manage.py seed_demo_data_despliegue3 --clean
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from allowList.models import CategoriaOSM, POI
from billing.models import Subscription, TierUsageEvent
from rutas.models import AuthUser, Curiosidad, Guia, Parada, Ruta
from tours.models import SESION_TOUR, TURISTA, TURISTASESION


SEED_SOURCE = "seed_demo_data_despliegue3"
DEMO_PASSWORD = "demo123"  # nosec B105 - contraseña demo para dataset de seed no productivo


GUIDES_DATA = [
    {
        "username": "guia_ana",
        "email": "ana@example.com",
        "first_name": "Ana",
        "last_name": "García",
        "subscription": Guia.Suscripcion.PREMIUM,
    },
    {
        "username": "guia_carlos",
        "email": "carlos@example.com",
        "first_name": "Carlos",
        "last_name": "López",
        "subscription": Guia.Suscripcion.FREEMIUM,
    },
    {
        "username": "guia_maria",
        "email": "maria@example.com",
        "first_name": "María",
        "last_name": "Rodríguez",
        "subscription": Guia.Suscripcion.PREMIUM,
    },
]


ROUTES_DATA = [
    {
        "title": "S3 · Sevilla Monumental Esencial",
        "guide_username": "guia_ana",
        "description": "Recorrido premium por patrimonio monumental y espacios historicos clave.",
        "duration_hours": 3.2,
        "num_people": 24,
        "effort": Ruta.Exigencia.BAJA,
        "mood": [Ruta.Mood.HISTORIA, Ruta.Mood.ARQUITECTURA_Y_DISEÑO],
        "is_ai": False,
        "stops": [
            {
                "order": 1,
                "name": "Archivo de Indias",
                "lat": 37.3846,
                "lng": -5.9931,
                "curiosity_title": "Memoria del comercio global",
                "curiosity_text": "Desde aqui se gestiono buena parte del trafico con America durante siglos.",
                "curiosity_type": Curiosidad.TipoCuriosidad.HISTORIA,
            },
            {
                "order": 2,
                "name": "Catedral de Sevilla",
                "lat": 37.3860,
                "lng": -5.9926,
                "curiosity_title": "Escala gotica extrema",
                "curiosity_text": "Su gran volumen fue una declaracion de poder urbano y religioso.",
                "curiosity_type": Curiosidad.TipoCuriosidad.ARQUITECTURA,
            },
            {
                "order": 3,
                "name": "Real Alcazar",
                "lat": 37.3838,
                "lng": -5.9930,
                "curiosity_title": "Palacio vivo",
                "curiosity_text": "Sigue siendo residencia oficial en visitas institucionales.",
                "curiosity_type": Curiosidad.TipoCuriosidad.EVENTO,
            },
            {
                "order": 4,
                "name": "Plaza del Triunfo",
                "lat": 37.3851,
                "lng": -5.9936,
                "curiosity_title": "Tres iconos en un punto",
                "curiosity_text": "Concentra catedral, archivo y alcazar en una sola postal urbana.",
                "curiosity_type": Curiosidad.TipoCuriosidad.DATO_CURIOSO,
            },
            {
                "order": 5,
                "name": "Torre del Oro",
                "lat": 37.3824,
                "lng": -5.9963,
                "curiosity_title": "Atalaya del Guadalquivir",
                "curiosity_text": "Controlaba el paso fluvial y la defensa del puerto historico.",
                "curiosity_type": Curiosidad.TipoCuriosidad.HISTORIA,
            },
            {
                "order": 6,
                "name": "Plaza de Espana",
                "lat": 37.3772,
                "lng": -5.9869,
                "curiosity_title": "Escenario de gran formato",
                "curiosity_text": "Su diseno semicircular se planteo como vitrina de arquitectura regional.",
                "curiosity_type": Curiosidad.TipoCuriosidad.ARQUITECTURA,
            },
        ],
    },
    {
        "title": "S3 · Miradores y Atardecer en Sevilla",
        "guide_username": "guia_ana",
        "description": "Ruta premium enfocada en vistas, fotografia y narrativa urbana.",
        "duration_hours": 2.4,
        "num_people": 20,
        "effort": Ruta.Exigencia.BAJA,
        "mood": [Ruta.Mood.LOCAL, Ruta.Mood.OCIO_CULTURAL],
        "is_ai": True,
        "stops": [
            {
                "order": 1,
                "name": "Setas de Sevilla",
                "lat": 37.3932,
                "lng": -5.9917,
                "curiosity_title": "Mirador contemporaneo",
                "curiosity_text": "Integra plaza, mercado y pasarela panoramica en una sola pieza.",
                "curiosity_type": Curiosidad.TipoCuriosidad.ARQUITECTURA,
            },
            {
                "order": 2,
                "name": "Puente de Triana",
                "lat": 37.3854,
                "lng": -6.0005,
                "curiosity_title": "Eje de barrio y rio",
                "curiosity_text": "Conecta el centro historico con una identidad local muy marcada.",
                "curiosity_type": Curiosidad.TipoCuriosidad.HISTORIA,
            },
            {
                "order": 3,
                "name": "Muelle de la Sal",
                "lat": 37.3866,
                "lng": -5.9960,
                "curiosity_title": "Postal fluvial",
                "curiosity_text": "Zona ideal para explicar transformaciones recientes de la ribera.",
                "curiosity_type": Curiosidad.TipoCuriosidad.DATO_CURIOSO,
            },
            {
                "order": 4,
                "name": "Paseo de Colon",
                "lat": 37.3855,
                "lng": -5.9991,
                "curiosity_title": "Borde escenico",
                "curiosity_text": "Concentra equipamientos culturales y puntos de encuentro turistico.",
                "curiosity_type": Curiosidad.TipoCuriosidad.EVENTO,
            },
            {
                "order": 5,
                "name": "Parque de Maria Luisa",
                "lat": 37.3750,
                "lng": -5.9870,
                "curiosity_title": "Verde historico",
                "curiosity_text": "Espacio clave para descanso en rutas largas y visitas de grupos.",
                "curiosity_type": Curiosidad.TipoCuriosidad.DATO_CURIOSO,
            },
        ],
    },
    {
        "title": "S3 · Jardines Historicos de Sevilla",
        "guide_username": "guia_carlos",
        "description": "Ruta freemium manual orientada a historia y naturaleza urbana.",
        "duration_hours": 2.0,
        "num_people": 12,
        "effort": Ruta.Exigencia.BAJA,
        "mood": [Ruta.Mood.HISTORIA, Ruta.Mood.NATURALEZA],
        "is_ai": False,
        "stops": [
            {
                "order": 1,
                "name": "Jardines de Murillo",
                "lat": 37.3828,
                "lng": -5.9884,
                "curiosity_title": "Puerta verde al casco historico",
                "curiosity_text": "Sirven de transicion entre muralla historica y zonas monumentales.",
                "curiosity_type": Curiosidad.TipoCuriosidad.HISTORIA,
            },
            {
                "order": 2,
                "name": "Parque de Maria Luisa",
                "lat": 37.3750,
                "lng": -5.9870,
                "curiosity_title": "Jardin de exposicion",
                "curiosity_text": "Su trazado se adapto para acoger grandes eventos del siglo XX.",
                "curiosity_type": Curiosidad.TipoCuriosidad.EVENTO,
            },
            {
                "order": 3,
                "name": "Glorieta de Becerra",
                "lat": 37.3742,
                "lng": -5.9863,
                "curiosity_title": "Micro-espacio narrativo",
                "curiosity_text": "Ideal para pausas cortas con explicacion de personajes locales.",
                "curiosity_type": Curiosidad.TipoCuriosidad.PERSONAJE,
            },
            {
                "order": 4,
                "name": "Plaza de Espana",
                "lat": 37.3772,
                "lng": -5.9869,
                "curiosity_title": "Remate monumental",
                "curiosity_text": "Cierra la ruta con un icono facilmente reconocible para el grupo.",
                "curiosity_type": Curiosidad.TipoCuriosidad.ARQUITECTURA,
            },
        ],
    },
    {
        "title": "S3 · Ruta IA Arquitectura Andaluza",
        "guide_username": "guia_carlos",
        "description": "Ruta freemium IA centrada en arquitectura y narrativa historica.",
        "duration_hours": 1.8,
        "num_people": 10,
        "effort": Ruta.Exigencia.MEDIA,
        "mood": [Ruta.Mood.ARQUITECTURA_Y_DISEÑO],
        "is_ai": True,
        "stops": [
            {
                "order": 1,
                "name": "Casa de Pilatos",
                "lat": 37.3891,
                "lng": -5.9867,
                "curiosity_title": "Patio y simbolo",
                "curiosity_text": "Ejemplo didactico de mezcla de lenguajes arquitectonicos.",
                "curiosity_type": Curiosidad.TipoCuriosidad.ARQUITECTURA,
            },
            {
                "order": 2,
                "name": "Palacio de las Duenas",
                "lat": 37.3936,
                "lng": -5.9888,
                "curiosity_title": "Residencia de linaje",
                "curiosity_text": "Combina herencia nobiliaria y adaptaciones de distintas epocas.",
                "curiosity_type": Curiosidad.TipoCuriosidad.HISTORIA,
            },
            {
                "order": 3,
                "name": "Iglesia del Salvador",
                "lat": 37.3899,
                "lng": -5.9924,
                "curiosity_title": "Centro de vida local",
                "curiosity_text": "Concentra gran afluencia y permite explicar usos contemporaneos.",
                "curiosity_type": Curiosidad.TipoCuriosidad.DATO_CURIOSO,
            },
            {
                "order": 4,
                "name": "Plaza Nueva",
                "lat": 37.3891,
                "lng": -5.9923,
                "curiosity_title": "Nodo urbano",
                "curiosity_text": "Conecta flujos peatonales y actividades institucionales.",
                "curiosity_type": Curiosidad.TipoCuriosidad.EVENTO,
            },
            {
                "order": 5,
                "name": "Ayuntamiento de Sevilla",
                "lat": 37.3889,
                "lng": -5.9955,
                "curiosity_title": "Fachada de poder",
                "curiosity_text": "Ejemplo de evolucion formal en arquitectura civil sevillana.",
                "curiosity_type": Curiosidad.TipoCuriosidad.ARQUITECTURA,
            },
        ],
    },
    {
        "title": "S3 · Sevilla de Leyendas y Relatos",
        "guide_username": "guia_maria",
        "description": "Ruta premium con enfoque narrativo en mitos urbanos y memoria oral.",
        "duration_hours": 2.7,
        "num_people": 18,
        "effort": Ruta.Exigencia.MEDIA,
        "mood": [Ruta.Mood.MISTERIO_Y_LEYENDAS, Ruta.Mood.HISTORIA],
        "is_ai": False,
        "stops": [
            {
                "order": 1,
                "name": "Calle Susona",
                "lat": 37.3878,
                "lng": -5.9897,
                "curiosity_title": "Relato popular persistente",
                "curiosity_text": "Una de las historias mas repetidas en visitas nocturnas.",
                "curiosity_type": Curiosidad.TipoCuriosidad.HISTORIA,
            },
            {
                "order": 2,
                "name": "Plaza de Dona Elvira",
                "lat": 37.3868,
                "lng": -5.9890,
                "curiosity_title": "Escena romantica",
                "curiosity_text": "Punto ideal para transiciones narrativas de personaje a personaje.",
                "curiosity_type": Curiosidad.TipoCuriosidad.PERSONAJE,
            },
            {
                "order": 3,
                "name": "Hospital de los Venerables",
                "lat": 37.3876,
                "lng": -5.9892,
                "curiosity_title": "Memoria de gremio",
                "curiosity_text": "Permite explicar estructuras sociales y legado artistico.",
                "curiosity_type": Curiosidad.TipoCuriosidad.HISTORIA,
            },
            {
                "order": 4,
                "name": "Plaza de la Alianza",
                "lat": 37.3858,
                "lng": -5.9902,
                "curiosity_title": "Rincon escenico",
                "curiosity_text": "Su escala ayuda a dinamicas de grupo y preguntas abiertas.",
                "curiosity_type": Curiosidad.TipoCuriosidad.DATO_CURIOSO,
            },
            {
                "order": 5,
                "name": "Calle Agua",
                "lat": 37.3861,
                "lng": -5.9884,
                "curiosity_title": "Toponimia con historia",
                "curiosity_text": "El nombre conecta infraestructuras antiguas y relato urbano.",
                "curiosity_type": Curiosidad.TipoCuriosidad.EVENTO,
            },
        ],
    },
    {
        "title": "S3 · Ruta IA Cine y Series",
        "guide_username": "guia_maria",
        "description": "Ruta premium IA para grupos interesados en localizaciones audiovisuales.",
        "duration_hours": 2.1,
        "num_people": 22,
        "effort": Ruta.Exigencia.BAJA,
        "mood": [Ruta.Mood.CINE_Y_SERIES, Ruta.Mood.ARQUITECTURA_Y_DISEÑO],
        "is_ai": True,
        "stops": [
            {
                "order": 1,
                "name": "Real Alcazar",
                "lat": 37.3838,
                "lng": -5.9930,
                "curiosity_title": "Set internacional",
                "curiosity_text": "Frecuente en producciones de alto alcance por su valor visual.",
                "curiosity_type": Curiosidad.TipoCuriosidad.EVENTO,
            },
            {
                "order": 2,
                "name": "Plaza de Espana",
                "lat": 37.3772,
                "lng": -5.9869,
                "curiosity_title": "Escala cinematografica",
                "curiosity_text": "La geometria del espacio facilita planos amplios y secuencias corales.",
                "curiosity_type": Curiosidad.TipoCuriosidad.ARQUITECTURA,
            },
            {
                "order": 3,
                "name": "Archivo de Indias",
                "lat": 37.3846,
                "lng": -5.9931,
                "curiosity_title": "Fondo de epoca",
                "curiosity_text": "Su entorno aporta continuidad visual para narrativa historica.",
                "curiosity_type": Curiosidad.TipoCuriosidad.HISTORIA,
            },
            {
                "order": 4,
                "name": "Setas de Sevilla",
                "lat": 37.3932,
                "lng": -5.9917,
                "curiosity_title": "Contraste contemporaneo",
                "curiosity_text": "Sirve de contrapunto moderno dentro de una misma ruta tematizada.",
                "curiosity_type": Curiosidad.TipoCuriosidad.DATO_CURIOSO,
            },
            {
                "order": 5,
                "name": "Puente de Triana",
                "lat": 37.3854,
                "lng": -6.0005,
                "curiosity_title": "Cierre de recorrido",
                "curiosity_text": "Aporta final visual potente para despedida y fotos de grupo.",
                "curiosity_type": Curiosidad.TipoCuriosidad.EVENTO,
            },
        ],
    },
]


TOURISTS_DATA = [
    "s3_turista_alba",
    "s3_turista_bruno",
    "s3_turista_clara",
    "s3_turista_diego",
    "s3_turista_elsa",
    "s3_turista_felix",
    "s3_turista_gala",
    "s3_turista_hugo",
    "s3_turista_irene",
    "s3_turista_joel",
    "s3_turista_karla",
    "s3_turista_luca",
    "s3_turista_marta",
    "s3_turista_nora",
    "s3_turista_oliver",
    "s3_turista_paula",
    "s3_turista_quim",
    "s3_turista_raquel",
    "s3_turista_sergio",
    "s3_turista_tania",
]


SESSIONS_DATA = [
    {
        "code": "S3A001",
        "route_title": "S3 · Sevilla Monumental Esencial",
        "state": SESION_TOUR.EN_CURSO,
        "current_stop_order": 3,
        "tourist_aliases": [
            "s3_turista_alba",
            "s3_turista_bruno",
            "s3_turista_clara",
            "s3_turista_diego",
            "s3_turista_elsa",
            "s3_turista_felix",
            "s3_turista_gala",
            "s3_turista_hugo",
            "s3_turista_irene",
            "s3_turista_joel",
            "s3_turista_karla",
            "s3_turista_luca",
        ],
        "starts_delta_minutes": -35,
    },
    {
        "code": "S3A002",
        "route_title": "S3 · Miradores y Atardecer en Sevilla",
        "state": SESION_TOUR.PENDIENTE,
        "current_stop_order": 1,
        "tourist_aliases": [
            "s3_turista_marta",
            "s3_turista_nora",
            "s3_turista_oliver",
            "s3_turista_paula",
            "s3_turista_quim",
            "s3_turista_raquel",
        ],
        "starts_delta_minutes": 20,
    },
    {
        "code": "S3C001",
        "route_title": "S3 · Jardines Historicos de Sevilla",
        "state": SESION_TOUR.PENDIENTE,
        "current_stop_order": 2,
        "tourist_aliases": [
            "s3_turista_alba",
            "s3_turista_bruno",
            "s3_turista_clara",
            "s3_turista_diego",
            "s3_turista_elsa",
            "s3_turista_felix",
            "s3_turista_gala",
            "s3_turista_hugo",
        ],
        "starts_delta_minutes": 55,
    },
    {
        "code": "S3M001",
        "route_title": "S3 · Sevilla de Leyendas y Relatos",
        "state": SESION_TOUR.EN_CURSO,
        "current_stop_order": 2,
        "tourist_aliases": [
            "s3_turista_irene",
            "s3_turista_joel",
            "s3_turista_karla",
            "s3_turista_luca",
            "s3_turista_marta",
            "s3_turista_nora",
            "s3_turista_oliver",
            "s3_turista_paula",
            "s3_turista_quim",
            "s3_turista_raquel",
            "s3_turista_sergio",
            "s3_turista_tania",
        ],
        "starts_delta_minutes": -15,
    },
]


POIS_DATA = [
    {"name": "Catedral de Sevilla", "lat": 37.3860, "lng": -5.9926, "cat": CategoriaOSM.IGLESIA},
    {"name": "Real Alcazar", "lat": 37.3838, "lng": -5.9930, "cat": CategoriaOSM.CASTILLO},
    {"name": "Torre del Oro", "lat": 37.3824, "lng": -5.9963, "cat": CategoriaOSM.MONUMENTO},
    {"name": "Archivo de Indias", "lat": 37.3846, "lng": -5.9931, "cat": CategoriaOSM.MUSEO},
    {"name": "Plaza de Espana", "lat": 37.3772, "lng": -5.9869, "cat": CategoriaOSM.PLAZA},
    {"name": "Parque de Maria Luisa", "lat": 37.3750, "lng": -5.9870, "cat": CategoriaOSM.PARQUE},
    {"name": "Setas de Sevilla", "lat": 37.3932, "lng": -5.9917, "cat": CategoriaOSM.MIRADOR},
    {"name": "Puente de Triana", "lat": 37.3854, "lng": -6.0005, "cat": CategoriaOSM.MONUMENTO},
    {"name": "Mercado de Triana", "lat": 37.3855, "lng": -6.0010, "cat": CategoriaOSM.MERCADO},
    {"name": "Casa de Pilatos", "lat": 37.3891, "lng": -5.9867, "cat": CategoriaOSM.MONUMENTO},
    {"name": "Palacio de las Duenas", "lat": 37.3936, "lng": -5.9888, "cat": CategoriaOSM.MONUMENTO},
    {"name": "Jardines de Murillo", "lat": 37.3828, "lng": -5.9884, "cat": CategoriaOSM.PARQUE},
    {"name": "Iglesia del Salvador", "lat": 37.3899, "lng": -5.9924, "cat": CategoriaOSM.IGLESIA},
    {"name": "Hospital de los Venerables", "lat": 37.3876, "lng": -5.9892, "cat": CategoriaOSM.MONUMENTO},
]


class Command(BaseCommand):
    help = (
        "Seed de despliegue v3 con guias fijos, tiers coherentes y datos "
        "idempotentes para plan, rutas, sesiones y allowlist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Elimina el dataset S3 previo antes de recrearlo.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            if options["clean"]:
                self.stdout.write(self.style.WARNING("⚠ Limpiando dataset S3 previo..."))
                self._clean_seed_data()

            self.stdout.write(self.style.SUCCESS("✓ Iniciando seed_demo_data_despliegue3"))

            guides_by_username = self._create_or_update_guides()
            self._sync_subscriptions(guides_by_username)
            routes_by_title = self._create_or_update_routes(guides_by_username)
            tourists_by_alias = self._create_or_update_tourists()
            self._create_or_update_sessions(routes_by_title, tourists_by_alias)
            self._seed_usage_events(guides_by_username, routes_by_title)
            self._create_or_update_pois()

            self.stdout.write(self.style.SUCCESS("✓ Seed despliegue3 completado correctamente"))
        except Exception as exc:
            raise CommandError(f"Error en seed_demo_data_despliegue3: {exc}") from exc

    def _clean_seed_data(self):
        session_codes = [item["code"] for item in SESSIONS_DATA]
        route_titles = [item["title"] for item in ROUTES_DATA]
        tourist_aliases = list(TOURISTS_DATA)
        poi_names = [item["name"] for item in POIS_DATA]
        guide_usernames = [item["username"] for item in GUIDES_DATA]

        sessions_qs = SESION_TOUR.objects.filter(codigo_acceso__in=session_codes)
        TURISTASESION.objects.filter(sesion_tour__in=sessions_qs).delete()
        sessions_qs.delete()

        TURISTA.objects.filter(alias__in=tourist_aliases).delete()
        Ruta.objects.filter(titulo__in=route_titles).delete()

        subscriptions_seed = Subscription.objects.filter(
            metadata__seed_source=SEED_SOURCE
        )
        subscriptions_seed.delete()

        TierUsageEvent.objects.filter(
            guia__user__user__username__in=guide_usernames
        ).delete()

        POI.objects.filter(
            nombre__in=poi_names, ciudad="Sevilla", fuente=POI.Fuente.MANUAL
        ).delete()

        self.stdout.write(self.style.SUCCESS("  ✓ Dataset S3 eliminado"))

    def _create_or_update_guides(self) -> dict[str, Guia]:
        self.stdout.write("Creando/actualizando guias...")
        guides_by_username: dict[str, Guia] = {}

        for data in GUIDES_DATA:
            user, _created_user = User.objects.get_or_create(username=data["username"])
            user.email = data["email"]
            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.is_active = True
            user.set_password(DEMO_PASSWORD)
            user.save()

            auth_user, _ = AuthUser.objects.get_or_create(user=user)
            guia, _ = Guia.objects.get_or_create(user=auth_user)
            guia.tipo_suscripcion = data["subscription"]
            guia.save(update_fields=["tipo_suscripcion"])

            guides_by_username[data["username"]] = guia
            self.stdout.write(
                f"  ✓ {data['username']} ({data['subscription']}) password={DEMO_PASSWORD}"
            )

        return guides_by_username

    def _sync_subscriptions(self, guides_by_username: dict[str, Guia]):
        self.stdout.write("Sincronizando suscripciones billing...")
        now = timezone.now()

        premium_usernames = {
            item["username"]
            for item in GUIDES_DATA
            if item["subscription"] == Guia.Suscripcion.PREMIUM
        }

        for username, guia in guides_by_username.items():
            if username in premium_usernames:
                stripe_subscription_id = f"sub_{SEED_SOURCE}_{username}"
                subscription, _ = Subscription.objects.get_or_create(
                    stripe_subscription_id=stripe_subscription_id,
                    defaults={"guia": guia},
                )
                subscription.guia = guia
                subscription.provider = Subscription.Provider.STRIPE
                subscription.tier = Guia.Suscripcion.PREMIUM
                subscription.status = Subscription.Status.ACTIVE
                subscription.stripe_customer_id = f"cus_{SEED_SOURCE}_{username}"
                subscription.stripe_price_id = "price_seed_demo_premium"
                subscription.current_period_start = now - timedelta(days=3)
                subscription.current_period_end = now + timedelta(days=27)
                subscription.cancel_at_period_end = False
                subscription.canceled_at = None
                existing_metadata = (
                    subscription.metadata if isinstance(subscription.metadata, dict) else {}
                )
                subscription.metadata = {
                    **existing_metadata,
                    "seed_source": SEED_SOURCE,
                    "seed_command": "seed_demo_data_despliegue3",
                }
                subscription.save()
                self.stdout.write(f"  ✓ Premium activo para {username}")
            else:
                Subscription.objects.filter(
                    guia=guia,
                    status__in=[
                        Subscription.Status.ACTIVE,
                        Subscription.Status.TRIALING,
                        Subscription.Status.PAST_DUE,
                    ],
                ).update(
                    status=Subscription.Status.CANCELED,
                    cancel_at_period_end=False,
                    canceled_at=now,
                    current_period_end=now,
                )
                self.stdout.write(f"  ✓ Freemium coherente para {username}")

    def _create_or_update_routes(self, guides_by_username: dict[str, Guia]) -> dict[str, Ruta]:
        self.stdout.write("Creando/actualizando rutas y paradas...")
        routes_by_title: dict[str, Ruta] = {}

        for data in ROUTES_DATA:
            guia = guides_by_username[data["guide_username"]]
            route, _ = Ruta.objects.update_or_create(
                titulo=data["title"],
                defaults={
                    "descripcion": data["description"],
                    "duracion_horas": data["duration_hours"],
                    "num_personas": data["num_people"],
                    "nivel_exigencia": data["effort"],
                    "mood": data["mood"],
                    "es_generada_ia": data["is_ai"],
                    "guia": guia,
                },
            )

            Parada.objects.filter(ruta=route).delete()
            for stop_data in data["stops"]:
                stop = Parada.objects.create(
                    ruta=route,
                    orden=stop_data["order"],
                    nombre=stop_data["name"],
                    descripcion=(
                        f"Parada {stop_data['order']} de la ruta {data['title']} "
                        f"(seed {SEED_SOURCE})."
                    ),
                    coordenadas=Point(stop_data["lng"], stop_data["lat"], srid=4326),
                )
                Curiosidad.objects.update_or_create(
                    parada=stop,
                    defaults={
                        "ciudad": "Sevilla",
                        "titulo": stop_data["curiosity_title"],
                        "texto": stop_data["curiosity_text"],
                        "tipo": stop_data["curiosity_type"],
                    },
                )

            routes_by_title[data["title"]] = route
            self.stdout.write(
                f"  ✓ {data['title']} ({len(data['stops'])} paradas, IA={data['is_ai']})"
            )

        return routes_by_title

    def _create_or_update_tourists(self) -> dict[str, TURISTA]:
        self.stdout.write("Creando/actualizando turistas anonimos...")
        tourists_by_alias: dict[str, TURISTA] = {}

        for alias in TOURISTS_DATA:
            tourist, _ = TURISTA.objects.get_or_create(alias=alias, defaults={"user": None})
            if tourist.user_id is not None:
                tourist.user = None
                tourist.save(update_fields=["user"])
            tourists_by_alias[alias] = tourist

        self.stdout.write(f"  ✓ {len(tourists_by_alias)} turistas listos")
        return tourists_by_alias

    def _create_or_update_sessions(
        self,
        routes_by_title: dict[str, Ruta],
        tourists_by_alias: dict[str, TURISTA],
    ):
        self.stdout.write("Creando/actualizando sesiones...")
        now = timezone.now()

        for data in SESSIONS_DATA:
            route = routes_by_title[data["route_title"]]
            start_dt = now + timedelta(minutes=int(data["starts_delta_minutes"]))
            session, created = SESION_TOUR.objects.update_or_create(
                codigo_acceso=data["code"],
                defaults={
                    "estado": data["state"],
                    "fecha_inicio": start_dt,
                    "ruta": route,
                },
            )

            current_stop = Parada.objects.filter(
                ruta=route, orden=data["current_stop_order"]
            ).first()
            if session.parada_actual_id != getattr(current_stop, "id", None):
                session.parada_actual = current_stop
                session.save(update_fields=["parada_actual"])

            selected_tourists = [tourists_by_alias[alias] for alias in data["tourist_aliases"]]
            TURISTASESION.objects.filter(sesion_tour=session).exclude(
                turista__in=selected_tourists
            ).update(activo=False)

            for tourist in selected_tourists:
                link, _ = TURISTASESION.objects.get_or_create(
                    sesion_tour=session,
                    turista=tourist,
                )
                if not link.activo:
                    link.activo = True
                    link.save(update_fields=["activo"])

            action = "creada" if created else "actualizada"
            self.stdout.write(
                f"  ✓ Sesion {data['code']} {action} "
                f"({len(selected_tourists)} turistas, estado={data['state']})"
            )

    def _seed_usage_events(
        self,
        guides_by_username: dict[str, Guia],
        routes_by_title: dict[str, Ruta],
    ):
        self.stdout.write("Sembrando metricas de uso por plan...")

        TierUsageEvent.objects.filter(guia__in=guides_by_username.values()).delete()

        usage_specs = [
            {
                "guide_username": "guia_ana",
                "action": TierUsageEvent.Action.IA_ROUTE_GENERATION,
                "count": 4,  # Premium <= 10
                "route_title": None,
            },
            {
                "guide_username": "guia_ana",
                "action": TierUsageEvent.Action.IA_STOP_REPLACEMENT,
                "count": 10,  # Premium <= 30
                "route_title": "S3 · Miradores y Atardecer en Sevilla",
            },
            {
                "guide_username": "guia_carlos",
                "action": TierUsageEvent.Action.IA_ROUTE_GENERATION,
                "count": 2,  # Freemium <= 3
                "route_title": None,
            },
            {
                "guide_username": "guia_carlos",
                "action": TierUsageEvent.Action.IA_STOP_REPLACEMENT,
                "count": 3,  # Freemium <= 9 y <=3 por ruta
                "route_title": "S3 · Ruta IA Arquitectura Andaluza",
            },
            {
                "guide_username": "guia_maria",
                "action": TierUsageEvent.Action.IA_ROUTE_GENERATION,
                "count": 6,  # Premium <= 10
                "route_title": None,
            },
            {
                "guide_username": "guia_maria",
                "action": TierUsageEvent.Action.IA_STOP_REPLACEMENT,
                "count": 8,  # Premium <= 30
                "route_title": "S3 · Ruta IA Cine y Series",
            },
        ]

        for spec in usage_specs:
            guia = guides_by_username[spec["guide_username"]]
            route = routes_by_title.get(spec["route_title"]) if spec["route_title"] else None
            for _ in range(spec["count"]):
                TierUsageEvent.objects.create(
                    guia=guia,
                    ruta=route,
                    action=spec["action"],
                )

        self.stdout.write("  ✓ Eventos de uso creados (coherentes con limites)")

    def _create_or_update_pois(self):
        self.stdout.write("Creando/actualizando allowlist POIs...")
        for data in POIS_DATA:
            POI.objects.update_or_create(
                nombre=data["name"],
                ciudad="Sevilla",
                fuente=POI.Fuente.MANUAL,
                defaults={
                    "categoria": data["cat"],
                    "coordenadas": Point(data["lng"], data["lat"], srid=4326),
                    "direccion": "",
                    "osm_id": None,
                    "osm_type": "",
                },
            )
        self.stdout.write(f"  ✓ {len(POIS_DATA)} POIs manuales listos")
