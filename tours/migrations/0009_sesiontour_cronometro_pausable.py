from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tours', '0008_rename_tours_recor_sesion__272d0f_idx_tours_recor_sesion__31f651_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='sesiontour',
            name='cronometro_pausado',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='sesiontour',
            name='cronometro_pausado_desde',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='sesiontour',
            name='cronometro_segundos_pausa_acumulados',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
