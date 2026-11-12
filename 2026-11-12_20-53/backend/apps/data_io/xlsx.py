"""Minimal .xlsx writer (port of legacy src/lib/xlsx.js): one RTL sheet, every cell an inline string, so
nothing is evaluated as a formula and leading zeros are kept."""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_BAD = re.compile("[^\t\n\r -퟿-�\U00010000-\U0010ffff]")


def _xml(value: Any) -> str:
    s = _BAD.sub("", "" if value is None else str(value))
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _column(index: int) -> str:
    s, n = "", index + 1
    while n > 0:
        s = chr(65 + (n - 1) % 26) + s
        n = (n - 1) // 26
    return s


def _row(cells: list[Any], r: int, style: int) -> str:
    out = []
    for i, v in enumerate(cells):
        t = _xml(v)
        if t == "":
            continue
        s = f' s="{style}"' if style else ""
        out.append(f'<c r="{_column(i)}{r}" t="inlineStr"{s}><is><t xml:space="preserve">{t}</t></is></c>')
    return f'<row r="{r}">{"".join(out)}</row>'


STYLES = (
    f'{HEAD}<styleSheet xmlns="{NS}">'
    '<fonts count="2"><font><sz val="11"/><name val="Tahoma"/></font>'
    '<font><b/><sz val="11"/><name val="Tahoma"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
)


def to_xlsx(headers: list[str], rows: list[list[Any]], sheet_name: str = "Sheet1") -> bytes:
    sheet = "application/vnd.openxmlformats-officedocument.spreadsheetml"
    body = "".join([_row(headers, 1, 1), *(_row(row, i + 2, 0) for i, row in enumerate(rows))])
    sheet_xml = (
        f'{HEAD}<worksheet xmlns="{NS}"><sheetViews><sheetView rightToLeft="1" workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<cols><col min="1" max="{max(len(headers), 1)}" width="20" customWidth="1"/></cols>'
        f"<sheetData>{body}</sheetData></worksheet>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("[Content_Types].xml", (
            f'{HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/xl/workbook.xml" ContentType="{sheet}.sheet.main+xml"/>'
            f'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="{sheet}.worksheet+xml"/>'
            f'<Override PartName="/xl/styles.xml" ContentType="{sheet}.styles+xml"/></Types>'
        ))
        z.writestr("_rels/.rels", (
            f'{HEAD}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
        ))
        z.writestr("xl/workbook.xml", (
            f'{HEAD}<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>'
            f'<sheet name="{_xml(sheet_name)[:31]}" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ))
        z.writestr("xl/_rels/workbook.xml.rels", (
            f'{HEAD}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{REL}/styles" Target="styles.xml"/></Relationships>'
        ))
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        z.writestr("xl/styles.xml", STYLES)
    return buf.getvalue()
