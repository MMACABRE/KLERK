"""The search keys of a patient (SPEC §2.2): one helper, called from Patient.save() and by the
migration tool.

A key is apps.core.text.fa_key of the text, so Persian variants and ASCII case compare equal. A
missing text gives
the empty key.
"""

from typing import Any

from apps.core.text import fa_key, nocase_key


def apply_keys(patient: Any) -> None:
    """Set every key column of a patient from its text columns."""
    patient.name_key = fa_key(f"{patient.first_name} {patient.last_name}")
    patient.father_name_key = fa_key(patient.father_name or "")
    patient.city_key = fa_key(patient.city or "")
    patient.allergies_key = fa_key(patient.allergies or "")
    patient.conditions_key = fa_key(patient.conditions or "")
    patient.visit_reason_key = fa_key(patient.visit_reason or "")
    patient.referral_key = fa_key(patient.referral or "")
    patient.last_name_sort = nocase_key(patient.last_name)
    patient.first_name_sort = nocase_key(patient.first_name)


def key_of(text: str | None) -> str:
    """The key of one text, for a search or a value key."""
    return fa_key(text or "")
