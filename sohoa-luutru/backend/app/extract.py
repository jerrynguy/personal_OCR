"""Trích xuất trường dữ liệu TT05 cho từng văn bản: luật trước, LLM sau, rồi gộp + kiểm tra.

- Luật: tên loại, số, ký hiệu, ngày ban hành, độ mật, độ khẩn, tờ số, ngôn ngữ.
- LLM: cơ quan ban hành (chuẩn hóa viết hoa), trích yếu, từ khóa, người ký, chức vụ.
  Chỉ khi luật KHÔNG đọc được tên loại / số ký hiệu / ngày thì mới hỏi thêm LLM (và đánh dấu
  "Cần kiểm tra"). LLM chỉ được gửi đoạn trích cần thiết, trả JSON tên trường ngắn — để nhanh.
"""

from __future__ import annotations

import re
from collections import Counter

from app.llm import LlmClient
from app.ocr import group_rows, lines_to_text
from app.rules import (
    DO_KHAN,
    DO_MAT,
    TEN_LOAI,
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
HEAD_CHARS = 700  # đầu văn bản (đã bỏ quốc hiệu, số, ngày): tên loại, trích yếu, vài dòng căn cứ (cho từ khóa)
SIG_ROWS = 8  # số dòng cuối của trang cuối: khối chữ ký (chức vụ, người ký)

# Tên trường NGẮN để LLM phải viết ít token nhất (mỗi token ~0.1s trên CPU).
# maxLength / maxItems là giới hạn CỨNG (llama.cpp biến thành grammar): model không thể viết lặp
# vô tận trong một trường (đã gặp khi chạy thật: kẹt trong danh sách từ khóa đến hết max_tokens).
LLM_BASE = {
    "co_quan": {"type": "string", "maxLength": 150},
    "trich_yeu": {"type": "string", "maxLength": 400},
    "tu_khoa": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 5},
    "nguoi_ky": {"type": "string", "maxLength": 60},
    "chuc_vu": {"type": "string", "maxLength": 80},
}
# Chỉ hỏi thêm khi LUẬT không đọc được (không bắt LLM đọc lại cái luật đã có -> nhanh hơn).
LLM_FALLBACK = {
    "ten_loai": {"type": "string", "maxLength": 40},
    "so_ky_hieu": {"type": "string", "maxLength": 40},
    "ngay": {"type": "string", "pattern": "^([0-9]{2}/[0-9]{2}/[0-9]{4})?$"},
}
LLM_MAX_TOKENS = 768  # chặn mọi trường hợp lặp còn sót (bình thường ~100 token + phần suy nghĩ ngắn)

# Giữ NGUYÊN câu này giữa các văn bản: llama.cpp nhớ phần đã đọc, văn bản sau không phải đọc lại.
LLM_SYSTEM = (
    "Bạn trích xuất thông tin văn bản hành chính Việt Nam từ đoạn trích OCR (có thể sai chính tả nhẹ; "
    "'|' ngăn 2 cột trên cùng dòng). Trả JSON:\n"
    "- co_quan: cơ quan ban hành (dòng [CƠ QUAN]), KHÔNG viết hoa toàn bộ: chỉ viết hoa chữ đầu và tên riêng, "
    "ví dụ 'Ủy ban nhân dân tỉnh An Bình', 'Sở Nội vụ tỉnh An Bình'.\n"
    "- trich_yeu: trích yếu nội dung ngay dưới tên loại hoặc dòng 'V/v'; sửa chính tả, viết đầy đủ từ viết tắt, giữ 'V/v'.\n"
    "- tu_khoa: 3-5 từ khóa về vấn đề văn bản đề cập; không dùng tên loại văn bản, cơ quan, địa danh, tên người.\n"
    "- nguoi_ky, chuc_vu: người ký và chức vụ trong phần [CHỮ KÝ].\n"
    "- ten_loai (Quyết định, Công văn...), so_ky_hieu (giữ nguyên sau 'Số:'), ngay (dd/mm/yyyy): nếu được hỏi.\n"
    "Trường nào không có thì để chuỗi rỗng, không đoán. Viết JSON gọn trên một dòng."
)


def llm_schema(rule: dict) -> dict:
    props = dict(LLM_BASE)
    if not rule["ten_loai_tai_lieu"]:
        props["ten_loai"] = LLM_FALLBACK["ten_loai"]
    if not (rule["so_cua_tai_lieu"] and rule["ky_hieu_cua_tai_lieu"]):
        props["so_ky_hieu"] = LLM_FALLBACK["so_ky_hieu"]
    if not rule["ngay_ban_hanh"]:
        props["ngay"] = LLM_FALLBACK["ngay"]
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _body_text(doc: Document) -> str:
    """Trang đầu, BỎ các dòng luật đã đọc (quốc hiệu, tiêu ngữ, dòng 'Số: ... | địa danh, ngày ...')."""
    rows = []
    for row in group_rows(doc.pages[0].lines):
        k = key_text(" ".join(l.text for l in row))
        if "CONG HOA" in k or "DOC LAP" in k or any(parse_so_ky_hieu(l.text) for l in row):
            continue
        rows.append("   |   ".join(l.text for l in row))
    return "\n".join(rows)


def document_excerpt(doc: Document, rule: dict) -> str:
    """Chỉ gửi LLM phần cần thiết thay vì cả văn bản — LLM đọc ít hơn thì nhanh hơn."""
    first_text = _body_text(doc)
    parts = []
    if rule["_co_quan_tho"]:
        parts.append(f"[CƠ QUAN] {rule['_co_quan_tho']}")
    parts.append("[ĐẦU VĂN BẢN]\n" + first_text[:HEAD_CHARS])
    if len(doc.pages) > 1 or len(first_text) > HEAD_CHARS:  # chữ ký chưa nằm trong phần đầu
        rows = group_rows(doc.pages[-1].lines)[-SIG_ROWS:]
        parts.append("[CHỮ KÝ]\n" + "\n".join("   |   ".join(l.text for l in r) for r in rows))
    return "\n\n".join(parts)


VI_CHARS = set("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")


def detect_language(doc: Document) -> str:
    """Có đủ chữ cái tiếng Việt có dấu -> Tiếng Việt; không thì để trống cho người dùng kiểm tra."""
    letters = [c for p in doc.pages[:2] for l in p.lines for c in l.text.lower() if c.isalpha()]
    if not letters:
        return ""
    return "Tiếng Việt" if sum(c in VI_CHARS for c in letters) / len(letters) > 0.05 else ""


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


def merge(rule: dict, llm: dict | None, ngon_ngu: str) -> tuple[dict, dict, list[str]]:
    """Gộp kết quả luật + LLM. Trả về (giá trị, nguồn từng trường, cảnh báo)."""
    out, src, warn = {}, {}, []
    llm = llm or {}

    def pick(key: str, rule_val: str, llm_val: str, label: str) -> None:
        if rule_val:
            out[key], src[key] = rule_val, "luật"
        elif llm_val:
            out[key], src[key] = llm_val, "LLM"
            warn.append(f"{label} do AI đọc (luật không tìm thấy) — kiểm tra lại")
        else:
            out[key], src[key] = "", ""
            warn.append(f"Không tìm thấy {label.lower()}")

    llm_skh = parse_so_ky_hieu("Số: " + llm["so_ky_hieu"]) if llm.get("so_ky_hieu") else None
    pick("ten_loai_tai_lieu", rule["ten_loai_tai_lieu"], llm.get("ten_loai", ""), "Tên loại")
    pick("so_cua_tai_lieu", rule["so_cua_tai_lieu"], llm_skh.so if llm_skh else "", "Số")
    pick("ky_hieu_cua_tai_lieu", rule["ky_hieu_cua_tai_lieu"], llm_skh.ky_hieu if llm_skh else "", "Ký hiệu")
    pick("ngay_ban_hanh", rule["ngay_ban_hanh"], llm.get("ngay", ""), "Ngày ban hành")

    for key, llm_key in [
        ("co_quan_ban_hanh", "co_quan"),
        ("trich_yeu_noi_dung", "trich_yeu"),
        ("nguoi_ky", "nguoi_ky"),
        ("chuc_vu_nguoi_ky", "chuc_vu"),
    ]:
        val = (llm.get(llm_key) or "").strip()
        out[key], src[key] = val, "LLM" if val else ""
    if not out["co_quan_ban_hanh"] and rule["_co_quan_tho"]:
        out["co_quan_ban_hanh"], src["co_quan_ban_hanh"] = rule["_co_quan_tho"], "luật (chưa chuẩn hóa)"
    if not out["trich_yeu_noi_dung"]:
        warn.append("Không có trích yếu nội dung")
    loai = {key_text(t) for t in TEN_LOAI}
    out["tu_khoa"] = "; ".join(
        k.strip() for k in llm.get("tu_khoa", []) if k.strip() and key_text(k) not in loai
    )
    src["tu_khoa"] = "LLM" if out["tu_khoa"] else ""
    out["ngon_ngu"], src["ngon_ngu"] = ngon_ngu, "luật" if ngon_ngu else ""
    if not ngon_ngu:
        warn.append("Không xác định được ngôn ngữ")

    for key in ("do_mat", "do_khan", "to_so"):
        out[key], src[key] = rule[key], "luật" if rule[key] else ""
    return out, src, warn


def extract_document(doc: Document, llm: LlmClient | None, ho_so: dict, stt: int) -> dict:
    """Bản ghi tài liệu đầy đủ theo TT05 (+ cột bổ sung, + '_nguon' và '_canh_bao')."""
    rule = rule_fields(doc)
    llm_out, timings = None, {}
    if llm is not None:
        llm_out, timings = llm.extract_json(
            LLM_SYSTEM, document_excerpt(doc, rule), llm_schema(rule), max_tokens=LLM_MAX_TOKENS
        )
    values, sources, warnings = merge(rule, llm_out, detect_language(doc))

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
