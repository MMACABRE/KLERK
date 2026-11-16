"""Fills a DEV database with fake demo data in every section (never on a real clinic: refuses when patients exist
unless --force). Patients, custom boxes in the form layout, medications, documents (small fake files), visits over
the past month and the next two weeks, bills with services and stock items, payments, refunds, a credit move,
storage lots (one expired, one near expiry, one low), saved searches, SMS log rows of every status, audit rows."""

from __future__ import annotations

import random
from datetime import time, timedelta
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.billing import ops
from apps.core.audit import audit
from apps.core.files import ensure_patient_dir, patient_dir_exists
from apps.documents.models import Document
from apps.finance.models import Account, Catalog, PayMethod
from apps.patients.custom_boxes import create_custom_box, write_custom_values
from apps.patients.layouts import read_layout, save_layout
from apps.patients.models import Medication, Patient
from apps.patients.services import next_patient_code
from apps.search.models import SavedSearch
from apps.sms.models import SmsMessage
from apps.storage.services import stock_in
from apps.visits.models import Visit

FIRST_F = ["سارا", "مریم", "زهرا", "فاطمه", "نرگس", "لیلا", "مهسا", "نازنین", "الهام", "شیما", "پریسا", "رها"]
FIRST_M = ["علی", "محمد", "رضا", "حسین", "امیر", "مهدی", "سعید", "حامد", "کاوه", "بهرام", "آرش", "پویا"]
LAST = ["احمدی", "رضایی", "محمدی", "حسینی", "کریمی", "موسوی", "جعفری", "صادقی", "رحیمی", "نوری", "کاظمی",
        "عباسی", "قاسمی", "یوسفی", "مرادی", "شریفی", "طاهری", "زارعی"]
CITIES = ["تهران", "اصفهان", "شیراز", "مشهد", "تبریز", "اهواز", "کرج", "رشت"]
REASONS = ["کنترل فشار خون", "چکاپ سالانه", "سردرد مزمن", "درد کمر", "پیگیری آزمایش", "واکسن", "معاینه‌ی پوست"]
ALLERGY = ["پنی‌سیلین", "گرده‌ی گل", "صدف", "آسپرین"]
COND = ["دیابت", "فشار خون", "آسم", "میگرن"]
MEDS = [("متفورمین", "۵۰۰ میلی‌گرم", "روزی دو بار"), ("لوزارتان", "۲۵ میلی‌گرم", "روزی یک بار"),
        ("سالبوتامول", "دو پاف", "هنگام نیاز")]
SERVICES = [("ویزیت متخصص", 4_000_000), ("نوار قلب", 2_500_000), ("پانسمان", 1_200_000), ("تزریق", 600_000)]
ITEMS = [("سرنگ ۵ سی‌سی", 50_000, 10, 5), ("گاز استریل", 80_000, 20, 8), ("سرم نمکی", 450_000, 6, 3),
         ("دستکش لاتکس", 30_000, 50, 20)]

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj " \
      b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
def _png(w: int = 120, h: int = 80) -> bytes:
    """A small sage-coloured PNG, made with the standard library."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes((122, 150, 120)) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG = _png()


class Command(BaseCommand):
    help = "Fill a dev database with fake demo data in every section."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--patients", type=int, default=60)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args: Any, **o: Any) -> None:
        if Patient.objects.exists() and not o["force"]:
            raise CommandError("patients exist already; use --force on a dev database only")
        rnd = random.Random(1404)  # nosec B311 - fixed-seed fake demo data, not security
        admin = User.objects.filter(is_owner=True).first() or User.objects.first()
        if admin is None:
            raise CommandError("create a user first")
        today = timezone.localdate()

        # Custom boxes, shown on the form (a new card at the end).
        boxes = [
            create_custom_box("choice", "شیفت مراجعه", "صبح,عصر,شب", admin.pk),
            create_custom_box("yes_no", "سیگاری", None, admin.pk),
            create_custom_box("number", "قند ناشتا", None, admin.pk),
            create_custom_box("date", "تاریخ آخرین واکسن", None, admin.pk),
        ]
        layout = read_layout("patient_form")
        layout["cards"].append({
            "id": "card:1", "label": "اطلاعات تکمیلی", "boxes": [{"id": f"c:{b.pk}"} for b in boxes],
        })
        save_layout("patient_form", layout, admin.pk)

        # Catalog and storage.
        visit_service = Catalog.objects.filter(kind="service", fixed=True).first()
        if visit_service:
            visit_service.sale_price = 3_000_000
            visit_service.save()
        services = [Catalog.objects.create(kind="service", name=n, sale_price=p) for n, p in SERVICES]
        if visit_service:
            services.insert(0, visit_service)
        items = []
        for name, price, warn, crit in ITEMS:
            it = Catalog.objects.create(kind="item", name=name, sale_price=price, purchase_cost=price // 2,
                                        low_warn=Decimal(warn), low_crit=Decimal(crit))
            items.append(it)
            stock_in(it.pk, Decimal("200"), today - timedelta(days=40), today + timedelta(days=300), price // 2, admin)
        # one expired lot, one lot near expiry, one low item
        stock_in(items[2].pk, Decimal("4"), today - timedelta(days=60), today - timedelta(days=3), 200_000, admin)
        stock_in(items[1].pk, Decimal("15"), today - timedelta(days=20), today + timedelta(days=7), 40_000, admin)
        low = Catalog.objects.create(
            kind="item", name="ماسک N95", sale_price=150_000, low_warn=Decimal(10), low_crit=Decimal(5),
        )
        stock_in(low.pk, Decimal("3"), today - timedelta(days=10), None, 70_000, admin)
        items.append(low)

        methods = list(PayMethod.objects.filter(active=True).order_by("id"))
        accounts = list(Account.objects.filter(active=True).order_by("id"))

        statuses = ["active"] * 7 + ["pending", "critical", "archived"]
        patients: list[Patient] = []
        for n in range(o["patients"]):
            sex = rnd.choice(["female", "male"])
            first = rnd.choice(FIRST_F if sex == "female" else FIRST_M)
            code = next_patient_code(folder_exists=patient_dir_exists)
            p = Patient.objects.create(
                code=code, first_name=first, last_name=rnd.choice(LAST), father_name=rnd.choice(FIRST_M), sex=sex,
                national_id=f"{rnd.randint(10**9, 10**10 - 1)}",
                birth_date=today - timedelta(days=rnd.randint(18 * 365, 80 * 365)),
                phone=f"0912{rnd.randint(1000000, 9999999)}", city=rnd.choice(CITIES), status=rnd.choice(statuses),
                visit_reason=rnd.choice(REASONS), referral=rnd.choice(["دکتر نوری", "اینستاگرام", "دوستان", None]),
                blood_type=rnd.choice(["A+", "B+", "O+", "AB-", None]), allergies=rnd.choice(ALLERGY + [None, None]),
                conditions=rnd.choice(COND + [None]),
                height_cm=Decimal(rnd.randint(150, 190)), weight_kg=Decimal(rnd.randint(50, 100)),
                blood_pressure=rnd.choice(["120/80", "135/85", "110/70"]), sms_optout=n % 13 == 0, updated_by=admin,
                medical_notes="بیمار برای پیگیری دو هفته بعد مراجعه کند." if n % 4 == 0 else None,
            )
            ensure_patient_dir(code)
            audit(admin.pk, "patient_create", p.pk, code)
            patients.append(p)
            with transaction.atomic():
                write_custom_values(p.pk, {
                    boxes[0].pk: str(rnd.randint(1, 3)), boxes[1].pk: rnd.choice(["0", "1"]),
                    boxes[2].pk: str(rnd.randint(80, 140)),
                    boxes[3].pk: (today - timedelta(days=rnd.randint(30, 700))).isoformat(),
                })
            if n % 3 == 0:
                med = MEDS[n % len(MEDS)]
                Medication.objects.create(patient=p, name=med[0], dosage=med[1], frequency=med[2])
            if n % 2 == 0:
                folder = ensure_patient_dir(code)
                (folder / "azmayesh-khoon.pdf").write_bytes(PDF)
                Document.objects.create(patient=p, filename="azmayesh-khoon.pdf", category="lab", title="آزمایش خون",
                                        doc_date=today - timedelta(days=rnd.randint(1, 90)), uploaded_by=admin)
                (folder / "scan.png").write_bytes(PNG)  # unclassified (no row), as if copied by hand

        # Visits: one doctor, so 30-minute slots that never overlap.
        live = [p for p in patients if p.status != "archived"]
        slot = 0
        visits: list[Visit] = []
        for day_off in range(-30, 15):
            d = today + timedelta(days=day_off)
            for k in range(rnd.randint(1, 4)):
                p = live[slot % len(live)]
                slot += 1
                hour = 9 + k
                status = "done" if day_off < 0 else "scheduled"
                if day_off < 0 and rnd.random() < 0.1:
                    status = "cancelled"
                v = Visit.objects.create(
                    patient=p, visit_date=d, visit_time=time(hour, 0), duration_min=rnd.choice([15, 20, 30]),
                    reason=rnd.choice(REASONS), status=status, created_by=admin,
                    doctor_note="معاینه انجام شد؛ داروها ادامه یابد." if status == "done" else None,
                )
                visits.append(v)
                audit(admin.pk, "visit_add", p.pk)

        # Bills and payments on past and today's visits.
        for v in visits:
            if v.status == "cancelled" or v.visit_date > today:
                continue
            ops.add_line(v.pk, services[0].pk, Decimal("1"), admin)
            if rnd.random() < 0.5:
                ops.add_line(v.pk, rnd.choice(services[1:]).pk, Decimal("1"), admin)
            if rnd.random() < 0.6:
                ops.add_line(v.pk, rnd.choice(items[:4]).pk, Decimal(rnd.choice(["1", "2", "0.5"])), admin)
            owed = ops.bill_for(Visit.objects.get(pk=v.pk))["owed"]
            r = rnd.random()
            m = rnd.choice(methods)
            if r < 0.6:
                ops.record_payment(v.pk, owed, v.visit_date, m.pk, m.default_account_id or accounts[0].pk, None, admin)
            elif r < 0.8:
                ops.record_payment(
                    v.pk, owed // 2 // 10 * 10, v.visit_date, m.pk, m.default_account_id or accounts[0].pk,
                    "قسط اول", admin,
                )
            elif r < 0.9:
                ops.record_payment(
                    v.pk, owed + 500_000, v.visit_date, m.pk, m.default_account_id or accounts[0].pk,
                    "بیش‌پرداخت", admin,
                )
        # One refund and one credit move from overpaid visits; a prepayment on a future visit.
        over = [v for v in visits if ops.bill_for(Visit.objects.get(pk=v.pk))["credit"] > 0]
        if over:
            ops.record_payment(over[0].pk, 300_000, today, methods[0].pk, accounts[0].pk, None, admin, kind="refund")
        if len(over) > 1:
            target = (
                Visit.objects.filter(patient_id=over[1].patient_id)
                .exclude(pk=over[1].pk).exclude(status="cancelled").first()
            )
            if target:
                ops.move_credit(over[1].pk, target.pk, 200_000, today, admin)
        future = [v for v in visits if v.visit_date > today]
        if future:
            ops.record_payment(future[0].pk, 1_000_000, today, methods[0].pk, accounts[0].pk, "پیش‌پرداخت", admin)

        # Saved searches.
        SavedSearch.objects.create(
            user=admin, name="بیماران بحرانی",
            query_json={"join": "and", "status": "critical", "rules": []},
        )
        SavedSearch.objects.create(
            user=admin, name="دیابتی‌های تهران",
            query_json={"join": "and", "status": "", "rules": [
                {"field": "conditions", "op": "contains", "value": "دیابت", "value2": ""},
                {"field": "city", "op": "contains", "value": "تهران", "value2": ""},
            ]},
        )

        # SMS log rows of every status (the worker does not send: SMS stays off and no key is stored).
        now_ms = int(timezone.now().timestamp() * 1000)
        for i, st in enumerate(["sent", "sent", "failed", "pending", "skipped", "cancelled"]):
            p = live[i]
            SmsMessage.objects.create(kind=["custom", "bulk", "custom", "bulk", "custom", "custom"][i], patient=p,
                                      phone=p.phone, body=f"{p.first_name} عزیز، نتیجه‌ی آزمایش شما آماده است.",
                                      status=st, reason="اعتبار کافی نیست." if st == "failed" else None,
                                      due_at=now_ms - i * 3_600_000, created_by=admin,
                                      sent_at=timezone.now() if st == "sent" else None)
        audit(admin.pk, "login")
        self.stdout.write(f"demo data: {len(patients)} patients, {len(visits)} visits, {len(items)} stock items")
