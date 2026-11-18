"""Writes apps/sms/golden/python_sealed.json: secrets sealed by apps.sms.credentials with the key of
node_sealed.json, so the Node test (tools/crypto_fixtures.test.mjs) can open them with the legacy
loadKey.

Run from transformed/backend (after tools/crypto_fixtures.mjs): python
tools/gen_sms_python_sealed.py"""

import base64
import json
import pathlib

from apps.sms.credentials import seal

HERE = pathlib.Path(__file__).resolve().parent
NODE_FIXTURE = HERE.parent / "apps" / "sms" / "golden" / "node_sealed.json"
OUT = HERE.parent / "apps" / "sms" / "golden" / "python_sealed.json"


def main() -> None:
    key_b64 = json.loads(NODE_FIXTURE.read_text(encoding="utf-8"))["key_b64"]
    key = base64.b64decode(key_b64, validate=True)
    cases = []
    for index in range(60):
        plain = f"pythonKey{index:03d}_ABCDEFGHIJ"
        cases.append({"plain": plain, "secret": seal(plain, key)})
    OUT.write_text(
        json.dumps({"key_b64": key_b64, "cases": cases}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(cases)} python-sealed secrets")


if __name__ == "__main__":
    main()
