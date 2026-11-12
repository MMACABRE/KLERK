"""Writes tests/legacy_schema.sql: the legacy migrations 001-018, concatenated in order, for the
migration tests (the container cannot see the repository root). Run on the host: python
transformed/backend/tools/make_legacy_schema.py"""

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2] / "legacy"
OUT = pathlib.Path(__file__).resolve().parents[1] / "tests" / "legacy_schema.sql"


def main() -> None:
    parts = []
    for path in sorted((REPO / "migrations").glob("*.sql")):
        parts.append(f"-- {path.name}\n" + path.read_text(encoding="utf-8").rstrip() + "\n")
    OUT.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.name} from {len(parts)} legacy migrations")


if __name__ == "__main__":
    main()
