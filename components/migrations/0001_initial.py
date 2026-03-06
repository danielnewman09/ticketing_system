"""Move Component and Language models from tickets to components app.

Uses SeparateDatabaseAndState because the underlying DB tables already exist.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tickets", "0006_remove_old_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Component",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=100, unique=True)),
                    ],
                    options={
                        "db_table": "components",
                        "ordering": ["name"],
                    },
                ),
                migrations.CreateModel(
                    name="Language",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=100, unique=True)),
                    ],
                    options={
                        "db_table": "languages",
                        "ordering": ["name"],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
