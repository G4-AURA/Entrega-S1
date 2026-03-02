# Generated manually on 2026-03-02
# Step 2: Data migration to assign correct ruta to existing sessions

from django.db import migrations


def populate_ruta_for_existing_sessions(apps, schema_editor):
    """
    Asigna una ruta a todas las sesiones que no tienen una.
    Si existe al menos una ruta, la asigna. Si no, no hace nada.
    """
    SesionTour = apps.get_model('tours', 'SESION_TOUR')
    Ruta = apps.get_model('rutas', 'Ruta')
    
    # Obtener sesiones sin ruta
    sesiones_sin_ruta = SesionTour.objects.filter(ruta__isnull=True)
    
    if sesiones_sin_ruta.exists():
        # Intentar obtener la primera ruta disponible
        primera_ruta = Ruta.objects.first()
        
        if primera_ruta:
            # Asignar la primera ruta (ajusta esta lógica según tus necesidades)
            sesiones_sin_ruta.update(ruta=primera_ruta)
        else:
            # Si no hay rutas, las sesiones quedarán con ruta=None
            # Deberás crearlas manualmente antes de aplicar la siguiente migración
            pass


def reverse_populate(apps, schema_editor):
    """
    No se puede revertir de forma segura sin perder datos.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tours', '0012_alter_sesion_tour_ruta_nullable'),
    ]

    operations = [
        migrations.RunPython(populate_ruta_for_existing_sessions, reverse_populate),
    ]
