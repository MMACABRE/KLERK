"""Every URL. API under /api/v1 (JSON), printable documents under /print/ (HTML). The gate
(apps.core.gate) decides access for every one of them; a path with no rule there is refused."""

from django.urls import path

from apps.accounts import views as acc
from apps.billing import views as bill
from apps.core.http import route
from apps.dashboard import views as dash
from apps.data_io import views as data
from apps.diagnostics import views as diag
from apps.documents import views as docs
from apps.finance import views as fin
from apps.ops.views import health
from apps.patients import views as pat
from apps.printing import views as prn
from apps.search import views as srch
from apps.sms import views as sms
from apps.storage import views as sto
from apps.visits import views as vis

P = "<str:code>"

api = [
    # session and shell
    path("auth/csrf", route(GET=acc.csrf)),
    path("auth/login", route(POST=acc.login)),
    path("auth/logout", route(POST=acc.logout)),
    path("me", route(GET=acc.me)),
    path("me/theme", route(PUT=acc.theme)),
    path("me/password", route(POST=acc.change_password)),
    path("public/app-config", route(GET=acc.app_config)),
    path("public/contact", route(GET=acc.contact)),
    # dashboard
    path("dashboard", dash.dashboard_view),
    path("dashboard/layout", dash.layout_view),
    path("dashboard/layout/undo", dash.undo_view),
    path("dashboard/layout/reset", dash.reset_view),
    # patient form layout and custom boxes (before patients/<code>)
    path("patients/layout", pat.layout_view),
    path("patients/layout/undo", route(POST=pat.layout_undo_for("patient_form"))),
    path("patients/layout/reset", route(POST=pat.layout_reset_for("patient_form"))),
    path("patients/layout/boxes", route(POST=pat.create_box)),
    path("patients/layout/boxes/<str:box_id>", route(GET=pat.box_detail, DELETE=pat.box_delete)),
    path("patients/layout/boxes/<str:box_id>/choices", route(POST=pat.box_choices)),
    # patients
    path("patients", pat.patients_view),
    path("patients/suggestions", route(GET=pat.suggestions)),
    path("patients/form", route(GET=pat.form_data)),
    path(f"patients/{P}", pat.patient_view),
    path(f"patients/{P}/change-code", route(POST=pat.change_code)),
    path(f"patients/{P}/archive", route(POST=pat.archive)),
    path(f"patients/{P}/unarchive", route(POST=pat.unarchive)),
    path(f"patients/{P}/delete-check", route(GET=pat.delete_check)),
    path(f"patients/{P}/medications", route(POST=pat.add_medication)),
    path(f"patients/{P}/medications/<str:mid>", route(DELETE=pat.remove_medication)),
    path(f"patients/{P}/history", route(GET=pat.history)),
    path(f"patients/{P}/discount", route(PUT=pat.set_discount)),
    # documents and photo
    path(f"patients/{P}/documents", docs.documents_view),
    path(f"patients/{P}/documents/classify", route(POST=docs.classify)),
    path(f"patients/{P}/files/<str:name>", docs.file_view),
    path(f"patients/{P}/photo", docs.photo_view),
    # visits and bill
    path(f"patients/{P}/visits", route(POST=vis.create)),
    path("visits", vis.visits_view),
    path("visits/day", route(GET=vis.day)),
    path("visits/patient-search", route(GET=vis.patient_search)),
    path("visits/<str:vid>", vis.visit_view),
    path("visits/<str:vid>/status", route(POST=vis.set_status)),
    path("visits/<str:vid>/note", route(PUT=vis.note)),
    path("visits/<str:vid>/lines", bill.lines_view),
    path("visits/<str:vid>/lines/<str:lid>", bill.line_view),
    path("visits/<str:vid>/lines/<str:lid>/discount", bill.line_discount_view),
    path("visits/<str:vid>/lines/<str:lid>/price", bill.line_price_view),
    path("visits/<str:vid>/discount", bill.visit_discount_view),
    path("visits/<str:vid>/payments", bill.payments_view),
    path("visits/<str:vid>/payments/<str:pid>", bill.payment_view),
    path("visits/<str:vid>/refund", bill.refund_view),
    path("visits/<str:vid>/move-credit", bill.move_view),
    # finance
    path("finance/overview", route(GET=fin.overview)),
    path("finance/payments", route(GET=fin.payments)),
    path("finance/pay", route(GET=fin.pay)),
    path("finance/settings", fin.settings_view),
    path("finance/catalog", fin.catalog_view),
    path("finance/catalog/<str:cid>", fin.catalog_item_view),
    path("finance/methods", fin.methods_view),
    path("finance/methods/<str:rid>", fin.method_view),
    path("finance/accounts", fin.accounts_view),
    path("finance/accounts/<str:rid>", fin.account_view),
    # storage
    path("storage/items", sto.items_view),
    path("storage/items/<str:iid>", sto.item_view),
    path("storage/items/<str:iid>/stock-in", route(POST=sto.stock_in)),
    path("storage/lots/<str:lid>/count", route(POST=sto.count)),
    path("storage/lots/<str:lid>/waste", route(POST=sto.waste)),
    path("storage/moves/<str:mid>", route(DELETE=sto.delete_move)),
    # search
    path("search", route(GET=srch.search)),
    path("search/fields", route(GET=srch.fields)),
    path("search/export.csv", route(GET=srch.export_csv)),
    path("search/export.xlsx", route(GET=srch.export_xlsx)),
    path("search/saved", srch.saved_view),
    path("search/saved/<str:sid>", srch.saved_item_view),
    # data
    path("data", route(GET=data.page)),
    path("data/template.csv", route(GET=data.template)),
    path("data/imports", route(POST=data.import_preview)),
    path("data/imports/jobs/<str:job_id>", route(GET=data.import_job)),
    path("data/imports/jobs/<str:job_id>/resume", route(POST=data.import_resume)),
    path("data/imports/<str:token>", route(DELETE=data.import_cancel)),
    path("data/imports/<str:token>/confirm", route(POST=data.import_confirm)),
    path("data/exports/patients.csv", route(POST=data.export_csv)),
    path("data/exports/patients.xlsx", route(POST=data.export_xlsx)),
    path("data/exports/full.zip", route(POST=data.export_full)),
    # users, audit, wipe
    path("users", acc.users_view),
    path("users/<str:uid>", acc.user_view),
    path("users/<str:uid>/password", acc.user_password_view),
    path("users/<str:uid>/activate", acc.user_activate_view),
    path("users/<str:uid>/deactivate", acc.user_deactivate_view),
    path("users/<str:uid>/permissions", acc.user_perms_view),
    path("audit", route(GET=acc.audit_log)),
    path("admin/wipe", data.wipe_view),
    # sms
    path("sms", route(GET=sms.log_view)),
    path("sms/settings", sms.settings_view),
    path("sms/key", sms.key_view),
    # Diagnostics feed (ADR-0013): the four reads take the token (gate.DIAG_TOKEN), never a session.
    path("diagnostics/specs", diag.specs_view),
    path("diagnostics/stats", diag.stats_view),
    path("diagnostics/errors", diag.errors_view),
    path("diagnostics/logs", diag.logs_view),
    path("diagnostics/client-errors", diag.client_errors_view),
    path("diagnostics/token", diag.token_view),
    path("sms/test", route(POST=sms.test)),
    path("sms/bulk", route(GET=sms.bulk_page)),
    path("sms/bulk/preview", route(POST=sms.bulk_preview)),
    path("sms/bulk/confirm", route(POST=sms.bulk_confirm)),
    path("sms/<str:mid>/retry", route(POST=sms.retry)),
    path(f"patients/{P}/sms", sms.patient_view),
]

urlpatterns = [
    path("health", health, name="health"),
    *[path(f"api/v1/{p.pattern}", p.callback) for p in api],
    path("print/finance/day", prn.finance_day),
    path("print/visits/day", prn.visits_day),
    path("print/visits/report", prn.visits_report),
    path("print/stock/usage", prn.stock_usage),
    path("print/stock/day", prn.stock_day),
    path("print/stock/inventory", prn.stock_inventory),
    path("print/visits/<str:vid>/bill", prn.bill),
    path(f"print/patients/{P}", prn.patient),
]

handler404 = "apps.core.http.handler404"
handler500 = "apps.core.http.handler500"
