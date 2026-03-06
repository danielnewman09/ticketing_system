"""Migrate data from old string fields to new typed fields.

Step 2 of 3: converts existing data.
"""

from datetime import datetime, timezone
from django.db import migrations


def migrate_data(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    Component = apps.get_model("tickets", "Component")
    Language = apps.get_model("tickets", "Language")

    for ticket in Ticket.objects.all():
        # Convert created_date string to datetime
        if ticket._created_date_str:
            try:
                dt = datetime.strptime(ticket._created_date_str, "%Y-%m-%d")
                ticket.created_at = dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        # Lowercase choice fields
        if ticket.priority:
            ticket.priority = ticket.priority.lower()
        if ticket.complexity:
            ticket.complexity = ticket.complexity.lower()
        if ticket.ticket_type:
            ticket.ticket_type = ticket.ticket_type.lower()

        # Convert null text fields to empty string
        if ticket.author is None:
            ticket.author = ""
        if ticket.summary is None:
            ticket.summary = ""

        ticket.save()

        # Parse comma-separated components into M2M
        if ticket._components_str:
            for name in ticket._components_str.split(","):
                name = name.strip()
                if name:
                    component, _ = Component.objects.get_or_create(name=name)
                    ticket.components.add(component)

        # Parse comma-separated languages into M2M
        if ticket._languages_str:
            for name in ticket._languages_str.split(","):
                name = name.strip()
                if name:
                    language, _ = Language.objects.get_or_create(name=name)
                    ticket.languages.add(language)


def reverse_data(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")

    for ticket in Ticket.objects.all():
        if ticket.created_at:
            ticket._created_date_str = ticket.created_at.strftime("%Y-%m-%d")
        if ticket.priority:
            ticket.priority = ticket.priority.capitalize()
        if ticket.complexity:
            ticket.complexity = ticket.complexity.capitalize()

        components = ticket.components.all()
        if components:
            ticket._components_str = ", ".join(c.name for c in components)

        languages = ticket.languages.all()
        if languages:
            ticket._languages_str = ", ".join(l.name for l in languages)

        ticket.save()


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0004_add_field_types"),
    ]

    operations = [
        migrations.RunPython(migrate_data, reverse_data),
    ]
