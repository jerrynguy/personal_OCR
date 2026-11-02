"""Xuất hồ sơ ra Excel (.xlsx), CSV, và tách PDF thành từng tệp tài liệu.

File Excel gồm 4 sheet:
  - Phông, Hồ sơ: mỗi trường một dòng (Tên trường | Giá trị)
  - Tài liệu: mỗi tài liệu một dòng, cột theo đúng thứ tự Điều 4 TT05, sau đó là các cột
    bổ sung (nền xám); ô "Cần kiểm tra" có nội dung được tô vàng
  - Mục lục văn bản: STT | Số, ký hiệu | Ngày tháng | Tên loại và trích yếu nội dung | Tờ số | Ghi chú
"""

from __future__ import annotations

import csv
from pathlib import Path

import pymupdf
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.tt05 import fields

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
EXTRA_FILL = PatternFill("solid", fgColor="595959")
WARN_FILL = PatternFill("solid", fgColor="FFF2CC")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")

MUC_LUC_COLS = ["STT", "Số, ký hiệu VB", "Ngày tháng văn bản", "Tên loại và trích yếu nội dung", "Tờ số", "Ghi chú"]
WIDE = {"trich_yeu_noi_dung": 50, "co_quan_ban_hanh": 32, "tu_khoa": 30, "can_kiem_tra": 50, "ghi_chu": 25}


def so_ky_hieu(doc: dict) -> str:
    so, kh = doc.get("so_cua_tai_lieu", ""), doc.get("ky_hieu_cua_tai_lieu", "")
    return f"{so}/{kh}" if so and kh else so or kh


def ten_loai_trich_yeu(doc: dict) -> str:
    """'Quyết định' + 'Về việc thành lập...' -> 'Quyết định về việc thành lập...'."""
    loai, ty = doc.get("ten_loai_tai_lieu", ""), doc.get("trich_yeu_noi_dung", "")
    if loai and ty:
        if ty[:3].lower() != "v/v":
            ty = ty[0].lower() + ty[1:]
        return f"{loai} {ty}"
    return loai or ty


def muc_luc_rows(docs: list[dict]) -> list[list]:
    return [
        [
            i,
            so_ky_hieu(d),
            d.get("ngay_ban_hanh", ""),
            ten_loai_trich_yeu(d),
            d.get("to_so") or d.get("trang_pdf", ""),
            d.get("ghi_chu", ""),
        ]
        for i, d in enumerate(docs, 1)
    ]


def _header(ws, row: int, values: list[str], fills: list[PatternFill]) -> None:
    for col, (v, fill) in enumerate(zip(values, fills), 1):
        c = ws.cell(row=row, column=col, value=v)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.border = BORDER


def _key_value_sheet(ws, level: str, record: dict) -> None:
    _header(ws, 1, ["Tên trường", "Giá trị"], [HEADER_FILL, HEADER_FILL])
    for r, f in enumerate(fields(level), 2):
        ws.cell(row=r, column=1, value=f["label"]).border = BORDER
        c = ws.cell(row=r, column=2, value=record.get(f["key"], ""))
        c.border, c.alignment = BORDER, WRAP
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 70


def export_xlsx(result: dict, path: Path) -> Path:
    wb = Workbook()
    ws_phong = wb.active
    ws_phong.title = "Phông"
    _key_value_sheet(ws_phong, "phong", result.get("phong", {}))
    _key_value_sheet(wb.create_sheet("Hồ sơ"), "ho_so", result["ho_so"])
    ws_tl = wb.create_sheet("Tài liệu")
    wb.active = wb.sheetnames.index("Tài liệu")  # mở file là thấy ngay danh sách tài liệu

    cols = [("stt", "STT", HEADER_FILL)]
    cols += [(f["key"], f["label"], HEADER_FILL) for f in fields("tai_lieu")]
    cols += [(f["key"], f["label"], EXTRA_FILL) for f in fields("bo_sung")]
    _header(ws_tl, 1, [c[1] for c in cols], [c[2] for c in cols])
    for r, doc in enumerate(result["tai_lieu"], 2):
        for col, (key, _label, _fill) in enumerate(cols, 1):
            c = ws_tl.cell(row=r, column=col, value=doc.get(key, ""))
            c.border, c.alignment = BORDER, WRAP
            if key == "can_kiem_tra" and doc.get(key):
                c.fill = WARN_FILL
    for col, (key, _label, _fill) in enumerate(cols, 1):
        ws_tl.column_dimensions[get_column_letter(col)].width = WIDE.get(key, 16)
    ws_tl.row_dimensions[1].height = 60
    ws_tl.freeze_panes = "B2"
    ws_tl.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(len(result['tai_lieu']) + 1, 1)}"

    ws_ml = wb.create_sheet("Mục lục văn bản")
    _header(ws_ml, 1, MUC_LUC_COLS, [HEADER_FILL] * len(MUC_LUC_COLS))
    for r, row in enumerate(muc_luc_rows(result["tai_lieu"]), 2):
        for col, v in enumerate(row, 1):
            c = ws_ml.cell(row=r, column=col, value=v)
            c.border, c.alignment = BORDER, WRAP
    for col, w in enumerate([6, 20, 14, 60, 10, 25], 1):
        ws_ml.column_dimensions[get_column_letter(col)].width = w
    ws_ml.freeze_panes = "A2"

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def export_csv(result: dict, out_dir: Path, prefix: str) -> list[Path]:
    """Mỗi sheet một file CSV, mã hóa UTF-8 có BOM để Excel mở đúng tiếng Việt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tl_cols = ["stt"] + [f["key"] for f in fields("tai_lieu")] + [f["key"] for f in fields("bo_sung")]
    tl_labels = ["STT"] + [f["label"] for f in fields("tai_lieu")] + [f["label"] for f in fields("bo_sung")]
    tables = {
        "tai_lieu": [tl_labels] + [[d.get(k, "") for k in tl_cols] for d in result["tai_lieu"]],
        "ho_so": [["Tên trường", "Giá trị"]] + [[f["label"], result["ho_so"].get(f["key"], "")] for f in fields("ho_so")],
        "phong": [["Tên trường", "Giá trị"]]
        + [[f["label"], result.get("phong", {}).get(f["key"], "")] for f in fields("phong")],
        "muc_luc": [MUC_LUC_COLS] + muc_luc_rows(result["tai_lieu"]),
    }
    paths = []
    for name, rows in tables.items():
        p = out_dir / f"{prefix}_{name}.csv"
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(rows)
        paths.append(p)
    return paths


def split_pdf(pdf_path: Path, docs: list[dict], out_dir: Path) -> list[Path]:
    """Tách PDF hồ sơ thành từng tệp tài liệu (tên tệp = cột 'Tệp tin tài liệu')."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with pymupdf.open(pdf_path) as src:
        for d in docs:
            a, _, b = str(d["trang_pdf"]).partition("-")
            first, last = int(a) - 1, int(b or a) - 1
            out = pymupdf.open()
            out.insert_pdf(src, from_page=first, to_page=last)
            p = out_dir / d["tep_tin_tai_lieu"]
            out.save(p, deflate=True)
            out.close()
            paths.append(p)
    return paths
