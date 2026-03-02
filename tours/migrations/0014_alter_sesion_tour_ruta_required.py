# Generated manually on 2026-03-02
# Step 3: Make ruta field required (null=False) without hardcoded default

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tours', '0013_populate_ruta_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sesion_tour',
            name='ruta',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='sesiones',
                to='rutas.ruta'
            ),
        ),
    ]
