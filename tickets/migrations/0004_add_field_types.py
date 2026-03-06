"""Add Component and Language models, new date fields, and choice constraints.

Step 1 of 3: adds new schema alongside old fields for data migration.
"""

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0003_move_models_to_apps"),
    ]

    operations = [
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
        # Rename old fields so new ones can take their names
        migrations.RenameField(
            model_name="ticket",
            old_name="target_components",
            new_name="_components_str",
        ),
        migrations.RenameField(
            model_name="ticket",
            old_name="languages",
            new_name="_languages_str",
        ),
        migrations.RenameField(
            model_name="ticket",
            old_name="created_date",
            new_name="_created_date_str",
        ),
        # Add new M2M fields
        migrations.AddField(
            model_name="ticket",
            name="components",
            field=models.ManyToManyField(blank=True, related_name="tickets", to="tickets.component"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="languages",
            field=models.ManyToManyField(blank=True, related_name="tickets", to="tickets.language"),
        ),
        # Add new date fields
        migrations.AddField(
            model_name="ticket",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="ticket",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        # Add choices to existing fields
        migrations.AlterField(
            model_name="ticket",
            name="priority",
            field=models.CharField(blank=True, choices=[("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low")], max_length=50),
        ),
        migrations.AlterField(
            model_name="ticket",
            name="complexity",
            field=models.CharField(blank=True, choices=[("small", "Small"), ("medium", "Medium"), ("large", "Large")], max_length=50),
        ),
        migrations.AlterField(
            model_name="ticket",
            name="ticket_type",
            field=models.CharField(choices=[("feature", "Feature"), ("bug", "Bug"), ("task", "Task")], default="feature", max_length=50),
        ),
        # Clean up null=True on text fields (use blank="" instead)
        migrations.AlterField(
            model_name="ticket",
            name="author",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AlterField(
            model_name="ticket",
            name="summary",
            field=models.TextField(blank=True),
        ),
    ]
