from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tours", "0004_repair_mensaje_chat_columns"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE tours_mensaje_chat
                ALTER COLUMN remitente_id DROP NOT NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
