"""Create the sqlite-vec virtual table for ticket embeddings."""

from django.db import migrations


def load_vec_and_create(apps, schema_editor):
    import sqlite_vec
    conn = schema_editor.connection.connection
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS ticket_embeddings USING vec0(
            embedding float[384]
        )
    """)


def drop_table(apps, schema_editor):
    schema_editor.connection.connection.execute(
        "DROP TABLE IF EXISTS ticket_embeddings"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(load_vec_and_create, drop_table),
    ]
