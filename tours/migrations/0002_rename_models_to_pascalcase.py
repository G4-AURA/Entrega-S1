# tours/migrations/0002_rename_models_to_pascalcase.py
#
# Migración escrita a mano. El generador automático de Django falla porque:
#
#   BUG A — RenameModel cuando old_name.lower() == new_name.lower():
#     Django usa lowercase como clave interna del estado de migraciones.
#     TURISTA.lower() == Turista.lower() == 'turista'  →  misma clave.
#     rename_model() escribe el nuevo valor, luego borra la clave "vieja"
#     (que es la misma), dejando el estado vacío → KeyError en reload_model.
#     SOLUCIÓN: NO hacer RenameModel para TURISTA ni TURISTASESION.
#     Sus keys internas ya son 'turista' y 'turistasesion' desde 0001.
#     Solo necesitan AlterModelOptions.
#
#   BUG B — RenameModel cambia el nombre de la tabla en BD:
#     SESION_TOUR   →  tabla real: tours_sesion_tour
#     SesionTour    →  tabla por defecto: tours_sesiontour  ← CAMBIA
#     Lo mismo para UBICACION_VIVO y MENSAJE_CHAT.
#     SOLUCIÓN: AlterModelTable inmediatamente después de RenameModel
#     para restaurar el nombre de tabla original y no tocar los datos.
#
# Orden final de operaciones:
#   1. RenameModel + AlterModelTable para los 3 modelos que sí cambian clave
#   2. AlterModelOptions (verbose names, ordering) para los 5 modelos
#   3. AlterField para alias (max_length 255 → 50)
#   4. AddIndex para los 2 índices nuevos

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rutas", "0002_alter_parada_orden_alter_ruta_duracion_horas_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tours", "0001_initial"),
    ]

    operations = [
        # ──────────────────────────────────────────────────────────────────
        # 1. RENOMBRAR modelos cuya clave interna SÍ cambia
        #    (old.lower() != new.lower())
        #
        #    SESION_TOUR  → 'sesion_tour'  /  SesionTour → 'sesiontour'  ✓ diferentes
        #    UBICACION_VIVO → 'ubicacion_vivo'  /  UbicacionVivo → 'ubicacionvivo'  ✓
        #    MENSAJE_CHAT   → 'mensaje_chat'    /  MensajeChat   → 'mensajechat'    ✓
        #
        #    Inmediatamente después de cada RenameModel se restaura el nombre
        #    de tabla para que PostgreSQL no ejecute ningún ALTER TABLE real.
        # ──────────────────────────────────────────────────────────────────
        migrations.RenameModel("SESION_TOUR", "SesionTour"),
        migrations.AlterModelTable("SesionTour", "tours_sesion_tour"),

        migrations.RenameModel("MENSAJE_CHAT", "MensajeChat"),
        migrations.AlterModelTable("MensajeChat", "tours_mensaje_chat"),

        migrations.RenameModel("UBICACION_VIVO", "UbicacionVivo"),
        migrations.AlterModelTable("UbicacionVivo", "tours_ubicacion_vivo"),

        # ──────────────────────────────────────────────────────────────────
        # 2. AlterModelOptions — verbose names y ordering
        #    (db_table se gestiona con AlterModelTable, no aquí)
        #    Nombres de modelo en lowercase tal como Django los almacena.
        # ──────────────────────────────────────────────────────────────────
        migrations.AlterModelOptions(
            name="turista",
            options={
                "verbose_name": "Turista",
                "verbose_name_plural": "Turistas",
            },
        ),
        migrations.AlterModelOptions(
            name="sesiontour",
            options={
                "verbose_name": "Sesión de Tour",
                "verbose_name_plural": "Sesiones de Tour",
            },
        ),
        migrations.AlterModelOptions(
            name="turistasesion",
            options={
                "verbose_name": "Turista en Sesión",
                "verbose_name_plural": "Turistas en Sesión",
            },
        ),
        migrations.AlterModelOptions(
            name="ubicacionvivo",
            options={
                "verbose_name": "Ubicación en Vivo",
                "verbose_name_plural": "Ubicaciones en Vivo",
            },
        ),
        migrations.AlterModelOptions(
            name="mensajechat",
            options={
                "ordering": ["momento"],
                "verbose_name": "Mensaje de Chat",
                "verbose_name_plural": "Mensajes de Chat",
            },
        ),

        # ──────────────────────────────────────────────────────────────────
        # 3. AlterField — alias max_length 255 → 50
        # ──────────────────────────────────────────────────────────────────
        migrations.AlterField(
            model_name="turista",
            name="alias",
            field=models.CharField(max_length=50),
        ),

        # ──────────────────────────────────────────────────────────────────
        # 4. AddIndex — índices de rendimiento nuevos
        # ──────────────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="sesiontour",
            index=models.Index(
                fields=["estado", "fecha_inicio"],
                name="tours_sesio_estado_833f95_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="ubicacionvivo",
            index=models.Index(
                fields=["sesion_tour", "usuario", "-timestamp"],
                name="tours_ubica_sesion__585ebc_idx",
            ),
        ),
    ]