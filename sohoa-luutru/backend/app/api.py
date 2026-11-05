"""API cho giao diện (Bước 6). Chỉ nghe 127.0.0.1; mọi request /api/* (trừ /api/health) phải
kèm token: header 'X-Token: <token>' hoặc '?token=<token>' (dùng cho ảnh / tải file).

Tóm tắt:
  GET    /api/health                         sống chưa (không cần token)
  GET    /api/he-thong                       model nào đã có / đang nạp, hàng đợi
  GET    /api/schema                         danh sách trường TT05 (để vẽ form)
  GET    /api/ho-so                          danh sách hồ sơ
  POST   /api/ho-so                          tạo hồ sơ {phong:{...}, ho_so:{...}}
  GET    /api/ho-so/{id}                     chi tiết: phông, hồ sơ, tài liệu, trạng thái
  PUT    /api/ho-so/{id}                     sửa thông tin phông / hồ sơ
  DELETE /api/ho-so/{id}                     xóa hồ sơ (cả file)
  POST   /api/ho-so/{id}/pdf                 tải PDF lên (multipart, trường 'file')
  POST   /api/ho-so/{id}/xu-ly               bắt đầu xử lý {ocr_lai?, ranh_gioi?: [trang bắt đầu...]}
  GET    /api/ho-so/{id}/tien-do             tiến độ lần xử lý gần nhất
  POST   /api/xu-ly/{job_id}/huy             hủy
  GET    /api/ho-so/{id}/trang               danh sách trang
  GET    /api/ho-so/{id}/trang/{n}/anh       ảnh trang (PNG)
  GET    /api/ho-so/{id}/trang/{n}/ocr       các dòng chữ + toạ độ (để tô sáng trên ảnh)
  PUT    /api/ho-so/{id}/tai-lieu/{stt}      sửa tay {thay_doi: {...}, da_soat?: bool}
  GET    /api/ho-so/{id}/xuat/xlsx|csv|pdf   tải file xuất (csv, pdf là .zip)
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import pymupdf
from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.config import ACTIVE_LLM_FILE, DET_MODELS, DOC_ORI_MODEL, VIETOCR_MODELS, paddle_model_dir, vietocr_weights_path
from app.export import export_csv, export_xlsx, split_pdf
from app.jobs import JobQueue
from app.config import DEFAULT_LLM_NAME, LLM_DIR
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
from app.pipeline import clear_pages, ho_so_dir, ocr_cache, pages_dir, refresh_ho_so, run_job
from app.services import LlmService, OcrService, warm_up
from app.winperf import disable_power_throttling, power_status
from app.tt05 import load_schema

MAX_PDF_MB = 500


def _safe(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", s).strip() or "ho_so"


def _public(info: dict) -> dict:
    """Bỏ đường dẫn tuyệt đối trên máy khỏi dữ liệu trả về giao diện."""
    out = dict(info)
    out["co_pdf"] = bool(info.get("tep_pdf")) and Path(info["tep_pdf"]).exists()
    out["ten_pdf"] = Path(info["tep_pdf"]).name if info.get("tep_pdf") else ""
    out.pop("tep_pdf", None)
    return out


def create_app(token: str | None = None, dev: bool = False, ocr_factory=None,
               frontend_dir: Path | None = None, warmup: bool = True) -> FastAPI:
    token = token if token is not None else secrets.token_urlsafe(24)
    ocr = OcrService(ocr_factory)
    llm = LlmService()
    jobs = JobQueue(lambda job: run_job(job, ocr, llm))

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
        j = jobs.latest_for(ho_so_id)
        return j is not None and not j.done

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
            "hang_doi": [j.to_dict() for j in jobs.active()],
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
            raise HTTPException(409, "Đang có hồ sơ xử lý — chờ xong rồi đổi model")
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
    def ds_ho_so():
        rows = db.list_ho_so()
        for r in rows:
            r["ten_pdf"] = Path(r.pop("tep_pdf") or "").name
        return rows

    @app.post("/api/ho-so", status_code=201)
    def tao_ho_so(body: dict = Body(...)):
        try:
            new_id = db.create_ho_so(body.get("phong", {}), body.get("ho_so", {}))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return _public(db.load_ho_so(new_id))

    @app.get("/api/ho-so/{ho_so_id}")
    def chi_tiet(ho_so_id: int):
        info = _public(load(ho_so_id))
        j = jobs.latest_for(ho_so_id)
        info["tien_do"] = j.to_dict() if j else None
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
        db.delete_ho_so(ho_so_id)
        shutil.rmtree(ho_so_dir(ho_so_id), ignore_errors=True)

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
            with pymupdf.open(tmp) as d:
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
        return {"so_trang": so_trang, "ten_file": file.filename, "canh_bao": low_dpi_warning(dest)}

    @app.post("/api/ho-so/{ho_so_id}/xu-ly", status_code=202)
    def xu_ly(ho_so_id: int, body: dict | None = Body(None)):
        info = load(ho_so_id)
        if not info["tep_pdf"]:
            raise HTTPException(400, "Hồ sơ chưa có file PDF")
        params = {k: v for k, v in (body or {}).items() if k in ("ocr_lai", "ranh_gioi", "khong_llm")}
        if "ranh_gioi" in params:
            starts = sorted({int(x) for x in params["ranh_gioi"] if 1 <= int(x) <= info["so_trang"]})
            if not starts or starts[0] != 1:
                starts = [1, *starts]
            params["ranh_gioi"] = starts
        job = jobs.submit(ho_so_id, "xu_ly", params)
        if not job.started:
            db.set_status(ho_so_id, "cho")
        return job.to_dict()

    @app.get("/api/ho-so/{ho_so_id}/tien-do")
    def tien_do(ho_so_id: int):
        load(ho_so_id)
        j = jobs.latest_for(ho_so_id)
        return j.to_dict() if j else None

    @app.post("/api/xu-ly/{job_id}/huy")
    def huy(job_id: int):
        if not jobs.cancel(job_id):
            raise HTTPException(404, "Không có lần xử lý đang chạy với mã này")
        return {"ok": True}

    # ------------------------------------------------------------ trang (ảnh + OCR)
    def page_img(ho_so_id: int, n: int) -> Path:
        return pages_dir(ho_so_id) / f"page_{n:03d}.png"

    @app.get("/api/ho-so/{ho_so_id}/trang")
    def ds_trang(ho_so_id: int):
        info = load(ho_so_id)
        out = []
        for n in range(1, info["so_trang"] + 1):
            img = page_img(ho_so_id, n)
            out.append({"so": n, "co_anh": img.exists(), "co_ocr": ocr_cache(img).exists()})
        return out

    @app.get("/api/ho-so/{ho_so_id}/trang/{n}/anh")
    def anh_trang(ho_so_id: int, n: int, nho: bool = False):
        """Ảnh trang. nho=1 -> ảnh thu nhỏ (rộng 300px, JPEG) cho danh sách trang."""
        info = load(ho_so_id)
        if not 1 <= n <= info["so_trang"]:
            raise HTTPException(404, "Không có trang này")
        img = page_img(ho_so_id, n)
        if not img.exists():  # chưa xử lý -> render nhanh để xem trước
            img = img.with_suffix(".preview.png")
            if not img.exists():
                img.parent.mkdir(parents=True, exist_ok=True)
                with pymupdf.open(info["tep_pdf"]) as d:
                    d[n - 1].get_pixmap(dpi=150, alpha=False).save(img)
        if not nho:
            return FileResponse(img, media_type="image/png", headers={"Cache-Control": "no-cache"})
        thumb = img.with_name(img.stem.split(".")[0] + ".thumb.jpg")
        if not thumb.exists() or thumb.stat().st_mtime < img.stat().st_mtime:
            from PIL import Image

            with Image.open(img) as im:
                im = im.convert("RGB")
                im.thumbnail((300, 425))
                im.save(thumb, "JPEG", quality=80)
        return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})

    @app.get("/api/ho-so/{ho_so_id}/trang/{n}/ocr")
    def ocr_trang(ho_so_id: int, n: int):
        load(ho_so_id)
        cache = ocr_cache(page_img(ho_so_id, n))
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

    # ------------------------------------------------------------ xuất
    @app.get("/api/ho-so/{ho_so_id}/xuat/{kieu}")
    def xuat(ho_so_id: int, kieu: str):
        info = load(ho_so_id)
        if not info["tai_lieu"]:
            raise HTTPException(400, "Hồ sơ chưa có tài liệu nào — hãy xử lý trước")
        ma = _safe(info["ho_so"]["ma_ho_so"])
        out = ho_so_dir(ho_so_id) / "xuat"
        shutil.rmtree(out, ignore_errors=True)
        if kieu == "xlsx":
            p = export_xlsx(info, out / f"{ma}.xlsx")
            return FileResponse(p, filename=p.name,
                                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if kieu in ("csv", "pdf"):
            files = (export_csv(info, out / "csv", ma) if kieu == "csv"
                     else split_pdf(Path(info["tep_pdf"]), info["tai_lieu"], out / "tai_lieu"))
            z = out / f"{ma}_{kieu}.zip"
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    zf.write(f, f.name)
            return FileResponse(z, filename=z.name, media_type="application/zip")
        raise HTTPException(404, "Kiểu xuất phải là xlsx, csv hoặc pdf")

    # ------------------------------------------------------------ giao diện đã build (Bước 6–7)
    if frontend_dir and frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="ui")

    return app
