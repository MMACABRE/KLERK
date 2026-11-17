"""Copy a legacy SQLite clinic database into the MySQL schema (SPEC §10).

python tools/migrate_sqlite.py --sqlite PATH [--patients-dir DIR] --verify-only Validate, then
run the whole copy inside one transaction against the migrated target, and roll it back. python
tools/migrate_sqlite.py --sqlite PATH [--patients-dir DIR] [--replace] Copy. An empty target
needs nothing; a non-empty one needs --replace. All or nothing: one transaction holds the clear
and every insert, and a failure leaves the previous target as it was. python
tools/migrate_sqlite.py --sqlite PATH [--patients-dir DIR] --check Compare the target with the
source (rows, money totals, per-visit owed and paid, AUTO_INCREMENT, folders). Exit 1 on any
difference.

Run from transformed/backend with the database settings in the environment
(DJANGO_SETTINGS_MODULE and the MYSQL_* variables). The source is opened read-only and
immutable (it may sit on a read-only mount), after refusing a non-empty <db>-wal file next to
it.
Python validates legacy shapes, NULLs, type affinity, exact decimals and orphans (with row ids).
Everything else is left to the database, whose error is reported by table, chunk, MySQL error
number and constraint name only. Output never contains row contents."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from apps.accounts.hashers import UNUSABLE_MARKER, rename_legacy  # noqa: E402
from apps.billing.bill import bill_totals  # noqa: E402
from apps.core.codes import is_code  # noqa: E402
from apps.core.legacy_time import read_stored  # noqa: E402
from apps.core.perms import parse_perms  # noqa: E402
from apps.core.text import fa_key, nocase_key  # noqa: E402
from apps.patients.keys import apply_keys, key_of  # noqa: E402

SCHEMA_MIGRATIONS = [
    f"{n:03d}_{name}.sql"
    for n, name in [
        (1, "init"),
        (2, "patient_ids"),
        (3, "visit_referral_photo"),
        (4, "drop_consent_status"),
        (5, "user_deleted"),
        (6, "visits"),
        (7, "visit_duration"),
        (8, "permissions"),
        (9, "storage"),
        (10, "finance"),
        (11, "sms"),
        (12, "patient_code_flag"),
        (13, "father_name"),
        (14, "catalog_deleted"),
        (15, "default_clinic_name"),
        (16, "visit_duration_90"),
        (17, "layouts"),
        (18, "choice_seq"),
    ]
]

# Copy order (SPEC §10 item 2, with login_attempts last).
COPY_ORDER = [
    "users",
    "patients",
    "medications",
    "documents",
    "saved_searches",
    "audit_log",
    "visits",
    "catalog",
    "lots",
    "stock_moves",
    "settings",
    "bill_lines",
    "accounts",
    "pay_methods",
    "payments",
    "sms_credentials",
    "sms_messages",
    "layouts",
    "custom_boxes",
    "patient_values",
    "login_attempts",
]
NOT_COPIED = {"sessions", "schema_migrations", "patient_seq", "sqlite_sequence"}
CHUNK_ROWS = 1000

MONEY = {
    ("bill_lines", "unit_price"),
    ("bill_lines", "override_price"),
    ("bill_lines", "disc_value"),
    ("payments", "amount"),
    ("catalog", "sale_price"),
    ("catalog", "purchase_cost"),
    ("visits", "disc_value"),
    ("patients", "disc_value"),
    ("lots", "unit_cost"),
    ("sms_messages", "due_at"),
    ("login_attempts", "ts"),
}
QTY = {
    ("bill_lines", "qty"),
    ("stock_moves", "qty"),
    ("lots", "qty_in"),
    ("lots", "remaining"),
    ("catalog", "low_warn"),
    ("catalog", "low_crit"),
    ("patients", "height_cm"),
    ("patients", "weight_kg"),
}
DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
TIME_TEXT = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
CONSTRAINT_NAME = re.compile(r"(?:key|constraint) '([A-Za-z0-9_.]+)'")
TARGET_NAME = {("users", "password_hash"): "password"}


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def problem(self, table: str, row_id: object, column: str, text: str) -> None:
        self.problems.append(f"{table} id={row_id} column={column}: {text}")

    def warn(self, table: str, row_id: object, column: str, text: str) -> None:
        self.warnings.append(f"{table} id={row_id} column={column}: {text}")


@dataclass
class Plan:
    columns: dict[str, list[str]] = field(default_factory=dict)
    kinds: dict[str, dict[str, str]] = field(default_factory=dict)
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    patient_seq_max: int = 0

    def auto_increment(self, table: str) -> int | None:
        """The AUTO_INCREMENT value the copy must leave behind (None for a table without an id)."""
        if "id" not in self.columns.get(table, []) or not has_auto_pk(table):
            return None
        ids = [int(r["id"]) for r in self.rows.get(table, [])]
        top = max(ids, default=0)
        if table == "patients":
            top = max(top, self.patient_seq_max)
        return top + 1


# ---- source and schema -------------------------------------------------------------


def unsaved_wal(path: Path) -> str | None:
    """A refusal when a non-empty `<db>-wal` sits next to the source: it may hold saved changes
    that are not yet in the main file, and the immutable open below would not read them."""
    wal = path.with_name(path.name + "-wal")
    if wal.exists() and wal.stat().st_size > 0:
        return (
            f"refused: {wal.name} is not empty, so the copy may lack saved changes. Stop the old "
            "app cleanly and copy again (docs/DEPLOY-AGENT-CUTOVER.md step 3)"
        )
    return None


def open_source(path: Path) -> sqlite3.Connection:
    # immutable=1: the source is a frozen copy on a read-only mount. Without it, SQLite would
    # have to create <db>-shm next to a WAL-mode database just to read it, which a read-only
    # folder forbids. Callers check unsaved_wal() first: an immutable open ignores the -wal file.
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def check_schema(con: sqlite3.Connection) -> list[str]:
    names = [row[0] for row in con.execute("SELECT name FROM schema_migrations")]
    if sorted(names) != sorted(SCHEMA_MIGRATIONS):
        missing = sorted(set(SCHEMA_MIGRATIONS) - set(names))
        unknown = sorted(set(names) - set(SCHEMA_MIGRATIONS))
        return [f"schema_migrations is not 001-018: missing {missing}, unknown {unknown}"]
    return []


def source_tables(con: sqlite3.Connection) -> list[str]:
    return [
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    ]


def source_rows(con: sqlite3.Connection, table: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    cursor = con.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
    columns = [d[0] for d in cursor.description]
    return columns, cursor.fetchall()


def target_model(table: str) -> Any:
    from django.apps import apps as django_apps

    for model in django_apps.get_models():
        if model._meta.db_table == table:
            return model
    return None


def field_by_column(model: Any) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for f in model._meta.concrete_fields:
        mapping.setdefault(f.name, f)
        mapping.setdefault(f.column, f)
    return mapping


def kind_of(f: Any, table: str, column: str) -> str:
    from django.db import models

    if (table, column) in MONEY:
        return "int"
    if (table, column) in QTY:
        return "dec"
    if column == "code" and table == "patients":
        return "code"
    if column == "perms" and table == "users":
        return "perms"
    if column == "password_hash" and table == "users":
        return "hash"
    if isinstance(f, models.DateTimeField):
        return "datetime"
    if isinstance(f, models.DateField):
        return "date"
    if isinstance(f, models.TimeField):
        return "time"
    if isinstance(f, models.BooleanField):
        return "bool"
    if isinstance(f, models.JSONField):
        return "json"
    if isinstance(f, models.DecimalField):
        return "dec"
    if isinstance(f, models.IntegerField) or f.is_relation:
        return "int"
    return "text"


# ---- conversion (Python validates only what the database cannot report usefully) ----


def exact_decimal(value: object, max_digits: int, decimal_places: int) -> Decimal | None:
    """A decimal is accepted only if it already has at most `decimal_places` digits and fits the
    field. nan, inf, 0.005 (not exact at 2 places) and 1e-9 are refused."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    exact = Decimal(str(value))
    if not exact.is_finite():
        return None
    quantum = Decimal(1).scaleb(-decimal_places)
    rounded = exact.quantize(quantum)
    if exact != rounded:
        return None
    if abs(rounded) >= Decimal(10) ** (max_digits - decimal_places):
        return None
    return rounded


def convert(
    report: Report, table: str, row_id: object, column: str, value: Any, kind: str, f: Any
) -> Any:
    if value is None:
        if not f.null and not f.primary_key and kind != "hash":
            report.problem(table, row_id, column, "NULL in a column that must have a value")
        return None
    if kind == "int":
        if type(value) is not int:
            report.problem(table, row_id, column, f"not an integer ({type(value).__name__})")
            return None
        return value
    if kind == "bool":
        if type(value) is not int or value not in (0, 1):
            report.problem(table, row_id, column, "not 0 or 1")
            return None
        return bool(value)
    if kind == "dec":
        decimal = exact_decimal(value, f.max_digits, f.decimal_places)
        if decimal is None:
            report.problem(
                table, row_id, column, "not an exact decimal that fits the column (2 places)"
            )
        return decimal
    if kind == "date":
        if type(value) is not str or not DATE_TEXT.fullmatch(value):
            report.problem(table, row_id, column, "not YYYY-MM-DD")
            return None
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            report.problem(table, row_id, column, "not a real date")
            return None
    if kind == "time":
        if type(value) is not str or not TIME_TEXT.fullmatch(value):
            report.problem(table, row_id, column, "not HH:MM")
            return None
        return dt.time(int(value[:2]), int(value[3:5]))
    if kind == "datetime":
        try:
            aware = read_stored(value)
        except (TypeError, ValueError):
            report.problem(table, row_id, column, "timestamp is not one of the three legacy shapes")
            return None
        return aware.astimezone(dt.UTC).replace(tzinfo=None) if aware else None
    if kind == "json":
        if type(value) is not str:
            report.problem(table, row_id, column, "JSON column is not text")
            return None
        try:
            return json.dumps(json.loads(value), ensure_ascii=False, sort_keys=True)
        except ValueError:
            report.problem(table, row_id, column, "not valid JSON")
            return None
    if kind == "code":
        if type(value) is not str or not is_code(value):
            report.problem(table, row_id, column, "patient code is not P- and six ASCII digits")
            return None
        return value
    if kind == "perms":
        return json.dumps(parse_perms(value), ensure_ascii=False, sort_keys=True)
    if kind == "hash":
        return value
    if kind == "text":
        if type(value) is not str:
            report.problem(table, row_id, column, f"not text ({type(value).__name__})")
            return None
        return value
    raise AssertionError(kind)


def password_for(report: Report, row_id: object, value: Any) -> str:
    """A legacy hash to the new prefix. An empty or refused one becomes the one fixed unusable
    marker, so a repeated copy and check see the same value."""
    if value is None or value == "":
        report.warn("users", row_id, "password_hash", "no password: the account cannot sign in")
        return UNUSABLE_MARKER
    try:
        return rename_legacy(value)
    except ValueError:
        report.warn("users", row_id, "password_hash", "hash refused: the account must be reset")
        return UNUSABLE_MARKER


def build_plan(con: sqlite3.Connection, report: Report) -> Plan:
    plan = Plan()
    legacy_ids: dict[str, set[Any]] = {}
    for table in source_tables(con):
        if table not in NOT_COPIED:
            _, rows = source_rows(con, table)
            legacy_ids[table] = {r[0] for r in rows} if rows else set()
    if "patient_seq" in source_tables(con):
        plan.patient_seq_max = max(
            (r[0] for r in con.execute("SELECT id FROM patient_seq")), default=0
        )
    for table in COPY_ORDER:
        model = target_model(table)
        if model is None:
            report.problem(table, "-", "-", "no target model for this table")
            continue
        columns, rows = source_rows(con, table)
        fields = field_by_column(model)
        target_cols: list[str] = []
        kinds: dict[str, str] = {}
        pairs: list[tuple[str, str, Any]] = []
        for col in columns:
            f = fields.get(TARGET_NAME.get((table, col), col))
            if f is None or type(f).__name__ == "GeneratedField":
                report.warn(table, "-", col, "column is not in the target schema: not copied")
                continue
            pairs.append((col, f.column, f))
            target_cols.append(f.column)
            kinds[f.column] = kind_of(f, table, col)
        plan.columns[table] = target_cols
        plan.kinds[table] = kinds
        plan.rows[table] = []
        id_index = columns.index("id") if "id" in columns else None
        for raw in rows:
            row_id = raw[id_index] if id_index is not None else "-"
            out: dict[str, Any] = {}
            for col, target_col, f in pairs:
                value = raw[columns.index(col)]
                converted = convert(report, table, row_id, col, value, kinds[target_col], f)
                if f.is_relation and value is not None:
                    parent = f.related_model._meta.db_table
                    if value not in legacy_ids.get(parent, set()):
                        report.problem(table, row_id, col, f"no {parent} row with this id (orphan)")
                out[target_col] = converted
            if table == "users":
                out["password"] = password_for(report, row_id, raw[columns.index("password_hash")])
                out["username_key"] = nocase_key(out["username"] or "")
                plan.kinds[table]["password"] = "hash"
                plan.kinds[table]["username_key"] = "text"
                for name in ("password", "username_key"):
                    if name not in target_cols:
                        target_cols.append(name)
            if table == "patients":
                keyed = SimpleNamespace(
                    **{
                        k: out.get(k)
                        for k in (
                            "first_name",
                            "last_name",
                            "father_name",
                            "city",
                            "allergies",
                            "conditions",
                            "visit_reason",
                            "referral",
                        )
                    }
                )
                apply_keys(keyed)
                for key in (
                    "name_key",
                    "father_name_key",
                    "city_key",
                    "allergies_key",
                    "conditions_key",
                    "visit_reason_key",
                    "referral_key",
                    "last_name_sort",
                    "first_name_sort",
                ):
                    out[key] = getattr(keyed, key)
                    if key not in target_cols:
                        target_cols.append(key)
                        plan.kinds[table][key] = "text"
            if table == "catalog":
                out["name_key"] = fa_key(out.get("name") or "")
                if "name_key" not in target_cols:
                    target_cols.append("name_key")
                    plan.kinds[table]["name_key"] = "text"
            if table == "patient_values":
                out["value_key"] = key_of(out.get("value"))
                if "value_key" not in target_cols:
                    target_cols.append("value_key")
                    plan.kinds[table]["value_key"] = "text"
            plan.rows[table].append(out)
    return plan


def source_bills(con: sqlite3.Connection) -> dict[int, tuple[int, int]]:
    """Owed and paid per visit from the source, with the Python bill port (apps/billing/bill.py)."""
    result: dict[int, tuple[int, int]] = {}
    for visit_id, status, disc_kind, disc_value in con.execute(
        "SELECT id, status, disc_kind, disc_value FROM visits ORDER BY id"
    ).fetchall():
        lines = [
            {
                "unit_price": u,
                "override_price": o,
                "qty": q,
                "disc_kind": k,
                "disc_value": v,
            }
            for u, o, q, k, v in con.execute(
                "SELECT unit_price, override_price, qty, disc_kind, disc_value FROM bill_lines "
                "WHERE visit_id = ?",
                (visit_id,),
            )
        ]
        payments = [
            r[0] for r in con.execute("SELECT amount FROM payments WHERE visit_id = ?", (visit_id,))
        ]
        totals = bill_totals(
            lines,
            payments,
            cancelled=status == "cancelled",
            disc_kind=disc_kind,
            disc_value=disc_value,
        )
        result[visit_id] = (totals.owed, totals.paid)
    return result


def target_bills() -> dict[int, tuple[int, int]]:
    """The same per-visit totals, from the rows MySQL holds."""
    from django.db import connection

    result: dict[int, tuple[int, int]] = {}
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, status, disc_kind, disc_value FROM visits ORDER BY id")
        visits = cursor.fetchall()
        cursor.execute(
            "SELECT visit_id, unit_price, override_price, qty, disc_kind, disc_value FROM "
            "bill_lines"
        )
        lines_by: dict[int, list[dict[str, Any]]] = {}
        for vid, u, o, q, k, v in cursor.fetchall():
            lines_by.setdefault(vid, []).append(
                {"unit_price": u, "override_price": o, "qty": q, "disc_kind": k, "disc_value": v}
            )
        cursor.execute("SELECT visit_id, amount FROM payments")
        payments_by: dict[int, list[int]] = {}
        for vid, amount in cursor.fetchall():
            payments_by.setdefault(vid, []).append(int(amount))
    for visit_id, status, disc_kind, disc_value in visits:
        totals = bill_totals(
            lines_by.get(visit_id, []),
            payments_by.get(visit_id, []),
            cancelled=status == "cancelled",
            disc_kind=disc_kind,
            disc_value=disc_value,
        )
        result[visit_id] = (totals.owed, totals.paid)
    return result


def payments_between_minus_4_and_minus_1(con: sqlite3.Connection) -> int:
    """The count only (quirk row 1): payments of -4 to -1 Rial."""
    return int(
        con.execute("SELECT COUNT(*) FROM payments WHERE amount BETWEEN -4 AND -1").fetchone()[0]
    )


def folder_report(
    con: sqlite3.Connection, patients_dir: Path | None, report: Report
) -> dict[str, Any]:
    """Codes only: a patient without a folder, a folder without a patient, and documents whose file
    is missing."""
    result: dict[str, Any] = {
        "codes_without_folder": [],
        "folders_without_patient": [],
        "documents_missing_file": 0,
    }
    if patients_dir is None:
        return result
    codes = {r[0] for r in con.execute("SELECT code FROM patients WHERE code IS NOT NULL")}
    folders = (
        {p.name for p in patients_dir.iterdir() if p.is_dir()} if patients_dir.is_dir() else set()
    )
    result["codes_without_folder"] = sorted(codes - folders)
    result["folders_without_patient"] = sorted(folders - codes)
    for code, filename in con.execute(
        "SELECT p.code, d.filename FROM documents d JOIN patients p ON p.id = d.patient_id"
    ):
        if not (patients_dir / str(code) / str(filename)).is_file():
            result["documents_missing_file"] += 1
    return result


# ---- MySQL: preflight, copy (one transaction), reads --------------------------------


class DryRunDone(Exception):
    """Raised inside the copy transaction to roll it back on purpose (--verify-only)."""


class CopyFailed(Exception):
    """A database error or a count mismatch inside the copy; the transaction is rolled back."""


def preflight() -> str | None:
    """One line when the target has migrations that are not applied yet."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if pending:
        return (
            f"target has {len(pending)} unapplied migration(s): run python manage.py migrate first"
        )
    return None


def target_counts() -> dict[str, int]:
    from django.db import connection

    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table in COPY_ORDER:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            counts[table] = int(cursor.fetchone()[0])
    return counts


def database_error_line(table: str, chunk: int | str, exc: BaseException) -> str:
    """Table, chunk, MySQL error number and constraint name. Never the message or the "
    "values in it."""
    args: tuple[Any, ...] = getattr(exc, "args", ())
    errno = args[0] if args and isinstance(args[0], int) else "-"
    text = str(args[1]) if len(args) > 1 else ""
    match = CONSTRAINT_NAME.search(text)
    name = match.group(1) if match else "-"
    return f"copy failed: table={table} chunk={chunk} mysql_errno={errno} constraint={name}"


def write_all(plan: Plan, *, replace: bool, dry_run: bool) -> dict[str, int]:
    """Clear (when replacing) and insert every table inside ONE transaction, then check each table's
    row count. Any failure rolls the whole transaction back. Raises CopyFailed (after printing
    one line) or DryRunDone."""
    from django.db import DatabaseError, connection, transaction

    written: dict[str, int] = {}
    try:
        with transaction.atomic():
            if replace:
                with connection.cursor() as cursor:
                    for table in reversed(COPY_ORDER):
                        try:
                            cursor.execute(f"DELETE FROM `{table}`")
                        except DatabaseError as exc:
                            print(database_error_line(table, "clear", exc))
                            raise CopyFailed from None
            for table in COPY_ORDER:
                columns = plan.columns.get(table, [])
                rows = plan.rows.get(table, [])
                if not columns or not rows:
                    written[table] = 0
                    continue
                names = ", ".join(f"`{c}`" for c in columns)
                sql = f"INSERT INTO `{table}` ({names}) VALUES ({', '.join(['%s'] * len(columns))})"
                for chunk, start in enumerate(range(0, len(rows), CHUNK_ROWS), start=1):
                    batch = rows[start : start + CHUNK_ROWS]
                    values = [[row.get(c) for c in columns] for row in batch]
                    try:
                        with connection.cursor() as cursor:
                            cursor.executemany(sql, values)
                    except DatabaseError as exc:
                        print(database_error_line(table, chunk, exc))
                        raise CopyFailed from None
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                    stored = int(cursor.fetchone()[0])
                if stored != len(rows):
                    print(f"copy failed: table={table} row count {stored} differs from the plan")
                    raise CopyFailed
                written[table] = len(rows)
            if dry_run:
                raise DryRunDone
    except DryRunDone:
        return written
    except CopyFailed:
        print("nothing written: the target is unchanged (transaction rolled back)")
        raise
    return written


def set_auto_increment(plan: Plan) -> None:
    """After the commit: AUTO_INCREMENT = max id + 1 (idempotent). DDL, so it cannot be part of the
    transaction."""
    from django.db import connection

    with connection.cursor() as cursor:
        for table in COPY_ORDER:
            value = plan.auto_increment(table)
            if value is not None:
                cursor.execute(f"ALTER TABLE `{table}` AUTO_INCREMENT = {value}")


def auto_increments() -> dict[str, int]:
    from django.db import connection

    out: dict[str, int] = {}
    with connection.cursor() as cursor:
        # MySQL caches information_schema statistics for a day by default; read the live value.
        cursor.execute("SET SESSION information_schema_stats_expiry = 0")
        for table in COPY_ORDER:
            cursor.execute(
                "SELECT AUTO_INCREMENT FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                [table],
            )
            row = cursor.fetchone()
            if row is not None and row[0] is not None:
                out[table] = int(row[0])
    return out


# ---- canonical form and checksums -----------------------------------------------------


def canon(kind: str, value: Any) -> str:
    if value is None:
        return "~"
    if kind == "int":
        return str(int(value))
    if kind == "bool":
        return "1" if value else "0"
    if kind == "dec":
        return str(format(Decimal(value).quantize(Decimal("0.01")), "f"))
    if kind == "date":
        return str(value.isoformat())
    if kind == "time":
        if isinstance(value, dt.timedelta):
            seconds = int(value.total_seconds())
            return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
        return str(value.strftime("%H:%M:%S"))
    if kind == "datetime":
        return str(value.isoformat(timespec="microseconds"))
    if kind in ("json", "perms"):
        return json.dumps(json.loads(value), ensure_ascii=False, sort_keys=True)
    return str(value)


def digest(rows: list[list[str]]) -> str:
    h = hashlib.sha256()
    for row in rows:
        h.update("\x1f".join(row).encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


def has_auto_pk(table: str) -> bool:
    return target_model(table)._meta.pk.get_internal_type() in ("AutoField", "BigAutoField")


def pk_columns(table: str) -> list[str]:
    """The primary key columns in order: one for most tables, two for patient_values (composite)."""
    pk = target_model(table)._meta.pk
    if hasattr(pk, "fields"):
        return [f.column for f in pk.fields]
    return [pk.column]


def plan_digests(plan: Plan) -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for table in COPY_ORDER:
        columns = plan.columns.get(table, [])
        if not columns:
            out[table] = (0, digest([]))
            continue
        keys = pk_columns(table)
        rows = sorted(plan.rows[table], key=lambda r: tuple(r.get(k) for k in keys))
        canonical = [[canon(plan.kinds[table][c], r.get(c)) for c in columns] for r in rows]
        out[table] = (len(rows), digest(canonical))
    return out


def target_digests(plan: Plan) -> dict[str, tuple[int, str]]:
    """Digests of what MySQL holds, over exactly the columns the plan writes, in "
    "primary-key order."""
    from django.db import connection

    out: dict[str, tuple[int, str]] = {}
    with connection.cursor() as cursor:
        for table in COPY_ORDER:
            columns = plan.columns.get(table, [])
            if not columns:
                out[table] = (0, digest([]))
                continue
            order = ", ".join(f"`{c}`" for c in pk_columns(table))
            names = ", ".join(f"`{c}`" for c in columns)
            cursor.execute(f"SELECT {names} FROM `{table}` ORDER BY {order}")
            canonical = [
                [canon(plan.kinds[table][c], v) for c, v in zip(columns, row, strict=True)]
                for row in cursor.fetchall()
            ]
            out[table] = (len(canonical), digest(canonical))
    return out


def sums_and_counts() -> dict[str, Any]:
    from django.db import connection

    queries = {
        "bill_lines.unit_price": "SELECT COALESCE(SUM(unit_price),0) FROM bill_lines",
        "bill_lines.override_price": "SELECT COALESCE(SUM(override_price),0) FROM bill_lines",
        "payments.amount": "SELECT COALESCE(SUM(amount),0) FROM payments",
        "visits.disc_value": "SELECT COALESCE(SUM(disc_value),0) FROM visits",
        "patients.disc_value": "SELECT COALESCE(SUM(disc_value),0) FROM patients",
        "visits.by_status": "SELECT status, COUNT(*) FROM visits GROUP BY status ORDER BY status",
        "payments.by_kind": "SELECT kind, COUNT(*) FROM payments GROUP BY kind ORDER BY kind",
        "sms_messages.by_status": (
            "SELECT status, COUNT(*) FROM sms_messages GROUP BY status ORDER BY status"
        ),
        "catalog.by_kind": "SELECT kind, COUNT(*) FROM catalog GROUP BY kind ORDER BY kind",
    }
    out: dict[str, Any] = {}
    with connection.cursor() as cursor:
        for name, sql in queries.items():
            cursor.execute(sql)
            rows = cursor.fetchall()
            out[name] = [[str(c) for c in r] for r in rows] if ".by_" in name else str(rows[0][0])
    return out


def source_sums(con: sqlite3.Connection) -> dict[str, Any]:
    def one(sql: str) -> str:
        return str(con.execute(sql).fetchone()[0])

    def groups(sql: str) -> list[list[str]]:
        return [[str(c) for c in r] for r in con.execute(sql).fetchall()]

    return {
        "bill_lines.unit_price": one("SELECT COALESCE(SUM(unit_price),0) FROM bill_lines"),
        "bill_lines.override_price": one("SELECT COALESCE(SUM(override_price),0) FROM bill_lines"),
        "payments.amount": one("SELECT COALESCE(SUM(amount),0) FROM payments"),
        "visits.disc_value": one("SELECT COALESCE(SUM(disc_value),0) FROM visits"),
        "patients.disc_value": one("SELECT COALESCE(SUM(disc_value),0) FROM patients"),
        "visits.by_status": groups(
            "SELECT status, COUNT(*) FROM visits GROUP BY status ORDER BY status"
        ),
        "payments.by_kind": groups(
            "SELECT kind, COUNT(*) FROM payments GROUP BY kind ORDER BY kind"
        ),
        "sms_messages.by_status": groups(
            "SELECT status, COUNT(*) FROM sms_messages GROUP BY status ORDER BY status"
        ),
        "catalog.by_kind": groups("SELECT kind, COUNT(*) FROM catalog GROUP BY kind ORDER BY kind"),
    }


# ---- commands ----------------------------------------------------------------------


def validate(con: sqlite3.Connection, report: Report, patients_dir: Path | None) -> Plan | None:
    problems = check_schema(con)
    report.problems.extend(problems)
    if problems:
        return None
    plan = build_plan(con, report)
    print_folders(folder_report(con, patients_dir, report))
    print(
        f"payments between -4 and -1 Rial: {payments_between_minus_4_and_minus_1(con)} (count only)"
    )
    return None if report.problems else plan


def print_folders(folders: dict[str, Any]) -> None:
    print(
        f"patients without a folder: {len(folders['codes_without_folder'])} "
        f"codes {folders['codes_without_folder'][:20]}"
    )
    print(
        f"folders without a patient: {len(folders['folders_without_patient'])} "
        f"codes {folders['folders_without_patient'][:20]}"
    )
    print(f"documents whose file is missing: {folders['documents_missing_file']}")


def print_report(report: Report) -> None:
    for w in report.warnings[:50]:
        print(f"warning: {w}")
    if len(report.warnings) > 50:
        print(f"warning: ... {len(report.warnings) - 50} more")
    for p in report.problems:
        print(f"problem: {p}")
    print(f"{len(report.problems)} problem(s), {len(report.warnings)} warning(s)")


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "klerk.settings.dev")
    import django

    django.setup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--patients-dir", type=Path, default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)

    setup_django()
    refusal = unsaved_wal(args.sqlite)
    if refusal is not None:
        print(refusal)
        print("nothing written")
        return 1
    con = open_source(args.sqlite)
    report = Report()
    try:
        plan = validate(con, report, args.patients_dir)
        print_report(report)
        if plan is None:
            print("nothing written")
            return 1
        pre = preflight()
        if pre is not None:
            print(pre)
            return 1
        digests = plan_digests(plan)
        for table in COPY_ORDER:
            if table in digests:
                print(f"{table}: rows={digests[table][0]} sha256={digests[table][1][:16]}")
        if args.check:
            return run_check(con, plan, digests)
        if args.verify_only:
            try:
                write_all(plan, replace=True, dry_run=True)
            except CopyFailed:
                return 1
            print("verified: the whole copy holds inside one transaction, which was rolled back")
            return 0
        if any(target_counts().values()) and not args.replace:
            print("refused: the target is not empty (use --replace to clear it first)")
            return 1
        try:
            written = write_all(plan, replace=True, dry_run=False)
        except CopyFailed:
            return 1
        set_auto_increment(plan)
        print("written:", ", ".join(f"{t}={n}" for t, n in written.items() if n))
        return 0
    finally:
        con.close()


def run_check(con: sqlite3.Connection, plan: Plan, digests: dict[str, tuple[int, str]]) -> int:
    got = target_digests(plan)
    differences = [t for t in COPY_ORDER if digests.get(t) != got.get(t)]
    for table in differences:
        print(
            f"difference in {table}: source rows={digests.get(table, (0, ''))[0]} "
            f"target rows={got.get(table, (0, ''))[0]}"
        )
    target_sums = sums_and_counts()
    for name, value in source_sums(con).items():
        if value != target_sums.get(name):
            print(f"difference in total {name}")
            differences.append(name)
    source_bill = source_bills(con)
    target_bill = target_bills()
    for visit_id in sorted(set(source_bill) | set(target_bill)):
        if source_bill.get(visit_id) != target_bill.get(visit_id):
            print(f"visit owed/paid differs: id {visit_id}")
            differences.append(f"visit {visit_id}")
    wanted = {table: plan.auto_increment(table) for table in COPY_ORDER}
    stored = auto_increments()
    for table in COPY_ORDER:
        if wanted[table] is not None and stored.get(table) != wanted[table]:
            print(f"difference in AUTO_INCREMENT of {table}")
            differences.append(f"auto_increment {table}")
    print(f"tables compared: {len(COPY_ORDER)}, differences: {len(differences)}")
    for table in COPY_ORDER:
        if table in got:
            print(f"  {table}: rows={got[table][0]} sha256={got[table][1][:16]}")
    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
