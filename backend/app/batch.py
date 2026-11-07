"""Nhập cả một thư mục hồ sơ đã số hóa.

Cấu trúc thường gặp (người dùng mô tả):
    Đà Lạt 1L/            <- thư mục chọn (= 1 "lô")
        1/                <- MỖI THƯ MỤC CÓ FILE PDF = 1 HỒ SƠ (ở cấp nào cũng được)
            H01.15.01.1.pdf          <- MỖI FILE PDF = 1 TÀI LIỆU (ranh giới theo file, app không tự chia)
            H01.15.01.100001.pdf
        2/ ...

Những gì app CHỈ GỢI Ý (người dùng sửa / quyết định ở bảng xem trước):
- Mã hồ sơ: phần giống nhau ở đầu tên các file (vd. H01.15.01); không có thì tên thư mục cha + thư mục con.
- File gộp: file mà nội dung từng trang trùng với các trang của >= 2 file khác cùng thư mục
  (vd. …1.pdf = …100001.pdf + …100002.pdf). App KHÔNG tự bỏ file nào; vẫn để tích sẵn.

App đọc thẳng file gốc trên máy, không sao chép (hàng nghìn file sẽ tốn gấp đôi ổ cứng).
"""

from __future__ import annotations

import hashlib
import itertools
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pymupdf

from app import db
from app.sources import pdf_lock

SEPS = "._- "
MAX_FILES = 100_000
SKIP_DIRS = {"$recycle.bin", "system volume information", "__macosx"}
THUMB_W, THUMB_H = 48, 68  # ảnh nhỏ để so 2 trang có cùng nội dung không (khi file gộp bị lưu lại)
THUMB_DIFF = 6.0  # chênh lệch trung bình mức xám (0–255, đã tăng tương phản) tối đa để coi là cùng một trang


def natural_key(s: str):
    """'2' < '10', 'a1' < 'a2' < 'a10' — sắp xếp như File Explorer của Windows."""
    return [(0, int(t), t) if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", s) if t]


# ------------------------------------------------------------------ mã hồ sơ
def common_code(stems: list[str]) -> str:
    """Phần đầu giống nhau của tên các file, cắt tại ký tự ngăn cách (. _ - khoảng trắng).

    ['H01.15.01.1', 'H01.15.01.100001'] -> 'H01.15.01'. Ít hơn 2 file / không có phần chung -> ''."""
    if len(stems) < 2:
        return ""
    pre = os.path.commonprefix(stems)
    while pre and not all(len(s) == len(pre) or s[len(pre)] in SEPS for s in stems):
        pre = pre[:-1]
    pre = pre.strip(SEPS)
    return pre if len(pre) >= 2 and any(c.isalnum() for c in pre) else ""


def folder_code(root: Path, folder: Path) -> str:
    rel = folder.relative_to(root).parts
    return ".".join([root.name, *rel]) if rel else root.name


# ------------------------------------------------------------------ dấu vân tay trang (tìm file gộp)
def page_fingerprint(doc: pymupdf.Document, page: pymupdf.Page) -> str:
    """Giống hệt từng byte ảnh scan (file gộp tạo bằng cách ghép PDF giữ nguyên ảnh) -> cùng dấu vân tay.
    Rất nhanh: không giải nén ảnh."""
    imgs = page.get_images(full=True)
    if imgs:
        xref, _smask, w, h = max(imgs, key=lambda im: im[2] * im[3])[:4]
        return f"i{w}x{h}:" + hashlib.md5(doc.xref_stream_raw(xref)).hexdigest()
    return "c:" + hashlib.md5(page.read_contents()).hexdigest()


def page_thumb(page: pymupdf.Page) -> bytes:
    from PIL import Image, ImageOps

    z = 2 * min(THUMB_W / max(page.rect.width, 1), THUMB_H / max(page.rect.height, 1))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY, alpha=False)
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples).resize((THUMB_W, THUMB_H), Image.BOX)
    return ImageOps.autocontrast(im).tobytes()


def thumb_diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / max(len(a), 1)


def is_concatenation(m: list[bytes], parts: list[list[bytes]]) -> bool:
    """Các trang của m giống lần lượt các trang của parts ghép nối (theo thứ tự tên file)."""
    flat = [t for p in parts for t in p]
    if len(flat) != len(m):
        return False
    for a, b in zip(m, flat):
        d = thumb_diff(a, b)
        if d > THUMB_DIFF or d > min(thumb_diff(a, c) for c in flat) + 1.0:
            return False
    return True


def find_merged(files: list[dict], prints: dict[int, list], same) -> dict[int, list[int]]:
    """{chỉ số file gộp: [chỉ số các file mà nó trùng nội dung]}.

    File M được gợi ý là bản gộp khi: M có >= 2 trang, MỌI trang của M trùng với một trang của file khác,
    và các trang đó đến từ >= 2 file khác (file thành phần chỉ trùng với mỗi M -> không bị gợi ý)."""
    out = {}
    for m, fm in enumerate(files):
        if m not in prints or len(prints[m]) < 2:
            continue
        owners = set()
        for p in prints[m]:
            hit = next((o for o, ps in prints.items() if o != m and any(same(p, q) for q in ps)), None)
            if hit is None:
                break
            owners.add(hit)
        else:
            if len(owners) >= 2:
                out[m] = sorted(owners)
    return out


def merged_suggestions(folder_files: list[dict]) -> None:
    """Đánh dấu file có vẻ là bản gộp (thêm khóa 'goi_y_gop'). Chỉ xét thư mục có >= 3 file đọc được."""
    files = [f for f in folder_files if not f.get("loi")]
    if len(files) < 3:
        return
    exact = {i: f["_dau"] for i, f in enumerate(files) if f.get("_dau")}
    found = find_merged(files, exact, lambda a, b: a == b)
    if not found:
        # File gộp đã bị lưu lại (ảnh nén lại, khác từng byte): chỉ xét đúng kiểu người dùng mô tả
        # "1 file = các file còn lại ghép lại" (số trang bằng tổng các file kia) rồi so ảnh nhỏ từng trang.
        total = sum(f["so_trang"] for f in files)
        cands = [i for i, f in enumerate(files) if f["so_trang"] >= 2 and 2 * f["so_trang"] == total]
        if cands:
            thumbs: dict[int, list[bytes]] = {}
            for i, f in enumerate(files):
                try:
                    with pdf_lock, pymupdf.open(f["duong_dan"]) as d:
                        thumbs[i] = [page_thumb(p) for p in d]
                except Exception:  # noqa: BLE001
                    thumbs = {}
                    break
            for m in cands:
                others = [i for i in range(len(files)) if i != m]
                if thumbs and is_concatenation(thumbs[m], [thumbs[i] for i in others]):
                    found[m] = others
    for m, owners in found.items():
        files[m]["goi_y_gop"] = [files[o]["ten"] for o in owners]


# ------------------------------------------------------------------ quét thư mục
def _pdf_info(path: Path, fingerprints: bool = False) -> dict:
    info = {"ten": path.name, "duong_dan": str(path), "dung_luong": 0, "so_trang": 0, "loi": ""}
    try:
        info["dung_luong"] = path.stat().st_size
        with pdf_lock, pymupdf.open(path) as d:
            if d.needs_pass:
                info["loi"] = "PDF đặt mật khẩu"
            else:
                info["so_trang"] = d.page_count
                if not d.page_count:
                    info["loi"] = "PDF không có trang nào"
                elif fingerprints:
                    info["_dau"] = [page_fingerprint(d, p) for p in d]
    except Exception:  # noqa: BLE001
        info["loi"] = "File hỏng hoặc không phải PDF"
    return info


def scan(root: Path, progress=None) -> dict:
    """Đọc cấu trúc thư mục -> bảng xem trước. progress(đã đọc, tổng số file)."""
    root = Path(os.path.expandvars(str(root).strip().strip('"'))).expanduser()
    if not root.is_dir():
        raise ValueError(f"Không thấy thư mục: {root}")
    root = root.resolve()
    groups: list[tuple[Path, list[str]]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted((d for d in dirnames if not d.startswith((".", "~")) and d.lower() not in SKIP_DIRS),
                             key=natural_key)
        pdfs = sorted((f for f in filenames if f.lower().endswith(".pdf") and not f.startswith("~$")), key=natural_key)
        if pdfs:
            groups.append((Path(dirpath), pdfs))
    n_files = sum(len(p) for _, p in groups)
    if n_files == 0:
        raise ValueError("Thư mục này (và các thư mục con) không có file PDF nào")
    if n_files > MAX_FILES:
        raise ValueError(f"Quá nhiều file ({n_files}). Hãy chọn thư mục nhỏ hơn (tối đa {MAX_FILES} file).")

    done = 0
    imported = db.imported_folders()
    folders = []
    for folder, names in groups:
        files = []
        for name in names:
            files.append(_pdf_info(folder / name, fingerprints=len(names) >= 3))
            done += 1
            if progress:
                progress(done, n_files)
        merged_suggestions(files)
        for f in files:
            f.pop("_dau", None)
        stems = [Path(f["ten"]).stem for f in files]
        code = common_code(stems)
        prev = imported.get(str(folder).lower())
        folders.append({
            "thu_muc": str(folder),
            "ten": str(folder.relative_to(root)) if folder != root else folder.name,
            "ma_goi_y": code or folder_code(root, folder),
            "ma_tu": "ten_file" if code else "thu_muc",
            "files": files,
            "da_nhap": {"id": prev[0], "ma_ho_so": prev[1]} if prev else None,
        })

    # Mã trùng giữa các thư mục trong lô (vd. mọi thư mục đều có file 'Scan_0001.pdf') -> dùng tên thư mục.
    counts: dict[str, int] = {}
    for f in folders:
        counts[f["ma_goi_y"]] = counts.get(f["ma_goi_y"], 0) + 1
    for f in folders:
        if counts[f["ma_goi_y"]] > 1 and f["ma_tu"] == "ten_file":
            f["ma_goi_y"], f["ma_tu"] = folder_code(root, Path(f["thu_muc"])), "thu_muc_vi_trung"
    taken = db.existing_codes([f["ma_goi_y"] for f in folders])
    for f in folders:
        f["ma_da_co"] = f["ma_goi_y"] in taken

    return {
        "thu_muc": str(root),
        "ten_lo": root.name,
        "so_ho_so": len(folders),
        "so_file": n_files,
        "so_trang": sum(x["so_trang"] for f in folders for x in f["files"]),
        "so_file_goi_y_gop": sum(1 for f in folders for x in f["files"] if x.get("goi_y_gop")),
        "ho_so": folders,
    }


class Scans:
    """Quét chạy ở luồng nền (hàng nghìn file mất vài chục giây), giao diện hỏi tiến độ."""

    def __init__(self):
        self._items: dict[int, dict] = {}
        self._ids = itertools.count(1)

    def start(self, path: str) -> int:
        sid = next(self._ids)
        item = {"id": sid, "xong": False, "loi": "", "da_doc": 0, "tong": 0, "ket_qua": None, "luc": time.time()}
        self._items[sid] = item

        def run():
            try:
                item["ket_qua"] = scan(Path(path), lambda d, t: item.update(da_doc=d, tong=t))
            except ValueError as e:
                item["loi"] = str(e)
            except Exception as e:  # noqa: BLE001
                item["loi"] = f"Lỗi khi đọc thư mục: {e.__class__.__name__}: {e}"
            finally:
                item["xong"] = True

        threading.Thread(target=run, daemon=True, name=f"quet-{sid}").start()
        for old in [k for k, v in self._items.items() if time.time() - v["luc"] > 6 * 3600]:
            self._items.pop(old, None)  # bỏ kết quả quét cũ
        return sid

    def get(self, sid: int) -> dict | None:
        return self._items.get(sid)


def create_from_scan(result: dict, chon: list[dict], phong: dict, ho_so_chung: dict, lo: str,
                     khong_llm: bool) -> tuple[list[int], list[dict]]:
    """Tạo hàng loạt hồ sơ từ kết quả quét + lựa chọn của người dùng.

    chon = [{'i': chỉ số thư mục trong kết quả quét, 'ma_ho_so', 'tieu_de_ho_so', 'files': [chỉ số file]}].
    Trả về (id các hồ sơ đã tạo theo đúng thứ tự thư mục, lỗi từng thư mục)."""
    created, errors = [], []
    pending = []
    with db.connect() as conn:
        for c in chon:
            folder = result["ho_so"][int(c["i"])]
            files = [folder["files"][int(k)] for k in c.get("files", [])]
            files = [f for f in files if not f["loi"] and f["so_trang"] > 0]
            ma = (c.get("ma_ho_so") or "").strip()
            if not files:
                errors.append({"thu_muc": folder["ten"], "loi": "Không có file PDF nào được chọn"})
                continue
            ds = [{"duong_dan": f["duong_dan"], "ten": f["ten"], "so_trang": f["so_trang"]} for f in files]
            fields = {**ho_so_chung, "ma_ho_so": ma, "tieu_de_ho_so": (c.get("tieu_de_ho_so") or "").strip(),
                      "tep_tin_ho_so": Path(folder["thu_muc"]).name}
            try:
                hid = db.create_ho_so(phong, fields, conn=conn, lo=lo, thu_muc=folder["thu_muc"], ds_pdf=ds)
            except ValueError as e:
                errors.append({"thu_muc": folder["ten"], "loi": str(e)})
                continue
            starts, page = [], 1
            for f in ds:  # mỗi file = 1 tài liệu: trang đầu của mỗi file là ranh giới
                starts.append(page)
                page += f["so_trang"]
            created.append(hid)
            pending.append((hid, starts))
    for hid, starts in pending:
        db.enqueue([hid], {"kind": "xu_ly", "ranh_gioi": starts, "khong_llm": bool(khong_llm)}, uu_tien=0)
    return created, errors


# ------------------------------------------------------------------ hộp chọn thư mục của Windows
PICKER = r"""
import sys, tkinter as tk
from tkinter import filedialog
r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True); r.update()
p = filedialog.askdirectory(parent=r, title='Chọn thư mục chứa hồ sơ đã số hóa', initialdir=sys.argv[1] or None, mustexist=True)
r.destroy()
sys.stdout.write(p or '')
"""


def pick_folder(initial: str = "") -> str:
    """Mở hộp chọn thư mục của hệ điều hành (chạy riêng 1 tiến trình). '' = người dùng bấm Hủy.
    Lỗi (máy không có tkinter / không có màn hình) -> RuntimeError: giao diện bảo dán đường dẫn."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        r = subprocess.run([sys.executable, "-c", PICKER, initial], capture_output=True, timeout=1800, env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"Không mở được hộp chọn thư mục: {e}") from None
    if r.returncode != 0:
        raise RuntimeError("Không mở được hộp chọn thư mục trên máy này — hãy dán đường dẫn thư mục vào ô.")
    return str(Path(r.stdout.decode("utf-8", "replace").strip())) if r.stdout.strip() else ""
