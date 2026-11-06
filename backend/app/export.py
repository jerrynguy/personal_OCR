"""Xuất dữ liệu TÀI LIỆU (Điều 4 khoản 1 điểm c TT 05/2025/TT-BNV) ra Excel / CSV,
và tách PDF hồ sơ thành từng tệp tài liệu.

File xuất CHỈ gồm 23 cột của điểm c, đúng thứ tự và tên trong Thông tư; mỗi văn bản một dòng.
(Thông tin phông / hồ sơ và các cột phụ để soát chỉ dùng trong app, không xuất ra.)
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
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
WIDE = {"trich_yeu_noi_dung": 50, "co_quan_ban_hanh": 32, "tu_khoa": 30, "ghi_chu": 25, "ma_luu_tru_tai_lieu": 22}


def columns() -> list[tuple[str, str]]:
    """[(key, tên cột theo Thông tư)] — đúng 23 trường điểm c, đúng thứ tự."""
    return [(f["key"], f["label"]) for f in fields("tai_lieu")]


def rows(docs: list[dict]) -> list[list]:
    cols = columns()
    return [[d.get(k, "") for k, _ in cols] for d in docs]


def export_xlsx(result: dict, path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Tài liệu"
    cols = columns()
    for c, (_key, label) in enumerate(cols, 1):
        cell = ws.cell(row=1, column=c, value=label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = BORDER
    for r, values in enumerate(rows(result["tai_lieu"]), 2):
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.border, cell.alignment = BORDER, WRAP
    for c, (key, _label) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(c)].width = WIDE.get(key, 16)
    ws.row_dimensions[1].height = 60
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(len(result['tai_lieu']) + 1, 1)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def export_csv(result: dict, path: Path) -> Path:
    """Một file CSV, mã hóa UTF-8 có BOM để Excel mở đúng tiếng Việt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([label for _k, label in columns()])
        w.writerows(rows(result["tai_lieu"]))
    return path


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
