# rutas/migrations/0003_add_graphhopper_fields.py
#
# Añade los campos de geometría y métricas de GraphHopper a Ruta y Parada.
# Dependencia: última migración real de la app rutas.

import django.contrib.gis.db.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rutas', '0002_alter_parada_orden_alter_ruta_duracion_horas_and_more'),
    ]

    operations = [
        # ── Ruta: geometría y métricas totales ───────────────────────────────
        migrations.AddField(
            model_name='ruta',
            name='geometria_ruta',
            field=django.contrib.gis.db.models.fields.LineStringField(
                blank=True, null=True, srid=4326,
                help_text='Trazado real sobre la red viaria calculado por GraphHopper.',
            ),
        ),
        migrations.AddField(
            model_name='ruta',
            name='distancia_total_m',
            field=models.FloatField(
                blank=True, null=True,
                help_text='Distancia total de la ruta en metros (GraphHopper).',
            ),
        ),
        migrations.AddField(
            model_name='ruta',
            name='duracion_total_s',
            field=models.IntegerField(
                blank=True, null=True,
                help_text='Duración total estimada de la ruta en segundos (GraphHopper).',
            ),
        ),

        # ── Parada: métricas del segmento hacia la siguiente parada ──────────
        migrations.AddField(
            model_name='parada',
            name='distancia_siguiente_m',
            field=models.FloatField(
                blank=True, null=True,
                help_text='Metros desde esta parada hasta la siguiente (GraphHopper).',
            ),
        ),
        migrations.AddField(
            model_name='parada',
            name='duracion_siguiente_s',
            field=models.IntegerField(
                blank=True, null=True,
                help_text='Segundos estimados desde esta parada hasta la siguiente (GraphHopper).',
            ),
        ),
    ]
