"""Remove Component and Language from tickets app state.

These models now live in the components app. The DB tables are unchanged.
The M2M fields on Ticket are updated to point to components.Component
and components.Language.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0006_remove_old_fields"),
        ("components", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="Component"),
                migrations.DeleteModel(name="Language"),
                migrations.AlterField(
                    model_name="ticket",
                    name="components",
                    field=models.ManyToManyField(
                        blank=True,
                        related_name="tickets",
                        to="components.component",
                    ),
                ),
                migrations.AlterField(
                    model_name="ticket",
                    name="languages",
                    field=models.ManyToManyField(
                        blank=True,
                        related_name="tickets",
                        to="components.language",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
