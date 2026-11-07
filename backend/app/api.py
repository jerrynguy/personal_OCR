"""API cho giao diện. Chỉ nghe 127.0.0.1; mọi request /api/* (trừ /api/health) phải
kèm token: header 'X-Token: <token>' hoặc '?token=<token>' (dùng cho ảnh / tải file).

Tóm tắt:
  GET    /api/health                         sống chưa (không cần token)
  GET    /api/he-thong                       model nào đã có / đang nạp, tóm tắt hàng đợi
  GET    /api/schema                         danh sách trường TT05 (để vẽ form)
  GET    /api/ho-so?q=&lo=&trang_thai=&trang=&moi_trang=   danh sách hồ sơ (lọc + phân trang)
  GET    /api/lo                             các lô đã nhập (thư mục cha)
  POST   /api/ho-so                          tạo hồ sơ {phong:{...}, ho_so:{...}}
  POST   /api/ho-so/xoa                      xóa nhiều hồ sơ {ids:[...]} hoặc {loc:{lo,q,trang_thai}}
  GET    /api/ho-so/{id}                     chi tiết: phông, hồ sơ, tài liệu, file nguồn, tiến độ
  PUT    /api/ho-so/{id}                     sửa thông tin phông / hồ sơ
  DELETE /api/ho-so/{id}                     xóa hồ sơ (dữ liệu của app; file gốc nhập từ thư mục KHÔNG bị xóa)
  POST   /api/ho-so/{id}/pdf                 tải PDF lên (multipart, trường 'file')
  POST   /api/ho-so/{id}/xu-ly               xếp hàng xử lý {ocr_lai?, ranh_gioi?: [trang bắt đầu...], khong_llm?}
  POST   /api/ho-so/{id}/doc-chu             chỉ đọc chữ (OCR) để app gợi ý trang đầu tài liệu
  GET    /api/ho-so/{id}/goi-y               trang có vẻ là trang đầu tài liệu (quốc hiệu / dòng "Số:")
  GET    /api/ho-so/{id}/tien-do             tiến độ (đang chạy / đang chờ thứ mấy / lần gần nhất)
  POST   /api/ho-so/{id}/huy                 hủy (đang chạy) hoặc bỏ khỏi hàng đợi (đang chờ)
  POST   /api/xu-ly/{job_id}/huy             hủy theo mã lần xử lý (giữ cho tương thích)
  GET    /api/ho-so/{id}/trang               danh sách trang
  GET    /api/ho-so/{id}/trang/{n}/anh       ảnh trang (?nho=1: ảnh thu nhỏ)
  GET    /api/ho-so/{id}/trang/{n}/ocr       các dòng chữ + toạ độ (để tô sáng trên ảnh)
  PUT    /api/ho-so/{id}/tai-lieu/{stt}      sửa tay {thay_doi: {...}, da_soat?: bool}
  GET    /api/ho-so/{id}/xuat/xlsx|csv|pdf   tải file xuất: 23 cột điểm c TT05 (pdf = .zip từng tài liệu)
  GET    /api/xuat/xlsx|xlsx-zip?ids=|lo=&q=&trang_thai=   xuất NHIỀU hồ sơ: 1 file gộp | mỗi hồ sơ 1 file (.zip)
  GET    /api/hang-doi                       hàng đợi: đang chạy, đang chờ, ước tính thời gian, tạm dừng?
  POST   /api/hang-doi/tam-dung | tiep-tuc   tạm dừng ngay / chạy tiếp
  POST   /api/hang-doi/them                  xếp nhiều hồ sơ {ids | loc, khong_llm?, chi_chua_ai?}
  POST   /api/hang-doi/bo                    bỏ nhiều hồ sơ đang chờ khỏi hàng {ids | loc}
  POST   /api/nhap/chon-thu-muc              mở hộp chọn thư mục của Windows -> {duong_dan}
  POST   /api/nhap/quet                      quét thư mục {duong_dan} -> {id}; GET /api/nhap/quet/{id} tiến độ + kết quả
  POST   /api/nhap/tao                       tạo hàng loạt từ kết quả quét + xếp hàng xử lý
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import pymupdf
from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import batch, db
from app.config import (
    ACTIVE_LLM_FILE,
    DATA_DIR,
    DEFAULT_LLM_NAME,
    DET_MODELS,
    DOC_ORI_MODEL,
    LLM_DIR,
    VIETOCR_MODELS,
    paddle_model_dir,
    vietocr_weights_path,
)
from app.export import export_csv, export_xlsx, write_xlsx
from app.jobs import JobQueue
from app.llm import (
    active_model_path,
    default_model_path,
    hardware_profile,
    installed_variants,
    is_gguf,
    list_models,
    resolve_runtime,
)
from app.pdf_render import low_dpi_warning
from app.pipeline import (
    clear_pages, ho_so_dir, load_ocr, ocr_path, pages_dir, refresh_ho_so, run_job, view_image,
)
from app.segment import is_first_page, text_layer_page
from app.services import LlmService, OcrService, warm_up
from app.sources import PdfSet, SourceMissing, missing_files, pdf_lock, split_to_files
from app.tt05 import load_schema
from app.winperf import disable_power_throttling, power_status

MAX_PDF_MB = 500
THUMB_W = 360  # ảnh thu nhỏ (màn tách văn bản)
PREVIEW_W = 1100  # ảnh xem trước của trang chưa đọc chữ


def _safe(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", s).strip() or "ho_so"


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _download(path: Path, media: str) -> FileResponse:
    """Tải file về với đúng tên tiếng Việt (filename*), kèm tên không dấu cho trình duyệt / phần mềm cũ."""
    from urllib.parse import quote

    from app.rules import strip_accents

    plain = re.sub(r"[^A-Za-z0-9._-]+", "_", strip_accents(path.name)).strip("_") or "tai_ve"
    cd = f"attachment; filename=\"{plain}\"; filename*=utf-8''{quote(path.name)}"
    return FileResponse(path, media_type=media, headers={"Content-Disposition": cd})


def _public(info: dict) -> dict:
    """Bỏ đường dẫn từng file trên máy khỏi dữ liệu trả về giao diện (thư mục gốc thì vẫn hiện để người dùng biết)."""
    out = dict(info)
    sources = info.get("nguon_pdf") or []
    out["co_pdf"] = bool(sources) and (info.get("tu_thu_muc") or Path(sources[0]["duong_dan"]).exists())
    out["ten_pdf"] = sources[0]["ten"] if len(sources) == 1 else (f"{len(sources)} file PDF" if sources else "")
    out["nguon_pdf"] = [{"ten": s["ten"], "so_trang": s["so_trang"], "trang_dau": s["trang_dau"]} for s in sources]
    out["file_thieu"] = missing_files(sources) if info.get("tu_thu_muc") else []
    out.pop("tep_pdf", None)
    return out


def create_app(token: str | None = None, dev: bool = False, ocr_factory=None,
               frontend_dir: Path | None = None, warmup: bool = True, llm_service=None) -> FastAPI:
    token = token if token is not None else secrets.token_urlsafe(24)
    ocr = OcrService(ocr_factory)
    llm = llm_service or LlmService()
    jobs = JobQueue(lambda job: run_job(job, ocr, llm))
    scans = batch.Scans()

    @asynccontextmanager
    async def lifespan(_app):
        disable_power_throttling()  # backend chạy nền cũng không bị Windows hạ tốc độ
        if warmup:
            warm_up(ocr, llm)  # nạp sẵn OCR + LLM ở luồng nền ngay khi mở app
        yield
        llm.stop()  # tắt app -> tắt luôn llama-server, trả RAM

    app = FastAPI(
        title="Số hóa Lưu trữ — API",
        docs_url="/docs" if dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if dev else None,
        lifespan=lifespan,
    )
    app.state.token = token
    app.state.ocr, app.state.llm, app.state.jobs = ocr, llm, jobs

    if dev:  # giao diện chạy riêng bằng 'npm run dev' ở cổng 3000
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def check_token(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health" and request.method != "OPTIONS" and token:
            given = request.headers.get("x-token") or request.query_params.get("token")
            if not given or not secrets.compare_digest(given, token):
                return JSONResponse({"detail": "Sai hoặc thiếu token"}, status_code=401)
        return await call_next(request)

    def load(ho_so_id: int) -> dict:
        try:
            return db.load_ho_so(ho_so_id)
        except KeyError:
            raise HTTPException(404, "Không có hồ sơ này") from None

    def busy(ho_so_id: int) -> bool:
        """Đang CHẠY (hồ sơ đang chờ trong hàng thì vẫn sửa được: lúc chạy sẽ đọc thông tin mới nhất)."""
        return jobs.running_for(ho_so_id)

    def selection(body: dict | None = None, ids: str | None = None, lo: str | None = None, q: str | None = None,
                  trang_thai: str | None = None) -> list[int]:
        """Hồ sơ được chọn: danh sách id, hoặc mọi hồ sơ khớp bộ lọc (lô / tìm kiếm / trạng thái)."""
        if body is not None:
            if body.get("ids") is not None:
                return db.select_ids(ids=body["ids"])
            loc = body.get("loc") or {}
            return db.select_ids(lo=loc.get("lo"), q=loc.get("q"), trang_thai=loc.get("trang_thai"))
        id_list = [int(x) for x in ids.split(",") if x.strip()] if ids else None
        return db.select_ids(ids=id_list, lo=lo, q=q, trang_thai=trang_thai)

    # ------------------------------------------------------------ hệ thống
    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/he-thong")
    def he_thong():
        llm_path = ""
        if ACTIVE_LLM_FILE.exists():
            llm_path = json.loads(ACTIVE_LLM_FILE.read_text(encoding="utf-8")).get("path", "")
        models = {name: paddle_model_dir(name).exists() for name in [DOC_ORI_MODEL, *DET_MODELS]}
        models.update({f"VietOCR {n}": vietocr_weights_path(n).exists() for n in VIETOCR_MODELS})
        q = jobs.summary(limit=0)
        return {
            "model_ocr": models,
            "model_llm": Path(llm_path).name if llm_path else "",
            "model_llm_co_file": bool(llm_path) and Path(llm_path).exists(),
            "ocr_da_nap": ocr.loaded,
            "llm_dang_chay": llm.running,
            "llm_dang_nap": llm.loading,
            "llm_loi": llm.last_error,
            "nguon_dien": power_status(),
            "phan_cung": hardware_profile()[0],
            "khuyen_nghi": hardware_profile()[1],
            "llama_cpp_da_cai": installed_variants(),
            "llm_cau_hinh": resolve_runtime() if installed_variants() else None,
            "hang_doi": {k: q[k] for k in ("tam_dung", "dang_chay", "so_cho", "uoc_tinh_giay")},
        }

    # ------------------------------------------------------------ model AI (LLM)
    def llm_status() -> dict:
        try:
            active = active_model_path()
        except FileNotFoundError:
            active = None
        return {
            "dang_dung": active.name if active else "",
            "duong_dan": str(active) if active else "",
            "mac_dinh": DEFAULT_LLM_NAME,
            "dang_nap": llm.loading,
            "dang_chay": llm.running,
            "loi": llm.last_error,
            "danh_sach": list_models(),
            "thu_muc": str(LLM_DIR),
            "ram_gb": hardware_profile()[0]["ram_gb"],
        }

    def check_switchable() -> None:
        if jobs.active():
            raise HTTPException(409, "Đang có hồ sơ xử lý — tạm dừng hàng đợi (hoặc chờ xong) rồi đổi model")
        if llm.loading:
            raise HTTPException(409, "Đang nạp model — chờ một chút")

    def use_model(path: Path) -> dict:
        if not path.exists() or path.suffix.lower() != ".gguf":
            raise HTTPException(400, "Không thấy file .gguf ở đường dẫn này")
        if not is_gguf(path):
            raise HTTPException(400, "File không phải model GGUF hợp lệ (llama.cpp không đọc được)")
        check_switchable()
        llm.switch_model(path.resolve())
        return llm_status()

    @app.get("/api/llm")
    def llm_info():
        return llm_status()

    @app.post("/api/llm/chon")
    def llm_chon(body: dict = Body(...)):
        """Dùng một file .gguf có sẵn trên máy (không sao chép)."""
        return use_model(Path(str(body.get("duong_dan", "")).strip().strip('"')))

    @app.post("/api/llm/mac-dinh")
    def llm_mac_dinh():
        p = default_model_path()
        if not p:
            raise HTTPException(404, f"Không tìm thấy {DEFAULT_LLM_NAME} — chép file vào {LLM_DIR}")
        return use_model(p)

    @app.put("/api/llm/tai-len")
    async def llm_tai_len(request: Request, ten: str):
        """Tải file model lên: thân request là nội dung file (ghi thẳng xuống đĩa, không qua bộ nhớ tạm)."""
        name = _safe(Path(ten).name)
        if not name.lower().endswith(".gguf"):
            raise HTTPException(400, "Chỉ nhận file .gguf")
        folder = LLM_DIR / "tai_len"
        folder.mkdir(parents=True, exist_ok=True)
        dest, tmp = folder / name, folder / (name + ".dang_tai")
        first = b""
        try:
            with open(tmp, "wb") as f:
                async for chunk in request.stream():
                    if len(first) < 4:
                        first += chunk[: 4 - len(first)]
                        if len(first) == 4 and first != b"GGUF":
                            raise HTTPException(400, "File không phải model GGUF hợp lệ")
                    f.write(chunk)
        except BaseException:
            tmp.unlink(missing_ok=True)  # lỗi / người dùng hủy -> không để lại file dở
            raise
        if first != b"GGUF":
            tmp.unlink(missing_ok=True)
            raise HTTPException(400, "File không phải model GGUF hợp lệ")
        tmp.replace(dest)
        return {"duong_dan": str(dest), "ten": name, "dung_luong_gb": round(dest.stat().st_size / 1e9, 1)}

    @app.delete("/api/llm")
    def llm_xoa(duong_dan: str):
        """Chỉ xóa được file nằm trong thư mục model của app và không phải model đang dùng."""
        p = Path(duong_dan).resolve()
        if LLM_DIR.resolve() not in p.parents or not p.exists():
            raise HTTPException(400, "Chỉ xóa được model đã tải lên vào thư mục của app")
        try:
            if p == active_model_path().resolve():
                raise HTTPException(400, "Đang dùng model này — chọn model khác trước khi xóa")
        except FileNotFoundError:
            pass
        p.unlink()
        return llm_status()

    @app.get("/api/schema")
    def schema():
        return {k: v for k, v in load_schema().items() if not k.startswith("_")}

    # ------------------------------------------------------------ hồ sơ
    @app.get("/api/ho-so")
    def ds_ho_so(q: str = "", lo: str | None = None, trang_thai: str = "", trang: int = 1, moi_trang: int = 50):
        moi_trang = max(1, min(moi_trang, 500))
        trang = max(1, trang)
        # xem 1 lô: theo thứ tự thư mục lúc nhập; còn lại: hồ sơ mới cập nhật lên đầu
        total, rows = db.query_ho_so(lo=lo, q=q.strip(), trang_thai=trang_thai, offset=(trang - 1) * moi_trang,
                                     limit=moi_trang, order="thu_tu" if lo else "moi_nhat")
        for r in rows:
            r.pop("tep_pdf", None)
        return {"tong": total, "trang": trang, "moi_trang": moi_trang, "ho_so": rows}

    @app.get("/api/lo")
    def ds_lo():
        return db.list_lo()

    @app.post("/api/ho-so", status_code=201)
    def tao_ho_so(body: dict = Body(...)):
        try:
            new_id = db.create_ho_so(body.get("phong", {}), body.get("ho_so", {}))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return _public(db.load_ho_so(new_id))

    def delete_one(ho_so_id: int) -> None:
        db.dequeue([ho_so_id])
        db.delete_ho_so(ho_so_id)
        shutil.rmtree(ho_so_dir(ho_so_id), ignore_errors=True)  # chỉ dữ liệu của app, không đụng file gốc

    @app.post("/api/ho-so/xoa")
    def xoa_nhieu(body: dict = Body(...)):
        ids = selection(body)
        skipped = [i for i in ids if busy(i)]
        for i in ids:
            if i not in skipped:
                delete_one(i)
        return {"da_xoa": len(ids) - len(skipped), "bo_qua_dang_chay": len(skipped)}

    @app.get("/api/ho-so/{ho_so_id}")
    def chi_tiet(ho_so_id: int):
        info = _public(load(ho_so_id))
        info["tien_do"] = jobs.progress(ho_so_id)
        info["hang_doi_tam_dung"] = jobs.paused
        return info

    @app.put("/api/ho-so/{ho_so_id}")
    def sua_ho_so(ho_so_id: int, body: dict = Body(...)):
        load(ho_so_id)
        if busy(ho_so_id):
            raise HTTPException(409, "Hồ sơ đang xử lý, chờ xong rồi sửa")
        try:
            db.update_ho_so_info(ho_so_id, body.get("phong"), body.get("ho_so"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return _public(refresh_ho_so(ho_so_id))

    @app.delete("/api/ho-so/{ho_so_id}", status_code=204)
    def xoa_ho_so(ho_so_id: int):
        load(ho_so_id)
        if busy(ho_so_id):
            raise HTTPException(409, "Hồ sơ đang xử lý, hãy hủy trước")
        delete_one(ho_so_id)

    # ------------------------------------------------------------ PDF + xử lý
    @app.post("/api/ho-so/{ho_so_id}/pdf")
    def tai_pdf(ho_so_id: int, file: UploadFile = File(...)):
        load(ho_so_id)
        if busy(ho_so_id):
            raise HTTPException(409, "Hồ sơ đang xử lý")
        folder = ho_so_dir(ho_so_id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "dang_tai.pdf"
        size = 0
        with open(tmp, "wb") as f:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_PDF_MB * 1024 * 1024:
                    f.close()
                    tmp.unlink(missing_ok=True)
                    raise HTTPException(413, f"File quá lớn (tối đa {MAX_PDF_MB} MB)")
                f.write(chunk)
        try:
            with pdf_lock, pymupdf.open(tmp) as d:
                if d.needs_pass:
                    raise ValueError("PDF đang đặt mật khẩu")
                so_trang = d.page_count
        except ValueError as e:
            tmp.unlink(missing_ok=True)
            raise HTTPException(400, str(e)) from None
        except Exception:  # noqa: BLE001 — không đưa chi tiết (có đường dẫn trên máy) ra giao diện
            tmp.unlink(missing_ok=True)
            raise HTTPException(400, "Không đọc được file: file hỏng hoặc không phải PDF") from None
        dest = folder / "goc.pdf"
        tmp.replace(dest)
        clear_pages(ho_so_id)  # PDF mới -> bỏ kết quả OCR cũ
        db.set_pdf(ho_so_id, str(dest), so_trang)
        # Lưu ở ổ đĩa tên goc.pdf, nhưng "Tệp tin hồ sơ" ghi tên file gốc của người dùng
        db.update_ho_so_info(ho_so_id, None, {"tep_tin_ho_so": Path(file.filename or "ho_so.pdf").name})
        with pdf_lock:
            warn = low_dpi_warning(dest)
        return {"so_trang": so_trang, "ten_file": file.filename, "canh_bao": warn}

    @app.post("/api/ho-so/{ho_so_id}/xu-ly", status_code=202)
    def xu_ly(ho_so_id: int, body: dict | None = Body(None)):
        info = load(ho_so_id)
        if not info["nguon_pdf"]:
            raise HTTPException(400, "Hồ sơ chưa có file PDF")
        params = {k: v for k, v in (body or {}).items() if k in ("ocr_lai", "ranh_gioi", "khong_llm")}
        if "ranh_gioi" in params:
            starts = sorted({int(x) for x in params["ranh_gioi"] if 1 <= int(x) <= info["so_trang"]})
            if not starts or starts[0] != 1:
                starts = [1, *starts]
            params["ranh_gioi"] = starts
        return jobs.submit(ho_so_id, "xu_ly", params, uu_tien=1)

    @app.post("/api/ho-so/{ho_so_id}/doc-chu", status_code=202)
    def doc_chu(ho_so_id: int):
        """Chỉ đọc chữ (OCR) mọi trang — để app gợi ý trang đầu tài liệu. Kết quả được dùng lại khi xử lý."""
        info = load(ho_so_id)
        if not info["nguon_pdf"]:
            raise HTTPException(400, "Hồ sơ chưa có file PDF")
        return jobs.submit(ho_so_id, "ocr", {}, uu_tien=1)

    @app.get("/api/ho-so/{ho_so_id}/goi-y")
    def goi_y(ho_so_id: int):
        """GỢI Ý trang đầu tài liệu (người dùng bấm xác nhận, app không tự tách): trang có quốc hiệu hoặc
        dòng 'Số: ...' ở đầu trang. Dùng kết quả OCR; trang chưa OCR mà PDF có sẵn lớp chữ thì dùng lớp chữ."""
        info = load(ho_so_id)
        total = info["so_trang"]
        hits, read = [], 0
        missing = []
        for n in range(1, total + 1):
            page = load_ocr(ho_so_id, n)
            if page is None:
                missing.append(n)
                continue
            read += 1
            if is_first_page(page):
                hits.append(n)
        if missing and info["nguon_pdf"]:
            try:
                with PdfSet(info["nguon_pdf"]) as pdfs:
                    for n in missing:
                        with pdf_lock:
                            page = text_layer_page(pdfs.page(n))
                        if page is not None:
                            read += 1
                            if is_first_page(page):
                                hits.append(n)
            except (SourceMissing, ValueError):
                pass
        return {"goi_y": sorted(hits), "da_doc": read, "tong": total}

    @app.get("/api/ho-so/{ho_so_id}/tien-do")
    def tien_do(ho_so_id: int):
        load(ho_so_id)
        return jobs.progress(ho_so_id)

    @app.post("/api/ho-so/{ho_so_id}/huy")
    def huy_ho_so(ho_so_id: int):
        load(ho_so_id)
        if not jobs.cancel(ho_so_id):
            raise HTTPException(404, "Hồ sơ này không đang xử lý hay đang chờ")
        return {"ok": True}

    @app.post("/api/xu-ly/{job_id}/huy")
    def huy(job_id: int):
        if not jobs.cancel_job(job_id):
            raise HTTPException(404, "Không có lần xử lý đang chạy với mã này")
        return {"ok": True}

    # ------------------------------------------------------------ trang (ảnh + OCR)
    @app.get("/api/ho-so/{ho_so_id}/trang")
    def ds_trang(ho_so_id: int):
        info = load(ho_so_id)
        return [{"so": n, "co_anh": view_image(ho_so_id, n) is not None, "co_ocr": ocr_path(ho_so_id, n).exists()}
                for n in range(1, info["so_trang"] + 1)]

    @app.get("/api/ho-so/{ho_so_id}/trang/{n}/anh")
    def anh_trang(ho_so_id: int, n: int, nho: bool = False):
        """Ảnh trang. nho=1 -> ảnh thu nhỏ (JPEG) cho màn tách văn bản.
        Trang đã đọc chữ: ảnh đã xoay thẳng (khớp toạ độ OCR). Chưa đọc: vẽ nhanh từ PDF để xem trước."""
        info = load(ho_so_id)
        if not 1 <= n <= info["so_trang"]:
            raise HTTPException(404, "Không có trang này")
        folder = pages_dir(ho_so_id)
        img = view_image(ho_so_id, n)
        stem = f"page_{n:03d}"
        try:
            if nho:
                thumb = folder / f"{stem}.thumb.jpg"
                if not thumb.exists() or (img is not None and thumb.stat().st_mtime < img.stat().st_mtime):
                    if img is not None:
                        from PIL import Image

                        with Image.open(img) as im:
                            im = im.convert("RGB")
                            im.thumbnail((THUMB_W, round(THUMB_W * 1.5)))
                            folder.mkdir(parents=True, exist_ok=True)
                            im.save(thumb, "JPEG", quality=80)
                    else:
                        with PdfSet(info["nguon_pdf"]) as pdfs:
                            pdfs.render_jpeg(n, thumb, THUMB_W)
                return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
            if img is None:
                img = folder / f"{stem}.preview.jpg"
                if not img.exists():
                    with PdfSet(info["nguon_pdf"]) as pdfs:
                        pdfs.render_jpeg(n, img, PREVIEW_W)
        except SourceMissing as e:
            raise HTTPException(404, str(e)) from None
        media = "image/png" if img.suffix == ".png" else "image/jpeg"
        return FileResponse(img, media_type=media, headers={"Cache-Control": "no-cache"})

    @app.get("/api/ho-so/{ho_so_id}/trang/{n}/ocr")
    def ocr_trang(ho_so_id: int, n: int):
        load(ho_so_id)
        cache = ocr_path(ho_so_id, n)
        if not cache.exists():
            raise HTTPException(404, "Trang này chưa OCR")
        data = json.loads(cache.read_text(encoding="utf-8"))
        data.pop("image", None)
        return data

    # ------------------------------------------------------------ sửa tài liệu
    @app.put("/api/ho-so/{ho_so_id}/tai-lieu/{stt}")
    def sua_tai_lieu(ho_so_id: int, stt: int, body: dict = Body(...)):
        load(ho_so_id)
        if busy(ho_so_id):
            raise HTTPException(409, "Hồ sơ đang xử lý")
        try:
            db.update_tai_lieu(ho_so_id, stt, body.get("thay_doi", {}), body.get("da_soat"))
        except KeyError as e:
            raise HTTPException(404, str(e)) from None
        info = refresh_ho_so(ho_so_id)
        return {"tai_lieu": next(d for d in info["tai_lieu"] if d["stt"] == stt), "ho_so": info["ho_so"]}

    # ------------------------------------------------------------ xuất 1 hồ sơ
    @app.get("/api/ho-so/{ho_so_id}/xuat/{kieu}")
    def xuat(ho_so_id: int, kieu: str):
        info = load(ho_so_id)
        if not info["tai_lieu"]:
            raise HTTPException(400, "Hồ sơ chưa có tài liệu nào — hãy xử lý trước")
        ma = _safe(info["ho_so"]["ma_ho_so"])
        out = ho_so_dir(ho_so_id) / "xuat"
        shutil.rmtree(out, ignore_errors=True)
        if kieu == "xlsx":
            return _download(export_xlsx(info, out / f"{ma}.xlsx"), XLSX)
        if kieu == "csv":
            return _download(export_csv(info, out / f"{ma}.csv"), "text/csv; charset=utf-8")
        if kieu == "pdf":
            try:
                files = split_to_files(info["nguon_pdf"], info["tai_lieu"], out / "tai_lieu",
                                       copy_whole=info["tu_thu_muc"])
            except SourceMissing as e:
                raise HTTPException(400, str(e)) from None
            z = out / f"{ma}_tai_lieu_pdf.zip"
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    zf.write(f, f.name)
            return _download(z, "application/zip")
        raise HTTPException(404, "Kiểu xuất phải là xlsx, csv hoặc pdf")

    # ------------------------------------------------------------ xuất nhiều hồ sơ
    @app.get("/api/xuat/{kieu}")
    def xuat_nhieu(kieu: str, ids: str | None = None, lo: str | None = None, q: str | None = None,
                   trang_thai: str | None = None):
        """kieu = xlsx: 1 file gộp mọi tài liệu của các hồ sơ (xếp theo hồ sơ); xlsx-zip: mỗi hồ sơ 1 file Excel.
        Hồ sơ chưa có tài liệu (chưa xử lý) không có trong file."""
        if kieu not in ("xlsx", "xlsx-zip"):
            raise HTTPException(404, "Kiểu xuất phải là xlsx hoặc xlsx-zip")
        chosen = selection(ids=ids, lo=lo, q=q, trang_thai=trang_thai)
        infos = (db.load_ho_so(i) for i in chosen)
        out = DATA_DIR / "xuat_gop"
        shutil.rmtree(out, ignore_errors=True)
        name = _safe(lo if lo and lo != "-" else "nhieu_ho_so")
        stamp = time.strftime("%Y%m%d_%H%M")
        if kieu == "xlsx":
            count = {"ho_so": 0}

            def docs():
                for info in infos:
                    if info["tai_lieu"]:
                        count["ho_so"] += 1
                        yield from info["tai_lieu"]

            p = write_xlsx(docs(), out / f"{name}_{stamp}.xlsx")
            if not count["ho_so"]:
                raise HTTPException(400, "Chưa có hồ sơ nào được xử lý trong các hồ sơ đã chọn")
            return _download(p, XLSX)
        z = out / f"{name}_{stamp}_moi_ho_so_1_file.zip"
        z.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        used: set[str] = set()
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for info in infos:
                if not info["tai_lieu"]:
                    continue
                fname = f"{_safe(info['ho_so']['ma_ho_so'])}.xlsx"
                while fname in used:
                    fname = fname[:-5] + "_.xlsx"
                used.add(fname)
                p = write_xlsx(info["tai_lieu"], out / "tam" / fname)
                zf.write(p, fname)
                p.unlink()
                n += 1
        if not n:
            raise HTTPException(400, "Chưa có hồ sơ nào được xử lý trong các hồ sơ đã chọn")
        return _download(z, "application/zip")

    # ------------------------------------------------------------ hàng đợi
    @app.get("/api/hang-doi")
    def hang_doi():
        return jobs.summary(limit=100)

    @app.post("/api/hang-doi/tam-dung")
    def tam_dung():
        jobs.pause()
        return jobs.summary(limit=0)

    @app.post("/api/hang-doi/tiep-tuc")
    def tiep_tuc():
        jobs.resume()
        return jobs.summary(limit=0)

    @app.post("/api/hang-doi/them")
    def them_hang_doi(body: dict = Body(...)):
        """Xếp nhiều hồ sơ. Giữ cách tách tài liệu hiện có; hồ sơ chưa xử lý lần nào: mỗi file 1 tài liệu
        (xem pipeline.default_starts). chi_chua_ai: chỉ hồ sơ còn văn bản chưa chạy AI (vd. lô đã chạy
        'bỏ qua AI'), và văn bản nào AI đã đọc xong thì không đọc lại."""
        ids = []
        for i in selection(body):
            info = db.load_ho_so(i)
            if not info["nguon_pdf"]:
                continue
            if body.get("chi_chua_ai") and info["tai_lieu"] and all(
                    d.get("ai_trang_thai") == "xong" for d in info["tai_lieu"]):
                continue  # đã chạy AI đủ cả rồi
            ids.append(i)
        params = {"khong_llm": bool(body.get("khong_llm")), "tiep_tuc": bool(body.get("chi_chua_ai"))}
        return {"da_xep": jobs.submit_many(ids, "xu_ly", params, uu_tien=0)}

    @app.post("/api/hang-doi/bo")
    def bo_hang_doi(body: dict = Body(...)):
        return {"da_bo": jobs.cancel_waiting(selection(body))}

    # ------------------------------------------------------------ nhập thư mục
    @app.post("/api/nhap/chon-thu-muc")
    def chon_thu_muc(body: dict | None = Body(None)):
        try:
            return {"duong_dan": batch.pick_folder(str((body or {}).get("ban_dau", "")))}
        except RuntimeError as e:
            raise HTTPException(501, str(e)) from None

    @app.post("/api/nhap/quet")
    def quet(body: dict = Body(...)):
        path = str(body.get("duong_dan", "")).strip().strip('"')
        if not path:
            raise HTTPException(400, "Cần đường dẫn thư mục")
        return {"id": scans.start(path)}

    @app.get("/api/nhap/quet/{scan_id}")
    def quet_tien_do(scan_id: int):
        item = scans.get(scan_id)
        if item is None:
            raise HTTPException(404, "Không có lần quét này (app đã khởi động lại?) — hãy quét lại")
        return item

    @app.post("/api/nhap/tao", status_code=201)
    def nhap_tao(body: dict = Body(...)):
        item = scans.get(int(body.get("quet_id", 0)))
        if item is None or not item.get("ket_qua"):
            raise HTTPException(404, "Không có kết quả quét — hãy quét lại thư mục")
        created, errors = batch.create_from_scan(
            item["ket_qua"], body.get("chon", []), body.get("phong", {}), body.get("ho_so", {}),
            str(body.get("lo") or item["ket_qua"]["ten_lo"]).strip(), bool(body.get("khong_llm")),
        )
        return {"da_tao": len(created), "ids": created, "loi": errors}

    # ------------------------------------------------------------ giao diện đã build
    if frontend_dir and frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="ui")

    return app
