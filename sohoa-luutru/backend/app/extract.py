"""Trích xuất trường dữ liệu TT05 cho từng văn bản: luật trước, LLM sau, rồi gộp + kiểm tra.

- Luật: tên loại, số, ký hiệu, ngày ban hành, độ mật, độ khẩn, tờ số.
- LLM: cơ quan ban hành (chuẩn hóa viết hoa), trích yếu, từ khóa, ngôn ngữ, người ký;
  đồng thời trả lại số/ký hiệu/ngày/tên loại để ĐỐI CHIẾU — luật và LLM khác nhau thì
  ghi vào cột "Cần kiểm tra" để người dùng soát.
"""

from __future__ import annotations

import re
from collections import Counter

from app.llm import LlmClient
from app.ocr import lines_to_text
from app.rules import (
    DO_KHAN,
    DO_MAT,
    find_co_quan_raw,
    find_flag,
    find_ngay,
    find_so_ky_hieu,
    find_ten_loai,
    find_to_so,
    key_text,
    parse_so_ky_hieu,
)
from app.segment import Document
from app.tt05 import defaults, inherited_keys

LOW_OCR = 0.80
FIRST_PAGE_CHARS = 2500  # đủ phần đầu văn bản (cơ quan, số, ngày, tên loại, trích yếu)
LAST_PAGE_CHARS = 1000  # phần cuối trang cuối (người ký)

NGON_NGU = ["Tiếng Việt", "Tiếng Anh", "Tiếng Pháp", "Tiếng Trung", "Tiếng Nga", "Khác"]

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "ten_loai_tai_lieu": {"type": "string"},
        "so_ky_hieu": {"type": "string"},
        "ngay_ban_hanh": {"type": "string", "pattern": "^([0-9]{2}/[0-9]{2}/[0-9]{4})?$"},
        "co_quan_ban_hanh": {"type": "string"},
        "trich_yeu_noi_dung": {"type": "string"},
        "tu_khoa": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "ngon_ngu": {"type": "string", "enum": NGON_NGU},
        "nguoi_ky": {"type": "string"},
        "chuc_vu_nguoi_ky": {"type": "string"},
    },
    "required": [
        "ten_loai_tai_lieu", "so_ky_hieu", "ngay_ban_hanh", "co_quan_ban_hanh",
        "trich_yeu_noi_dung", "tu_khoa", "ngon_ngu", "nguoi_ky", "chuc_vu_nguoi_ky",
    ],
    "additionalProperties": False,
}

LLM_SYSTEM = (
    "Bạn là chuyên viên lưu trữ, trích xuất thông tin văn bản hành chính Việt Nam theo thể thức "
    "Nghị định 30/2020/NĐ-CP và Thông tư 05/2025/TT-BNV. Đầu vào là văn bản OCR (có thể sai chính "
    "tả nhẹ; '|' ngăn cách 2 cột trên cùng một dòng). Quy tắc:\n"
    "- ten_loai_tai_lieu: tên loại văn bản, viết hoa chữ cái đầu (Quyết định, Công văn, Tờ trình...). "
    "Không có tên loại mà có 'V/v' dưới số ký hiệu thì là 'Công văn'.\n"
    "- so_ky_hieu: giữ NGUYÊN số và ký hiệu sau chữ 'Số:', không thêm bớt, không diễn giải.\n"
    "- ngay_ban_hanh: ngày ở dòng 'địa danh, ngày ... tháng ... năm ...', dạng dd/mm/yyyy.\n"
    "- co_quan_ban_hanh: cơ quan ở góc trên bên trái, ghép các dòng, viết hoa chữ cái đầu và "
    "tên riêng theo quy tắc chính tả (ví dụ: Ủy ban nhân dân tỉnh An Bình).\n"
    "- trich_yeu_noi_dung: trích yếu ngay dưới tên loại (hoặc dòng 'V/v'), sửa lỗi chính tả, "
    "viết đầy đủ từ viết tắt (giữ nguyên 'V/v').\n"
    "- tu_khoa: 3–5 từ khóa ngắn về nội dung chính.\n"
    "- nguoi_ky, chuc_vu_nguoi_ky: ở phần chữ ký cuối văn bản.\n"
    "Không đoán: trường nào không có trong văn bản thì để chuỗi rỗng."
)


def document_text(doc: Document) -> str:
    text = lines_to_text(doc.pages[0].lines)[:FIRST_PAGE_CHARS]
    if len(doc.pages) > 1:
        last = lines_to_text(doc.pages[-1].lines)
        text += "\n--- phần cuối văn bản (trang cuối) ---\n" + last[-LAST_PAGE_CHARS:]
    return text


def rule_fields(doc: Document) -> dict:
    first = doc.pages[0]
    skh = find_so_ky_hieu(first)
    to_so = [t for t in (find_to_so(p) for p in doc.pages) if t]
    return {
        "ten_loai_tai_lieu": find_ten_loai(first) or "",
        "so_cua_tai_lieu": skh.so if skh else "",
        "ky_hieu_cua_tai_lieu": skh.ky_hieu if skh else "",
        "ngay_ban_hanh": find_ngay(first) or "",
        "do_mat": find_flag(first, DO_MAT) or "",
        "do_khan": find_flag(first, DO_KHAN) or "",
        "to_so": (to_so[0] if len(to_so) == 1 else f"{to_so[0]}-{to_so[-1]}") if to_so else "",
        "_co_quan_tho": find_co_quan_raw(first, skh),
    }


def _same(a: str, b: str) -> bool:
    return key_text(a) == key_text(b)


def merge(rule: dict, llm: dict | None) -> tuple[dict, dict, list[str]]:
    """Gộp kết quả luật + LLM. Trả về (giá trị, nguồn từng trường, cảnh báo)."""
    out, src, warn = {}, {}, []
    llm = llm or {}

    def pick(key: str, rule_val: str, llm_val: str, label: str) -> None:
        if rule_val:
            out[key], src[key] = rule_val, "luật"
            if llm_val and not _same(rule_val, llm_val):
                warn.append(f"{label}: luật đọc '{rule_val}', LLM đọc '{llm_val}'")
        elif llm_val:
            out[key], src[key] = llm_val, "LLM"
        else:
            out[key], src[key] = "", ""
            warn.append(f"Không tìm thấy {label.lower()}")

    llm_skh = parse_so_ky_hieu("Số: " + llm.get("so_ky_hieu", "")) if llm.get("so_ky_hieu") else None
    pick("ten_loai_tai_lieu", rule["ten_loai_tai_lieu"], llm.get("ten_loai_tai_lieu", ""), "Tên loại")
    pick("so_cua_tai_lieu", rule["so_cua_tai_lieu"], llm_skh.so if llm_skh else "", "Số")
    pick("ky_hieu_cua_tai_lieu", rule["ky_hieu_cua_tai_lieu"], llm_skh.ky_hieu if llm_skh else "", "Ký hiệu")
    pick("ngay_ban_hanh", rule["ngay_ban_hanh"], llm.get("ngay_ban_hanh", ""), "Ngày ban hành")

    for key, llm_key in [
        ("co_quan_ban_hanh", "co_quan_ban_hanh"),
        ("trich_yeu_noi_dung", "trich_yeu_noi_dung"),
        ("ngon_ngu", "ngon_ngu"),
        ("nguoi_ky", "nguoi_ky"),
        ("chuc_vu_nguoi_ky", "chuc_vu_nguoi_ky"),
    ]:
        out[key], src[key] = llm.get(llm_key, ""), "LLM" if llm.get(llm_key) else ""
    if not out["co_quan_ban_hanh"] and rule["_co_quan_tho"]:
        out["co_quan_ban_hanh"], src["co_quan_ban_hanh"] = rule["_co_quan_tho"], "luật (chưa chuẩn hóa)"
    if not out["trich_yeu_noi_dung"]:
        warn.append("Không có trích yếu nội dung")
    out["tu_khoa"] = "; ".join(k.strip() for k in llm.get("tu_khoa", []) if k.strip())
    src["tu_khoa"] = "LLM" if out["tu_khoa"] else ""

    for key in ("do_mat", "do_khan", "to_so"):
        out[key], src[key] = rule[key], "luật" if rule[key] else ""
    return out, src, warn


def extract_document(doc: Document, llm: LlmClient | None, ho_so: dict, stt: int) -> dict:
    """Bản ghi tài liệu đầy đủ theo TT05 (+ cột bổ sung, + '_nguon' và '_canh_bao')."""
    rule = rule_fields(doc)
    llm_out, timings = None, {}
    if llm is not None:
        llm_out, timings = llm.extract_json(
            LLM_SYSTEM, f"Văn bản OCR:\n\n{document_text(doc)}", LLM_SCHEMA, max_tokens=2048
        )
    values, sources, warnings = merge(rule, llm_out)

    rec = defaults("tai_lieu")
    for key in inherited_keys():
        rec[key] = ho_so.get(key, "") or rec.get(key, "")
    rec.update({k: v for k, v in values.items() if k in rec or k in ("do_mat", "do_khan", "to_so")})
    if not rec.get("ngon_ngu"):
        rec["ngon_ngu"] = "Tiếng Việt"

    ma_ho_so = ho_so.get("ma_ho_so", "")
    rec["ma_luu_tru_tai_lieu"] = f"{ma_ho_so}.{stt:02d}" if ma_ho_so else f"{stt:02d}"
    rec["so_luong_trang"] = len(doc.pages)
    rec["so_luong_to"] = len(doc.pages)
    rec["tep_tin_tai_lieu"] = f"{rec['ma_luu_tru_tai_lieu']}.pdf"

    scores = [l.score for p in doc.pages for l in p.lines]
    avg = sum(scores) / len(scores) if scores else 0.0
    if avg < LOW_OCR:
        warnings.append(f"Chất lượng OCR thấp ({avg:.2f})")
    if rec.get("do_mat"):
        warnings.append(f"Tài liệu có độ mật: {rec['do_mat']} — kiểm tra mức độ tiếp cận")

    rec.update(
        stt=stt,
        trang_pdf=doc.page_range,
        nguoi_ky=values["nguoi_ky"],
        chuc_vu_nguoi_ky=values["chuc_vu_nguoi_ky"],
        diem_ocr=round(avg, 2),
        can_kiem_tra=" | ".join(warnings),
        _nguon=sources,
        _llm_timings={k: timings.get(k) for k in ("prompt_n", "predicted_n", "prompt_ms", "predicted_ms")},
    )
    return rec


def _parse_date(d: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", d or "")
    return (int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def build_ho_so(ho_so_input: dict, docs: list[dict], pdf_name: str) -> dict:
    """Bản ghi hồ sơ: trường nhập tay lấy từ ho_so_input, trường tự tính từ các tài liệu."""
    rec = defaults("ho_so")
    rec.update({k: v for k, v in ho_so_input.items() if k in rec and v not in (None, "")})
    dates = sorted(filter(None, (_parse_date(d["ngay_ban_hanh"]) for d in docs)))
    fmt = lambda t: f"{t[2]:02d}/{t[1]:02d}/{t[0]}"  # noqa: E731
    keywords = Counter(k for d in docs for k in d["tu_khoa"].split("; ") if k)
    rec.update(
        ngon_ngu=", ".join(sorted({d["ngon_ngu"] for d in docs if d["ngon_ngu"]})),
        thoi_gian_bat_dau=fmt(dates[0]) if dates else "",
        thoi_gian_ket_thuc=fmt(dates[-1]) if dates else "",
        tu_khoa="; ".join(k for k, _ in keywords.most_common(8)),
        tong_so_tai_lieu=len(docs),
        so_luong_to=sum(d["so_luong_to"] for d in docs),
        so_luong_trang=sum(d["so_luong_trang"] for d in docs),
        tep_tin_ho_so=rec.get("tep_tin_ho_so") or pdf_name,
    )
    return rec
