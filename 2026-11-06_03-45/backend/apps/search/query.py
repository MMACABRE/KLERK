"""Advanced search (SPEC §3.10; legacy src/lib/search-sql.js) as Django Q objects.

Field names and operators come ONLY from the whitelists below; user values reach the database only as ORM
parameters. Custom box fields `c<id>` exist only for live boxes read from the table.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Any

from django.db.models import Exists, FloatField, OuterRef, Q
from django.db.models.functions import Cast
from django.utils import timezone

from apps.core.jalali import TEHRAN, fa_digits, parse_jalali
from apps.core.labels import SEX, STATUS
from apps.core.text import fa_key, normalize_text, to_ascii_digits
from apps.patients.custom_boxes import live_custom_boxes
from apps.patients.models import PatientValue

MAX_RULES = 6
STATUS_KEYS = ["active", "pending", "critical", "archived"]


class SearchError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


FIELDS: dict[str, dict[str, Any]] = {
    "name": {"col": "name_key", "key": True, "type": "text", "label": "نام و نام خانوادگی"},
    "father_name": {"col": "father_name_key", "key": True, "type": "text", "label": "نام پدر"},
    "code": {"col": "code", "type": "text", "label": "کد بیمار"},
    "national_id": {"col": "national_id", "type": "text", "label": "کد ملی"},
    "phone": {"col": "phone", "type": "text", "label": "تلفن"},
    "city": {"col": "city_key", "key": True, "type": "text", "label": "شهر"},
    "allergies": {"col": "allergies_key", "key": True, "type": "text", "label": "حساسیت‌ها"},
    "conditions": {"col": "conditions_key", "key": True, "type": "text", "label": "بیماری‌ها"},
    "visit_reason": {"col": "visit_reason_key", "key": True, "type": "text", "label": "علت مراجعه"},
    "referral": {"col": "referral_key", "key": True, "type": "text", "label": "معرف"},
    "blood_type": {"col": "blood_type", "type": "enum", "label": "گروه خونی",
                   "values": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]},
    "sex": {"col": "sex", "type": "enum", "label": "جنسیت", "values": ["female", "male"], "valueLabels": SEX},
    "status": {"col": "status", "type": "enum", "label": "وضعیت", "values": STATUS_KEYS,
               "valueLabels": {k: v["label"] for k, v in STATUS.items()}},
    "age": {"col": "age", "type": "number", "label": "سن"},
    "birth_date": {"col": "birth_date", "type": "date", "label": "تاریخ تولد"},
    "created_at": {"col": "created_at", "type": "date", "local": True, "label": "تاریخ ثبت پرونده"},
    "updated_at": {"col": "updated_at", "type": "date", "local": True, "label": "آخرین تغییر"},
}

UI_OPS = {
    "text": ["contains", "not_contains", "equals"],
    "code": ["contains", "equals"],
    "number": ["eq", "lt", "gt", "between"],
    "date": ["before", "after", "between"],
    "enum": ["is", "is_not"],
}
CODE_FIELDS = {"code", "national_id", "phone"}
HIDDEN_FIELDS = {"status"}
for _key, _f in FIELDS.items():
    _f["ops"] = UI_OPS["code" if _key in CODE_FIELDS else _f["type"]]
    _f["hidden"] = _key in HIDDEN_FIELDS
    if _f["type"] == "enum" and not _f["hidden"]:
        _f["choices"] = [[v, (_f.get("valueLabels") or {}).get(v, v)] for v in _f["values"]]

OPERATORS = {
    "text": {"contains": "شامل", "not_contains": "شامل نباشد", "equals": "برابر"},
    "number": {"eq": "برابر", "lt": "کمتر از", "gt": "بیشتر از", "between": "بین"},
    "date": {"eq": "برابر", "before": "قبل از", "after": "بعد از", "between": "بین"},
    "enum": {"is": "باشد", "is_not": "نباشد"},
}
CUSTOM_KIND = {"short_text": "text", "long_text": "text", "number": "number", "date": "date", "choice": "enum",
               "yes_no": "enum"}


def _blank(v: Any) -> bool:
    return v is None or str(v).strip() == ""


def status_filter(v: Any) -> str:
    return v if isinstance(v, str) and v in STATUS_KEYS else ""


def search_fields() -> dict[str, dict[str, Any]]:
    out = dict(FIELDS)
    for box in live_custom_boxes():
        t = CUSTOM_KIND.get(box.type)
        if not t:
            continue
        f: dict[str, Any] = {"custom": box.pk, "type": t, "label": box.label, "hidden": False}
        if box.type == "choice":
            f["values"] = [str(c["id"]) for c in box.choices or []]
            f["valueLabels"] = {str(c["id"]): c["label"] for c in box.choices or []}
        elif box.type == "yes_no":
            f["values"] = ["1", "0"]
            f["valueLabels"] = {"1": "بله", "0": "خیر"}
        f["ops"] = ["is"] if box.type == "yes_no" else UI_OPS[t]
        if "values" in f:
            f["choices"] = [[v, f["valueLabels"][v]] for v in f["values"]]
        out[f"c{box.pk}"] = f
    return out


def _number(v: Any) -> float:
    s = to_ascii_digits(str(v)).strip()
    try:
        n = float(s) if s else 0.0
    except ValueError:
        raise SearchError("مقدار عددی نامعتبر است.") from None
    if not math.isfinite(n):
        raise SearchError("مقدار عددی نامعتبر است.")
    return n


def _date(v: Any) -> date:
    d = parse_jalali(str(v))
    if d is None:
        raise SearchError(f"تاریخ «{fa_digits(str(v)[:20])}» نامعتبر است. نمونه: ۱۴۰۳/۰۵/۱۲")
    return d


def _enum(field: dict[str, Any], v: Any) -> str:
    typed = normalize_text(str(v))
    values: list[str] = field["values"]
    for k in values:
        if k.lower() == typed.lower():
            return k
    labels = field.get("valueLabels") or {}
    for k in values:
        if labels.get(k) and fa_key(labels[k]) == fa_key(typed):
            return k
    raise SearchError("مقدار انتخاب‌شده نامعتبر است.")


def _text_value(field: dict[str, Any], v: Any) -> str:
    if field.get("key"):
        return fa_key(str(v))
    s = to_ascii_digits(str(v).strip())
    if field["col"] == "code":
        return s.upper()
    if field["col"] in ("phone", "national_id"):
        return s.replace(" ", "").replace("-", "").replace("\t", "")
    return s


def _sorted_pair(lo: Any, hi: Any) -> tuple[Any, Any]:
    return (lo, hi) if lo <= hi else (hi, lo)


def _cutoff(today: date, years: int) -> date | None:
    """The latest birth date whose age today is at least `years` (None when no date is that far back)."""
    y = today.year - years
    if y < 1:
        return None
    if y > 9999:
        return date.max
    try:
        return date(y, today.month, today.day)
    except ValueError:
        return date(y, 2, 28)


def _age_at_least(n: int, today: date) -> Q:
    c = _cutoff(today, n)
    return Q(pk__in=[]) if c is None else Q(birth_date__lte=c)


def _age_at_most(n: int, today: date) -> Q:
    c = _cutoff(today, n + 1)
    return Q(birth_date__isnull=False) if c is None else Q(birth_date__gt=c)


def _age_q(op: str, value: Any, value2: Any) -> Q:
    today = timezone.localdate()
    if op == "between":
        if _blank(value2):
            raise SearchError("برای «بین» هر دو مقدار لازم است.")
        lo, hi = _sorted_pair(_number(value), _number(value2))
        return _age_at_least(math.ceil(lo), today) & _age_at_most(math.floor(hi), today)
    n = _number(value)
    if op == "eq":
        return _age_at_least(int(n), today) & _age_at_most(int(n), today) if n.is_integer() else Q(pk__in=[])
    if op == "lt":
        return _age_at_most(math.ceil(n) - 1, today)
    return _age_at_least(math.floor(n) + 1, today)


def _local_start(d: date) -> datetime:
    return datetime.combine(d, time(0), tzinfo=TEHRAN)


def _date_q(field: dict[str, Any], op: str, value: Any, value2: Any) -> Q:
    col = field["col"]
    if op == "between":
        if _blank(value2):
            raise SearchError("برای «بین» هر دو مقدار لازم است.")
        lo, hi = _sorted_pair(_date(value), _date(value2))
        if field.get("local"):
            return Q(**{f"{col}__gte": _local_start(lo), f"{col}__lt": _local_start(hi + timedelta(days=1))})
        return Q(**{f"{col}__range": (lo, hi)})
    d = _date(value)
    if field.get("local"):
        start, nxt = _local_start(d), _local_start(d + timedelta(days=1))
        if op == "eq":
            return Q(**{f"{col}__gte": start, f"{col}__lt": nxt})
        if op == "before":
            return Q(**{f"{col}__lt": start})
        return Q(**{f"{col}__gte": nxt})
    lookup = {"eq": "exact", "before": "lt", "after": "gt"}[op]
    return Q(**{f"{col}__{lookup}": d})


def _custom_q(field: dict[str, Any], op: str, value: Any, value2: Any) -> Q:
    base = PatientValue.objects.filter(patient_id=OuterRef("pk"), box_id=field["custom"])
    negate = False
    t = field["type"]
    if t == "text":
        v = fa_key(str(value))
        if op == "equals":
            sub = base.filter(value_key=v)
        else:
            sub = base.filter(value_key__contains=v)
            negate = op == "not_contains"
    elif t == "enum":
        sub = base.filter(value=_enum(field, value))
        negate = op == "is_not"
    elif t in ("number", "date"):
        if t == "number":
            conv: Any = _number
            sub = base.annotate(_n=Cast("value", FloatField()))
            col = "_n"
        else:
            def conv(x: Any) -> str:
                return _date(x).isoformat()

            sub = base
            col = "value"
        if op == "between":
            if _blank(value2):
                raise SearchError("برای «بین» هر دو مقدار لازم است.")
            lo, hi = _sorted_pair(conv(value), conv(value2))
            sub = sub.filter(**{f"{col}__gte": lo, f"{col}__lte": hi})
        else:
            lookup = {"eq": "exact", "lt": "lt", "gt": "gt", "before": "lt", "after": "gt"}[op]
            sub = sub.filter(**{f"{col}__{lookup}": conv(value)})
    else:
        raise SearchError("نوع فیلد نامعتبر است.")
    q = Q(Exists(sub))
    return ~q if negate else q


def rule_q(rule: dict[str, Any], fields: dict[str, dict[str, Any]]) -> Q:
    key = rule.get("field")
    if not isinstance(key, str) or key not in fields:
        raise SearchError("فیلد جستجو نامعتبر است.")
    field = fields[key]
    op = rule.get("op")
    if not isinstance(op, str) or op not in OPERATORS[field["type"]]:
        raise SearchError("عملگر جستجو نامعتبر است.")
    value, value2 = rule.get("value"), rule.get("value2")
    if field.get("custom"):
        return _custom_q(field, op, value, value2)
    t, col = field["type"], field["col"]
    if t == "text":
        v = _text_value(field, value)
        if op == "equals":
            return Q(**{col: v})
        if op == "contains":
            return Q(**{f"{col}__contains": v})
        return Q(**{f"{col}__isnull": True}) | ~Q(**{f"{col}__contains": v})
    if t == "enum":
        v = _enum(field, value)
        return Q(**{col: v}) if op == "is" else (Q(**{f"{col}__isnull": True}) | ~Q(**{col: v}))
    if col == "age":
        return _age_q(op, value, value2)
    return _date_q(field, op, value, value2)


def build_q(query: dict[str, Any], fields: dict[str, dict[str, Any]] | None = None) -> Q:
    fields = fields or FIELDS
    join_or = query.get("join") == "or"
    raw_rules = query.get("rules")
    rules: list[Any] = raw_rules if isinstance(raw_rules, list) else []
    parts = []
    for rule in rules[:MAX_RULES]:
        if not isinstance(rule, dict) or _blank(rule.get("field")) or _blank(rule.get("value")):
            continue
        parts.append(rule_q(rule, fields))
    q = Q()
    if parts:
        q = parts[0]
        for p in parts[1:]:
            q = (q | p) if join_or else (q & p)
    status = status_filter(query.get("status"))
    if status:
        q = q & Q(status=status) if parts else Q(status=status)
    return q


def query_from_form(params: Any) -> dict[str, Any]:
    """join, s, f1..f6, o1..o6, v1..v6, w1..w6. A repeated parameter becomes a rule that always fails."""

    def one(name: str) -> Any:
        if hasattr(params, "getlist"):
            got = params.getlist(name)
            if len(got) > 1:
                return ["odd"]
            return got[0] if got else None
        v = params.get(name)
        return v if v is None or isinstance(v, str) else ["odd"]

    rules = []
    for i in range(1, MAX_RULES + 1):
        rule = {"field": one(f"f{i}"), "op": one(f"o{i}"), "value": one(f"v{i}"), "value2": one(f"w{i}")}
        odd = any(v is not None and not isinstance(v, str) for v in rule.values())
        rules.append({"field": " invalid", "op": "is", "value": "x"} if odd else rule)
    join = one("join")
    s = one("s")
    return {"join": "or" if join == "or" else "and", "status": status_filter(s), "rules": rules}


def has_rule(r: dict[str, Any]) -> bool:
    return bool(r) and str(r.get("field") or "").strip() != "" and str(r.get("value") or "").strip() != ""


def describe(query: dict[str, Any], fields: dict[str, dict[str, Any]]) -> str:
    rules = [r for r in query["rules"] if has_rule(r)]
    status = status_filter(query.get("status"))
    if not rules and not status:
        return ""
    lines = []
    for r in rules:
        field = fields.get(r["field"]) if isinstance(r["field"], str) else None
        op = OPERATORS[field["type"]].get(r["op"], "؟") if field else "؟"
        value = str(r["value"])[:60] + (f" و {str(r['value2'])[:60]}" if op == "بین" and r.get("value2") else "")
        lines.append(f"({field['label'] if field else '؟'} {op} {value})")
    head = "ترکیب: هر یک از شرط‌ها (یا)" if query["join"] == "or" else "ترکیب: همه‌ی شرط‌ها (و)"
    body = [line if i == 0 else f"{'یا' if query['join'] == 'or' else 'و'} {line}" for i, line in enumerate(lines)]
    out = ([head, *body] if rules else []) + ([f"وضعیت: {STATUS[status]['label']}"] if status else [])
    return "\n".join(out)


def query_to_params(query: dict[str, Any]) -> dict[str, str]:
    p = {"join": query["join"]}
    for i, r in enumerate(query["rules"][:MAX_RULES]):
        n = i + 1
        for k, v in (("f", r.get("field")), ("o", r.get("op")), ("v", r.get("value")), ("w", r.get("value2"))):
            if v is not None and str(v) != "":
                p[f"{k}{n}"] = str(v)
    if status_filter(query.get("status")):
        p["s"] = query["status"]
    return p
