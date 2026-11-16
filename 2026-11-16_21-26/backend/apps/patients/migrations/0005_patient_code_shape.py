"""The database refuses a patient code that is not P- and six ASCII digits (SPEC §2.2, round 15 item
5).

REGEXP_LIKE in a CHECK is deterministic on MySQL 8.4 and is case-sensitive with the 'c' flag. The
services check the same shape first (apps.core.codes.require_code), so this is the backstop."""

from django.db import migrations

CHECK = (
    "ALTER TABLE patients ADD CONSTRAINT patients_code_shape "
    "CHECK (REGEXP_LIKE(code, '^P-[0-9]{6}$', 'c'))"
)


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0004_drop_patient_seq"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CHECK,
            reverse_sql="ALTER TABLE patients DROP CHECK patients_code_shape",
        ),
    ]
