# Generated manually on 2026-03-02
# Step 1: Make ruta field nullable to avoid hardcoded default

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rutas', '0002_alter_parada_orden_alter_ruta_duracion_horas_and_more'),
        ('tours', '0011_delete_participant'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sesion_tour',
            name='ruta',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='sesiones',
                to='rutas.ruta'
            ),
        ),
    ]
