from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from rutas.models import Parada, Ruta

from . import services
from .models import SesionTour


@receiver(post_save, sender=SesionTour)
def invalidate_session_snapshot_on_save(sender, instance, **kwargs):
    services.invalidate_route_snapshot(instance.id)


@receiver(post_delete, sender=SesionTour)
def invalidate_session_snapshot_on_delete(sender, instance, **kwargs):
    services.invalidate_route_snapshot(instance.id)


@receiver(post_save, sender=Ruta)
def invalidate_route_snapshots_on_route_save(sender, instance, **kwargs):
    services.invalidate_route_snapshots_for_route(instance.id)


@receiver(post_delete, sender=Ruta)
def invalidate_route_snapshots_on_route_delete(sender, instance, **kwargs):
    services.invalidate_route_snapshots_for_route(instance.id)


@receiver(post_save, sender=Parada)
def invalidate_route_snapshots_on_stop_save(sender, instance, **kwargs):
    services.invalidate_route_snapshots_for_route(instance.ruta_id)


@receiver(post_delete, sender=Parada)
def invalidate_route_snapshots_on_stop_delete(sender, instance, **kwargs):
    services.invalidate_route_snapshots_for_route(instance.ruta_id)
