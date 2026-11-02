"""Luật trích xuất các trường có thể thức cố định (Nghị định 30/2020/NĐ-CP, Phụ lục I).

Không dùng LLM cho các trường này: nhanh, ổn định, và giữ NGUYÊN số/ký hiệu gốc.
Mọi so khớp đều làm trên văn bản đã BỎ DẤU để chịu được lỗi dấu của OCR.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from app.ocr import OcrLine, OcrPage, group_rows

HEADER_ZONE = 0.35  # phần trên cùng của trang chứa quốc hiệu, cơ quan, số, ngày

# Tên loại văn bản (NĐ 30 Phụ lục III + văn bản QPPL + một số loại thường gặp trong hồ sơ).
TEN_LOAI = [
    "Thông tư liên tịch", "Nghị quyết liên tịch", "Nghị quyết", "Nghị định", "Thông tư",
    "Quyết định", "Chỉ thị", "Quy chế", "Quy định", "Thông cáo", "Thông báo", "Hướng dẫn",
    "Chương trình", "Kế hoạch", "Phương án", "Đề án", "Dự án", "Báo cáo", "Biên bản",
    "Tờ trình", "Hợp đồng", "Công văn", "Công điện", "Bản ghi nhớ", "Bản thỏa thuận",
    "Giấy ủy quyền", "Giấy mời", "Giấy giới thiệu", "Giấy nghỉ phép", "Phiếu gửi",
    "Phiếu chuyển", "Phiếu báo", "Thư công", "Luật", "Pháp lệnh", "Lệnh", "Sắc lệnh",
    "Bằng khen", "Giấy khen", "Giấy chứng nhận", "Đơn", "Tờ khai", "Danh sách", "Bản kê",
]

DO_MAT = {"MAT": "Mật", "TOI MAT": "Tối mật", "TUYET MAT": "Tuyệt mật"}
DO_KHAN = {"KHAN": "Khẩn", "THUONG KHAN": "Thượng khẩn", "HOA TOC": "Hỏa tốc"}


def strip_accents(text: str) -> str:
    """'Số: 125/QĐ-UBND' -> 'So: 125/QD-UBND'."""
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def key_text(text: str) -> str:
    """Bỏ dấu, viết hoa, bỏ dấu câu, gộp khoảng trắng — để so khớp."""
    t = re.sub(r"[^A-Z0-9/ ]", " ", strip_accents(text).upper())
    return re.sub(r"\s+", " ", t).strip()


TEN_LOAI_KEYS = sorted(((key_text(t), t) for t in TEN_LOAI), key=lambda x: -len(x[0]))

# "Số: 125/QĐ-UBND", "Số 12/2025/NĐ-CP", OCR có thể đọc "Sô:", "S6:"...
SO_RE = re.compile(r"^\s*S[^\s\d]?\s*[:;.]?\s*(\d{1,6}[a-zA-Z]?)\s*/\s*([\w./-]+)", re.UNICODE)
DATE_RE = re.compile(r"ngay\s*(\d{1,2})\s*thang\s*(\d{1,2})\s*nam\s*(\d{4})", re.I)


@dataclass
class SoKyHieu:
    so: str
    ky_hieu: str
    line: OcrLine | None = None

    @property
    def full(self) -> str:
        return f"{self.so}/{self.ky_hieu}"


def parse_so_ky_hieu(text: str) -> SoKyHieu | None:
    t = re.sub(r"\s*([/-])\s*", r"\1", text.strip())
    m = SO_RE.match(t)
    if not m:
        return None
    ky_hieu = m.group(2).strip(".-/")
    return SoKyHieu(m.group(1), ky_hieu) if ky_hieu else None


def parse_date(text: str) -> str | None:
    m = DATE_RE.search(strip_accents(text))
    if not m:
        return None
    d, mth, y = (int(g) for g in m.groups())
    try:
        date(y, mth, d)
    except ValueError:
        return None
    return f"{d:02d}/{mth:02d}/{y}"


def header_lines(page: OcrPage, zone: float = HEADER_ZONE) -> list[OcrLine]:
    return [l for l in page.lines if l.cy < page.height * zone]


def has_quoc_hieu(page: OcrPage) -> bool:
    keys_ = " ".join(key_text(l.text) for l in header_lines(page, 0.3))
    return "CONG HOA" in keys_ or "DOC LAP" in keys_


def find_so_ky_hieu(page: OcrPage) -> SoKyHieu | None:
    for line in sorted(header_lines(page), key=lambda l: l.cy):
        skh = parse_so_ky_hieu(line.text)
        if skh:
            skh.line = line
            return skh
    return None


def find_ngay(page: OcrPage) -> str | None:
    """Ngày ở dòng 'Địa danh, ngày ... tháng ... năm ...' trong vùng đầu trang.

    Ưu tiên dòng có dấu phẩy trước chữ 'ngày' để không lấy nhầm ngày trong 'Căn cứ ...'.
    """
    candidates = []
    for line in sorted(header_lines(page), key=lambda l: l.cy):
        d = parse_date(line.text)
        if d:
            has_comma = bool(re.search(r",\s*ng", strip_accents(line.text), re.I))
            candidates.append((not has_comma, line.cy, d))
    return min(candidates)[2] if candidates else None


def find_ten_loai(page: OcrPage) -> str | None:
    """Dòng VIẾT HOA đầu tiên (dưới phần quốc hiệu) trùng tên loại văn bản.

    Không có tên loại mà có 'V/v' -> Công văn (NĐ 30).
    """
    for row in group_rows([l for l in page.lines if l.cy < page.height * 0.6]):
        text = " ".join(l.text for l in row)
        letters = [c for c in text if c.isalpha()]
        if not letters or "".join(letters) != "".join(letters).upper():
            continue  # chỉ xét dòng viết hoa toàn bộ
        k = key_text(text)
        if "CONG HOA" in k or "DOC LAP" in k:
            continue
        for key, name in TEN_LOAI_KEYS:
            if k == key or k.startswith(key + " "):
                return name
    for line in header_lines(page, 0.45):
        if key_text(line.text).startswith("V/V"):
            return "Công văn"
    return None


def find_flag(page: OcrPage, table: dict[str, str]) -> str | None:
    """Dấu độ mật / độ khẩn: một dòng đứng riêng, chỉ gồm chữ 'MẬT', 'KHẨN'..."""
    for line in page.lines:
        k = key_text(line.text)
        if k in table:
            return table[k]
    return None


def find_co_quan_raw(page: OcrPage, skh: SoKyHieu | None) -> str:
    """Các dòng góc trên bên trái, phía trên dòng 'Số:' — tên cơ quan ban hành (chưa chuẩn hóa)."""
    limit = skh.line.box[1] if skh and skh.line else page.height * 0.2
    lines = [
        l for l in header_lines(page)
        # loại dòng 'Số: ...' bằng cách thử phân tích số/ký hiệu — KHÔNG so chữ "SO" vì
        # bỏ dấu thì "SỞ NỘI VỤ" cũng thành "SO NOI VU".
        if l.box[2] < page.width * 0.55 and l.cy < limit and parse_so_ky_hieu(l.text) is None
    ]
    return " ".join(l.text for l in sorted(lines, key=lambda l: l.cy))


def find_to_so(page: OcrPage) -> str | None:
    """Tờ số: con số đứng riêng ở góc trên bên phải (do người lập hồ sơ đánh)."""
    for l in page.lines:
        if re.fullmatch(r"\d{1,4}", l.text.strip()) and l.cy < page.height * 0.1 and l.cx > page.width * 0.7:
            return l.text.strip()
    return None
