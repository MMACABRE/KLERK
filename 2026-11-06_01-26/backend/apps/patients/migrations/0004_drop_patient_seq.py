"""Drop patient_seq. Round 15: patient ids are plain AUTO_INCREMENT and the code is computed by
next_patient_code (legacy nextPatientCode), so the sequence table is no longer needed."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0003_value_key_prefix_index"),
    ]

    operations = [
        migrations.DeleteModel(name="PatientSeq"),
    ]
