"""Move HLR, LLR, and TicketRequirement models from tickets to requirements app.

Uses SeparateDatabaseAndState because the underlying DB tables already exist
with the correct schema — we only need to update Django's migration state.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tickets", "0002_ticket_embeddings"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="HighLevelRequirement",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("description", models.TextField()),
                    ],
                    options={
                        "db_table": "high_level_requirements",
                    },
                ),
                migrations.CreateModel(
                    name="LowLevelRequirement",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("description", models.TextField()),
                        ("verification", models.CharField(choices=[("automated", "Automated"), ("review", "Review"), ("inspection", "Inspection")], default="review", max_length=20)),
                        ("high_level_requirement", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="low_level_requirements", to="requirements.highlevelrequirement")),
                    ],
                    options={
                        "db_table": "low_level_requirements",
                    },
                ),
                migrations.CreateModel(
                    name="TicketRequirement",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("low_level_requirement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="requirements.lowlevelrequirement")),
                        ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tickets.ticket")),
                    ],
                    options={
                        "db_table": "ticket_requirements",
                        "unique_together": {("ticket", "low_level_requirement")},
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
