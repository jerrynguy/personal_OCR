"""Các file PDF của một hồ sơ, xem như MỘT dãy trang liên tục.

- Hồ sơ tải lên: 1 file (data/ho_so/<id>/goc.pdf).
- Hồ sơ nhập từ thư mục: nhiều file gốc nằm nguyên chỗ trên máy người dùng (không sao chép, đỡ tốn ổ cứng);
  trang 1 của file 2 là trang (số trang file 1 + 1) của hồ sơ.

sources = info['nguon_pdf'] = [{'duong_dan', 'ten', 'so_trang', 'trang_dau'}] (xem db._sources).
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pymupdf

# MuPDF KHÔNG an toàn khi nhiều luồng dùng cùng lúc (luồng xử lý, luồng quét thư mục, các request vẽ ảnh
# thu nhỏ...). Mọi thao tác với PDF đều đi qua khóa này; mỗi lần giữ khóa chỉ ngắn (1 trang / 1 file).
pdf_lock = threading.RLock()


class SourceMissing(FileNotFoundError):
    pass


class PdfSet:
    """Mở file nguồn khi cần (chỉ giữ 1 file mở: các trang thường được đọc lần lượt)."""

    def __init__(self, sources: list[dict]):
        self.sources = sources
        self._path: str | None = None
        self._doc: pymupdf.Document | None = None

    @property
    def page_count(self) -> int:
        return sum(int(s["so_trang"]) for s in self.sources)

    def locate(self, n: int) -> tuple[dict, int]:
        """Trang n của hồ sơ (từ 1) -> (file nguồn, chỉ số trang trong file, từ 0)."""
        for s in self.sources:
            if s["trang_dau"] <= n < s["trang_dau"] + int(s["so_trang"]):
                return s, n - s["trang_dau"]
        raise IndexError(f"Không có trang {n}")

    def _open(self, path: str) -> pymupdf.Document:
        with pdf_lock:
            return self._open_locked(path)

    def _open_locked(self, path: str) -> pymupdf.Document:
        if path != self._path:
            self.close()
            if not Path(path).exists():
                raise SourceMissing(
                    f"Không thấy file {Path(path).name} (đường dẫn {path}). "
                    "File gốc đã bị di chuyển, đổi tên hoặc xóa? Hãy để file về đúng chỗ rồi xử lý lại."
                )
            self._doc = pymupdf.open(path)
            if self._doc.needs_pass:
                raise ValueError(f"PDF {Path(path).name} đang đặt mật khẩu")
            self._path = path
        return self._doc

    def page(self, n: int) -> pymupdf.Page:
        src, idx = self.locate(n)
        return self._open(src["duong_dan"])[idx]

    def render(self, n: int, out: Path, dpi: int = 300) -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        with pdf_lock:
            self.page(n).get_pixmap(dpi=dpi, alpha=False).save(out)
        return out

    def render_jpeg(self, n: int, out: Path, width: int) -> Path:
        """Ảnh JPEG rộng `width` px của trang (xem trước / ảnh thu nhỏ), vẽ thẳng từ PDF."""
        out.parent.mkdir(parents=True, exist_ok=True)
        with pdf_lock:
            page = self.page(n)
            z = width / max(page.rect.width, 1)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            pix.save(out, jpg_quality=80) if out.suffix.lower() in (".jpg", ".jpeg") else pix.save(out)
        return out

    def close(self) -> None:
        with pdf_lock:
            if self._doc is not None:
                self._doc.close()
            self._doc, self._path = None, None

    def __enter__(self) -> "PdfSet":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def page_range(trang_pdf: str) -> tuple[int, int]:
    a, _, b = str(trang_pdf).partition("-")
    return int(a), int(b or a)


def whole_source(sources: list[dict], trang_pdf: str) -> dict | None:
    """Tài liệu chiếm trọn đúng 1 file nguồn (vd. nhập thư mục: mỗi file 1 tài liệu) -> file đó."""
    a, b = page_range(trang_pdf)
    for s in sources:
        if s["trang_dau"] == a and s["trang_dau"] + int(s["so_trang"]) - 1 == b:
            return s
    return None


def missing_files(sources: list[dict]) -> list[str]:
    return [s["ten"] for s in sources if not Path(s["duong_dan"]).exists()]


def split_to_files(sources: list[dict], docs: list[dict], out_dir: Path, copy_whole: bool = False) -> list[Path]:
    """Tách thành từng tệp tài liệu (tên tệp = cột 'Tệp tin tài liệu').

    copy_whole: tài liệu trùng đúng 1 file gốc -> chép nguyên file gốc (không ghi lại, giữ nguyên chất lượng)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with pdf_lock, PdfSet(sources) as pdfs:
        for d in docs:
            dest = out_dir / d["tep_tin_tai_lieu"]
            src = whole_source(sources, d["trang_pdf"]) if copy_whole else None
            if src is not None and Path(src["duong_dan"]).exists():
                shutil.copyfile(src["duong_dan"], dest)
                paths.append(dest)
                continue
            a, b = page_range(d["trang_pdf"])
            out = pymupdf.open()
            for n in range(a, b + 1):
                s, idx = pdfs.locate(n)
                out.insert_pdf(pdfs._open(s["duong_dan"]), from_page=idx, to_page=idx)
            out.save(dest, deflate=True)
            out.close()
            paths.append(dest)
    return paths
