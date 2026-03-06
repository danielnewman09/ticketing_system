"""Move the ticket_embeddings virtual table ownership to the search app.

The table already exists from tickets.0002_ticket_embeddings. This migration
is a no-op that establishes search as the owner in Django's migration state.
"""

from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tickets", "0002_ticket_embeddings"),
    ]

    operations = []
