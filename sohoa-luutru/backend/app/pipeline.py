"""Xử lý trọn một hồ sơ: tách trang -> OCR -> tách văn bản -> trích xuất -> lưu CSDL.

Dữ liệu mỗi hồ sơ nằm ở data/ho_so/<id>/:
    goc.pdf                    PDF người dùng tải lên
    trang/page_001.png         ảnh trang (đã xoay thẳng nếu cần)
    trang/page_001.ocr.json    kết quả OCR (dùng lại, không OCR lại nếu đã có)
    xuat/                      file Excel / CSV / PDF xuất ra
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from app import db
from app.config import DATA_DIR
from app.extract import build_ho_so, extract_document
from app.jobs import Cancelled, Job
from app.ocr import OcrPage
from app.pdf_render import render_pdf
from app.segment import split_by_boundaries, split_documents
from app.services import LlmService, OcrService
from app.tt05 import inherited_keys


def ho_so_dir(ho_so_id: int) -> Path:
    return DATA_DIR / "ho_so" / str(ho_so_id)


def pages_dir(ho_so_id: int) -> Path:
    return ho_so_dir(ho_so_id) / "trang"


def clear_pages(ho_so_id: int) -> None:
    shutil.rmtree(pages_dir(ho_so_id), ignore_errors=True)


def ocr_cache(img: Path) -> Path:
    return img.with_suffix(".ocr.json")


def run_job(job: Job, ocr: OcrService, llm: LlmService) -> None:
    ho_so_id = job.ho_so_id
    info = db.load_ho_so(ho_so_id)
    pdf = Path(info["tep_pdf"] or "")
    if not pdf.exists():
        raise FileNotFoundError("Hồ sơ chưa có file PDF")
    db.set_status(ho_so_id, "dang_xu_ly")
    try:
        _run(job, info, pdf, ocr, llm)
    except Cancelled:
        db.set_status(ho_so_id, "xong" if info["tai_lieu"] else "moi", "Đã hủy lần xử lý gần nhất")
        raise
    except Exception as e:
        db.set_status(ho_so_id, "loi", f"{e.__class__.__name__}: {e}")
        raise


def _run(job: Job, info: dict, pdf: Path, ocr: OcrService, llm: LlmService) -> None:
    ho_so_id = job.ho_so_id
    if job.params.get("ocr_lai"):
        clear_pages(ho_so_id)

    # 1) Tách trang (trang đã OCR thì giữ ảnh cũ — có thể đã được xoay thẳng)
    job.update(stage="tach_trang", current=0, total=info["so_trang"])
    images = render_pdf(
        pdf, pages_dir(ho_so_id),
        skip=lambda img: ocr_cache(img).exists() and img.exists(),
        on_page=lambda n, total: job.update(current=n, total=total),
    )
    page_nos = [int(p.stem.split("_")[1]) for p in images]

    # 2) OCR (dùng lại kết quả đã lưu)
    todo = [img for img in images if not ocr_cache(img).exists()]
    if todo and not ocr.loaded:
        job.update(stage="nap_ocr", current=0, total=0)
    engine = ocr.get() if todo else None
    job.update(stage="ocr", current=0, total=len(images))
    pages: list[OcrPage] = []
    for n, img in enumerate(images, 1):
        cache = ocr_cache(img)
        if cache.exists():
            page = OcrPage.from_dict(json.loads(cache.read_text(encoding="utf-8")))
        else:
            page = engine.run(img)
            cache.write_text(json.dumps(page.to_dict(), ensure_ascii=False), encoding="utf-8")
        pages.append(page)
        job.update(current=n, message=f"Trang {n}/{len(images)}")

    # 3) Tách văn bản (tự động, hoặc theo ranh giới người dùng chỉnh)
    job.update(stage="tach_van_ban", current=0, total=0, message="")
    starts = job.params.get("ranh_gioi")
    docs = split_by_boundaries(pages, page_nos, starts) if starts else split_documents(pages, page_nos)

    # 4) Trích xuất: luật + LLM
    client = None
    if not job.params.get("khong_llm"):
        job.update(stage="nap_llm")
        client = llm.client()
    job.update(stage="trich_xuat", current=0, total=len(docs))
    ho_so_base = info["ho_so"]
    records = []
    for i, doc in enumerate(docs, 1):
        try:
            rec = extract_document(doc, client, ho_so_base, stt=i)
        except (ValueError, RuntimeError) as e:  # LLM lỗi ở 1 văn bản -> vẫn giữ kết quả của luật
            rec = extract_document(doc, None, ho_so_base, stt=i)
            rec["can_kiem_tra"] = " | ".join(filter(None, [f"LLM lỗi: {e}"[:200], rec["can_kiem_tra"]]))
        records.append(rec)
        llm.touch()
        so = "/".join(filter(None, [rec["so_cua_tai_lieu"], rec["ky_hieu_cua_tai_lieu"]]))
        job.update(current=i, message=f"Văn bản {i}: {rec['ten_loai_tai_lieu']} {so}".strip())

    # 5) Giữ lại công soát của người dùng: văn bản nào vẫn đúng các trang như lần trước thì
    #    giữ các ô đã "sửa tay" và cờ đã soát.
    old = {d["trang_pdf"]: d for d in db.load_ho_so(ho_so_id)["tai_lieu"]}
    for rec in records:
        prev = old.get(rec["trang_pdf"])
        if not prev:
            continue
        for k, src in prev["_nguon"].items():
            if src == "sửa tay" and k in prev:
                rec[k] = prev[k]
                rec["_nguon"][k] = "sửa tay"
        rec["da_soat"] = prev.get("da_soat", False)

    # 6) Lưu
    job.update(stage="luu", current=0, total=0, message="")
    ho_so = build_ho_so(ho_so_base, records, pdf.name)
    db.replace_tai_lieu(ho_so_id, records, ho_so)
    db.set_status(ho_so_id, "xong")


def refresh_ho_so(ho_so_id: int) -> dict:
    """Sau khi người dùng sửa thông tin hồ sơ / tài liệu:
    - đẩy trường kế thừa + mã lưu trữ xuống các tài liệu (trừ ô đã sửa tay),
    - tính lại các trường tự tính của hồ sơ.
    """
    info = db.load_ho_so(ho_so_id)
    ho_so, docs = info["ho_so"], info["tai_lieu"]
    ma = ho_so.get("ma_ho_so", "")
    for d in docs:
        nguon = d["_nguon"]
        for k in inherited_keys():
            if nguon.get(k) != "sửa tay":
                d[k] = ho_so.get(k, "")
        if nguon.get("ma_luu_tru_tai_lieu") != "sửa tay":
            d["ma_luu_tru_tai_lieu"] = f"{ma}.{d['stt']:02d}" if ma else f"{d['stt']:02d}"
        if nguon.get("tep_tin_tai_lieu") != "sửa tay":
            d["tep_tin_tai_lieu"] = f"{d['ma_luu_tru_tai_lieu']}.pdf"
    if docs:
        db.write_docs(ho_so_id, docs)
        pdf_name = Path(info["tep_pdf"] or "").name
        db.update_ho_so_info(ho_so_id, None, build_ho_so(ho_so, docs, pdf_name))
    return db.load_ho_so(ho_so_id)
