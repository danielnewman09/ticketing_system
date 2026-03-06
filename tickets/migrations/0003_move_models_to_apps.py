"""Remove HLR, LLR, and TicketRequirement from tickets app state.

These models now live in the requirements app. The DB tables are unchanged.
The M2M through table reference on Ticket is updated to point to
requirements.TicketRequirement.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0002_ticket_embeddings"),
        ("requirements", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="TicketRequirement"),
                migrations.DeleteModel(name="LowLevelRequirement"),
                migrations.DeleteModel(name="HighLevelRequirement"),
                migrations.AlterField(
                    model_name="ticket",
                    name="low_level_requirements",
                    field=models.ManyToManyField(
                        blank=True,
                        related_name="tickets",
                        through="requirements.TicketRequirement",
                        to="requirements.lowlevelrequirement",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
