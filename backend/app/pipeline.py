"""Xử lý trọn một hồ sơ: đọc chữ từng trang (OCR) -> tách văn bản -> trích xuất -> lưu CSDL.

Dữ liệu mỗi hồ sơ nằm ở data/ho_so/<id>/:
    goc.pdf                    PDF người dùng tải lên (hồ sơ nhập từ thư mục: đọc thẳng file gốc, không chép)
    trang/page_001.jpg         ảnh trang để xem (đã xoay thẳng, thu nhỏ ~150 DPI)
    trang/page_001.ocr.json    kết quả OCR (dùng lại, không OCR lại nếu đã có)
    trang/page_001.thumb.jpg   ảnh thu nhỏ cho màn tách văn bản
    xuat/                      file Excel / CSV / PDF xuất ra

Ảnh 300 DPI để OCR chỉ tồn tại trong lúc đọc trang đó rồi xóa: giữ lại ảnh 300 DPI của hàng chục nghìn
trang sẽ tốn hàng trăm GB ổ cứng. Hồ sơ cũ (đã có page_001.png) vẫn xem được như trước.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from app import db
from app.config import DATA_DIR
from app.extract import build_ho_so, extract_document
from app.jobs import Job
from app.ocr import OcrPage
from app.segment import split_by_boundaries
from app.services import LlmService, OcrService
from app.sources import PdfSet, whole_source
from app.tt05 import inherited_keys

VIEW_MAX_WIDTH = 1400  # ảnh để xem: ~150 DPI với khổ A4, đủ rõ để soát, ~200 KB/trang
VIEW_QUALITY = 78


def ho_so_dir(ho_so_id: int) -> Path:
    return DATA_DIR / "ho_so" / str(ho_so_id)


def pages_dir(ho_so_id: int) -> Path:
    return ho_so_dir(ho_so_id) / "trang"


def clear_pages(ho_so_id: int) -> None:
    shutil.rmtree(pages_dir(ho_so_id), ignore_errors=True)


def page_png(ho_so_id: int, n: int) -> Path:
    return pages_dir(ho_so_id) / f"page_{n:03d}.png"


def ocr_path(ho_so_id: int, n: int) -> Path:
    return pages_dir(ho_so_id) / f"page_{n:03d}.ocr.json"


def view_path(ho_so_id: int, n: int) -> Path:
    return pages_dir(ho_so_id) / f"page_{n:03d}.jpg"


def view_image(ho_so_id: int, n: int) -> Path | None:
    """Ảnh đã xử lý (xoay thẳng, khớp toạ độ OCR) của trang n, nếu có."""
    for p in (view_path(ho_so_id, n), page_png(ho_so_id, n)):
        if p.exists():
            return p
    return None


def ocr_cache(img: Path) -> Path:  # giữ tương thích: page_001.png -> page_001.ocr.json
    return img.with_suffix(".ocr.json")


def load_ocr(ho_so_id: int, n: int) -> OcrPage | None:
    p = ocr_path(ho_so_id, n)
    if not p.exists():
        return None
    return OcrPage.from_dict(json.loads(p.read_text(encoding="utf-8")))


def make_view(src: Path, dest: Path) -> None:
    from PIL import Image

    with Image.open(src) as im:
        im = im.convert("RGB")
        if im.width > VIEW_MAX_WIDTH:
            im = im.resize((VIEW_MAX_WIDTH, round(im.height * VIEW_MAX_WIDTH / im.width)), Image.LANCZOS)
        im.save(dest, "JPEG", quality=VIEW_QUALITY, optimize=True)


def run_job(job: Job, ocr: OcrService, llm: LlmService) -> None:
    """Hủy / lỗi: hàng đợi (jobs.JobQueue) tự đặt lại trạng thái hồ sơ."""
    info = db.load_ho_so(job.ho_so_id)
    if not info["nguon_pdf"]:
        raise FileNotFoundError("Hồ sơ chưa có file PDF")
    db.set_status(job.ho_so_id, "dang_xu_ly")
    pages = ocr_all(job, info, ocr)
    if job.kind == "ocr":  # chỉ đọc chữ để gợi ý trang đầu tài liệu -> xong, chưa tách / trích xuất
        db.end_stopped(job.ho_so_id, "")
        return
    _extract(job, info, pages, llm)


def ocr_all(job: Job, info: dict, ocr: OcrService) -> list[OcrPage]:
    """Đọc chữ mọi trang (trang đã đọc thì dùng lại). Mỗi trang: ảnh 300 DPI -> OCR -> ảnh xem nhỏ."""
    ho_so_id = job.ho_so_id
    if job.params.get("ocr_lai"):
        clear_pages(ho_so_id)
    total = info["so_trang"]
    todo = [n for n in range(1, total + 1) if not ocr_path(ho_so_id, n).exists()]
    if todo and not ocr.loaded:
        job.update(stage="nap_ocr", current=0, total=0)
    engine = ocr.get() if todo else None
    job.update(stage="ocr", current=0, total=total)
    pages: list[OcrPage] = []
    t_ocr, n_ocr = 0.0, 0
    with PdfSet(info["nguon_pdf"]) as pdfs:
        for n in range(1, total + 1):
            page = load_ocr(ho_so_id, n)
            if page is None:
                t0 = time.perf_counter()
                png = pdfs.render(n, page_png(ho_so_id, n), dpi=300)
                page = engine.run(png)  # xoay thẳng ảnh nếu cần, toạ độ theo ảnh đã xoay
                make_view(png, view_path(ho_so_id, n))
                page.image = view_path(ho_so_id, n).name
                ocr_path(ho_so_id, n).write_text(json.dumps(page.to_dict(), ensure_ascii=False), encoding="utf-8")
                png.unlink(missing_ok=True)
                for old in (page_png(ho_so_id, n).with_suffix(".preview.jpg"),
                            page_png(ho_so_id, n).with_suffix(".thumb.jpg")):
                    old.unlink(missing_ok=True)  # ảnh xem trước (chưa xoay) không còn đúng nữa
                t_ocr += time.perf_counter() - t0
                n_ocr += 1
            pages.append(page)
            src, idx = pdfs.locate(n)
            where = f" — {src['ten']}" if len(info["nguon_pdf"]) > 1 else ""
            job.update(current=n, message=f"Trang {n}/{total}{where}")
    job.stats.update(ocr_pages=n_ocr, ocr_s=t_ocr)
    return pages


def default_starts(info: dict) -> list[int]:
    """Cách tách hiện tại: theo lần xử lý trước; chưa xử lý -> trang đầu của từng file nguồn."""
    return ([int(str(d["trang_pdf"]).split("-")[0]) for d in info["tai_lieu"]]
            or [s["trang_dau"] for s in info["nguon_pdf"]] or [1])


def _extract(job: Job, info: dict, pages: list[OcrPage], llm: LlmService) -> None:
    ho_so_id = job.ho_so_id
    page_nos = list(range(1, len(pages) + 1))

    # 3) Tách văn bản. Ranh giới do NGƯỜI DÙNG đánh dấu (tab "Tách văn bản"), hoặc theo file khi nhập thư mục.
    # Không gửi -> giữ cách tách của lần xử lý trước; chưa từng xử lý -> mỗi file 1 tài liệu (PDF tải lên:
    # cả file là 1 tài liệu). App KHÔNG tự đoán ranh giới theo nội dung.
    job.update(stage="tach_van_ban", current=0, total=0, message="")
    starts = job.params.get("ranh_gioi") or default_starts(info)
    docs = split_by_boundaries(pages, page_nos, starts)

    # 4) Kết quả của LUẬT cho mọi văn bản -> lưu ngay (vài giây) để giao diện hiện và soát được luôn.
    ho_so_base = info["ho_so"]
    use_llm = not job.params.get("khong_llm")
    old = {d["trang_pdf"]: d for d in db.load_ho_so(ho_so_id)["tai_lieu"]}
    # Làm tiếp sau khi tạm dừng / tắt app: văn bản AI đã đọc xong thì giữ nguyên, không đọc lại.
    resume = job.params.get("tiep_tuc")
    records, done_ai = [], set()
    for i, doc in enumerate(docs, 1):
        prev = old.get(doc.page_range)
        if resume and use_llm and prev and prev.get("ai_trang_thai") == "xong" and prev["stt"] == i:
            rec = prev
            done_ai.add(i)
        else:
            rec = extract_document(doc, None, ho_so_base, stt=i)
            rec["ai_trang_thai"] = "cho" if use_llm else "tat"
            rec = _keep_manual(rec, old)
        records.append(_file_name(rec, info))
    pdf_name = info["ho_so"].get("tep_tin_ho_so") or (info["nguon_pdf"][0]["ten"] if info["nguon_pdf"] else "")
    db.replace_tai_lieu(ho_so_id, records, build_ho_so(ho_so_base, records, pdf_name))

    # 5) AI làm giàu từng văn bản (cơ quan, trích yếu, từ khóa, người ký); xong văn bản nào lưu văn bản đó.
    if use_llm and len(done_ai) < len(docs):
        if not llm.running:
            job.update(stage="nap_llm", current=0, total=0)
        client = llm.client()
        job.update(stage="trich_xuat", current=len(done_ai), total=len(docs))
        t_ai, n_ai = 0.0, 0
        for i, doc in enumerate(docs, 1):
            if i in done_ai:
                continue
            t0 = time.perf_counter()
            try:
                rec = extract_document(doc, client, ho_so_base, stt=i)
                rec["ai_trang_thai"] = "xong"
            except (ValueError, RuntimeError) as e:  # AI lỗi ở 1 văn bản -> giữ kết quả của luật
                rec = extract_document(doc, None, ho_so_base, stt=i)
                rec["ai_trang_thai"] = "loi"
                rec["can_kiem_tra"] = " | ".join(filter(None, [f"AI lỗi: {e}"[:200], rec["can_kiem_tra"]]))
            t_ai += time.perf_counter() - t0
            n_ai += 1
            job.stats.update(ai_docs=n_ai, ai_s=t_ai)
            rec = _file_name(_keep_manual(rec, old), info)
            records[i - 1] = rec
            db.write_docs(ho_so_id, [rec])
            llm.touch()
            so = "/".join(filter(None, [rec["so_cua_tai_lieu"], rec["ky_hieu_cua_tai_lieu"]]))
            job.update(current=i, message=f"Văn bản {i}: {rec['ten_loai_tai_lieu']} {so}".strip())

    # 6) Tính lại dữ liệu hồ sơ (thời gian, từ khóa...) và xong
    job.update(stage="luu", current=0, total=0, message="")
    db.update_ho_so_info(ho_so_id, None, build_ho_so(ho_so_base, records, pdf_name))
    db.set_status(ho_so_id, "xong")


def _file_name(rec: dict, info: dict) -> dict:
    """Cột 'Tệp tin tài liệu': hồ sơ nhập từ thư mục, tài liệu trùng đúng 1 file -> tên file gốc
    (người dùng đã chọn). Còn lại: mã lưu trữ tài liệu + .pdf (file app tách ra khi xuất)."""
    if rec.get("_nguon", {}).get("tep_tin_tai_lieu") == "sửa tay":
        return rec
    src = whole_source(info["nguon_pdf"], rec["trang_pdf"]) if info.get("tu_thu_muc") else None
    rec["tep_tin_tai_lieu"] = src["ten"] if src else f"{rec['ma_luu_tru_tai_lieu']}.pdf"
    return rec


def _keep_manual(rec: dict, old: dict) -> dict:
    """Giữ công soát: văn bản vẫn đúng các trang như lần trước -> giữ ô 'sửa tay' và cờ đã soát."""
    prev = old.get(rec["trang_pdf"])
    if prev:
        for k, src in prev["_nguon"].items():
            if src == "sửa tay" and k in prev:
                rec[k] = prev[k]
                rec["_nguon"][k] = "sửa tay"
        rec["da_soat"] = prev.get("da_soat", False)
    return rec


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
        _file_name(d, info)
    if docs:
        db.write_docs(ho_so_id, docs)
        pdf_name = info["nguon_pdf"][0]["ten"] if info["nguon_pdf"] else ""
        db.update_ho_so_info(ho_so_id, None, build_ho_so(ho_so, docs, pdf_name))
    return db.load_ho_so(ho_so_id)
