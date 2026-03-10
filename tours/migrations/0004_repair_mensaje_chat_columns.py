from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tours", "0003_alter_sesiontour_turistas_alter_turista_table_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE tours_mensaje_chat
                ADD COLUMN IF NOT EXISTS nombre_remitente varchar(255);

                UPDATE tours_mensaje_chat
                SET nombre_remitente = 'Anónimo'
                WHERE nombre_remitente IS NULL;

                ALTER TABLE tours_mensaje_chat
                ALTER COLUMN nombre_remitente SET DEFAULT 'Anónimo';

                ALTER TABLE tours_mensaje_chat
                ALTER COLUMN nombre_remitente SET NOT NULL;

                ALTER TABLE tours_mensaje_chat
                ADD COLUMN IF NOT EXISTS turista_id bigint NULL;

                CREATE INDEX IF NOT EXISTS tours_mensaje_chat_turista_id_idx
                ON tours_mensaje_chat (turista_id);

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'tours_mensaje_chat_turista_id_fk'
                    ) THEN
                        ALTER TABLE tours_mensaje_chat
                        ADD CONSTRAINT tours_mensaje_chat_turista_id_fk
                        FOREIGN KEY (turista_id)
                        REFERENCES tours_turista(id)
                        DEFERRABLE INITIALLY DEFERRED;
                    END IF;
                END$$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
