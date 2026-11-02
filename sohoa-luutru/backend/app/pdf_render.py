"""Tách PDF scan nhiều trang thành ảnh PNG từng trang."""

from pathlib import Path

import pymupdf


def parse_page_range(spec: str | None, page_count: int) -> list[int]:
    """'1-3,5' -> [0, 1, 2, 4] (chỉ số bắt đầu từ 0). None -> tất cả trang."""
    if not spec:
        return list(range(page_count))
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        for p in range(start, end + 1):
            if 1 <= p <= page_count:
                pages.add(p - 1)
    return sorted(pages)


def render_pdf(
    pdf_path: Path, out_dir: Path, dpi: int = 300, pages: str | None = None
) -> list[Path]:
    """Render từng trang PDF thành page_001.png, page_002.png... trong out_dir.

    300 DPI là mức chuẩn cho OCR văn bản hành chính (chữ cỡ 13–14).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise ValueError("PDF đang bị đặt mật khẩu, hãy gỡ mật khẩu trước.")
        for idx in parse_page_range(pages, doc.page_count):
            pix = doc[idx].get_pixmap(dpi=dpi, alpha=False)
            img_path = out_dir / f"page_{idx + 1:03d}.png"
            pix.save(img_path)
            result.append(img_path)
    return result


def pdf_page_count(pdf_path: Path) -> int:
    with pymupdf.open(pdf_path) as doc:
        return doc.page_count
