# Generated manually on 2026-03-02

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_existing_messages(apps, schema_editor):
    """Poblar nombre_remitente para mensajes existentes"""
    MENSAJE_CHAT = apps.get_model('tours', 'MENSAJE_CHAT')
    for mensaje in MENSAJE_CHAT.objects.all():
        if mensaje.remitente:
            # Para usuarios registrados, usar su username
            mensaje.nombre_remitente = mensaje.remitente.username
        else:
            # Fallback
            mensaje.nombre_remitente = 'Anónimo'
        mensaje.save(update_fields=['nombre_remitente'])


class Migration(migrations.Migration):

    dependencies = [
        ('tours', '0011_delete_participant'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Añadir campo nombre_remitente
        migrations.AddField(
            model_name='mensaje_chat',
            name='nombre_remitente',
            field=models.CharField(default='Anónimo', max_length=255),
        ),
        
        # Verificar y añadir campo turista solo si no existe
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='tours_mensaje_chat' AND column_name='turista_id'
                    ) THEN
                        ALTER TABLE tours_mensaje_chat 
                        ADD COLUMN turista_id INTEGER NULL 
                        REFERENCES tours_turista(id) ON DELETE CASCADE;
                        
                        CREATE INDEX IF NOT EXISTS tours_mensaje_chat_turista_id_idx 
                        ON tours_mensaje_chat(turista_id);
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE tours_mensaje_chat DROP COLUMN IF EXISTS turista_id;"
        ),
        
        # Hacer remitente opcional (nullable)
        migrations.AlterField(
            model_name='mensaje_chat',
            name='remitente',
            field=models.ForeignKey(
                blank=True, 
                null=True, 
                on_delete=django.db.models.deletion.CASCADE, 
                to=settings.AUTH_USER_MODEL
            ),
        ),
        
        # Migrar datos existentes
        migrations.RunPython(migrate_existing_messages, migrations.RunPython.noop),
    ]
