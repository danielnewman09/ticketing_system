"""Remove old string fields replaced by typed fields.

Step 3 of 3: cleanup.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0005_migrate_field_data"),
    ]

    operations = [
        migrations.RemoveField(model_name="ticket", name="_components_str"),
        migrations.RemoveField(model_name="ticket", name="_languages_str"),
        migrations.RemoveField(model_name="ticket", name="_created_date_str"),
        migrations.RemoveField(model_name="ticket", name="last_modified"),
    ]
