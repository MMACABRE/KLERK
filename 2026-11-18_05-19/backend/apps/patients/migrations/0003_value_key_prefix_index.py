"""The index on (box_id, value_key(191)) of SPEC §2.2.

A prefix length cannot be written in the model, so it is raw SQL here. The migration state does not
track it; the reverse drops it.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0002_name_sort_keys"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX patient_values_box_value_key "
                "ON patient_values (box_id, value_key(191))"
            ),
            reverse_sql="DROP INDEX patient_values_box_value_key ON patient_values",
        ),
    ]
