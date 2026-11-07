"""Tách PDF nhiều trang thành từng văn bản.

App KHÔNG tự tách theo nội dung (người dùng đã chốt: tự tách chia sai với file gộp nhiều thứ, vd. nghị định
kèm phụ lục). Ranh giới do người dùng đánh dấu -> split_by_boundaries().

is_first_page() chỉ dùng để GỢI Ý trên màn "Tách văn bản" (người dùng bấm xác nhận): trang có quốc hiệu
('CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM' / 'Độc lập - Tự do - Hạnh phúc') hoặc dòng 'Số: ...' ở đầu trang.
split_documents() (tự tách) chỉ còn dùng cho script dòng lệnh Bước 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ocr import OcrPage
from app.rules import find_so_ky_hieu, has_quoc_hieu


@dataclass
class Document:
    pages: list[OcrPage] = field(default_factory=list)
    page_numbers: list[int] = field(default_factory=list)  # số trang trong PDF, bắt đầu từ 1

    @property
    def page_range(self) -> str:
        a, b = self.page_numbers[0], self.page_numbers[-1]
        return str(a) if a == b else f"{a}-{b}"


def is_first_page(page: OcrPage) -> bool:
    return has_quoc_hieu(page) or find_so_ky_hieu(page) is not None


def split_documents(pages: list[OcrPage], page_numbers: list[int] | None = None) -> list[Document]:
    page_numbers = page_numbers or list(range(1, len(pages) + 1))
    docs: list[Document] = []
    for page, no in zip(pages, page_numbers):
        if not docs or is_first_page(page):
            docs.append(Document())
        docs[-1].pages.append(page)
        docs[-1].page_numbers.append(no)
    return docs


def split_by_boundaries(pages: list[OcrPage], page_numbers: list[int], starts: list[int]) -> list[Document]:
    """Tách theo danh sách trang bắt đầu văn bản do người dùng chỉ định (số trang PDF)."""
    starts_set = set(starts)
    docs: list[Document] = []
    for page, no in zip(pages, page_numbers):
        if not docs or no in starts_set:
            docs.append(Document())
        docs[-1].pages.append(page)
        docs[-1].page_numbers.append(no)
    return docs


def text_layer_page(page) -> OcrPage | None:
    """Trang PDF có sẵn lớp chữ (PDF tạo từ Word, hoặc máy scan đã nhận dạng chữ) -> dùng để gợi ý
    trang đầu ngay, không cần OCR. Không có chữ -> None."""
    from app.ocr import OcrLine

    lines = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = " ".join(s["text"] for s in line.get("spans", [])).strip()
            if text:
                x0, y0, x1, y1 = (int(v) for v in line["bbox"])
                lines.append(OcrLine(text, 1.0, [x0, y0, x1, y1], [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]))
    if sum(len(l.text) for l in lines) < 20:
        return None
    return OcrPage("", int(page.rect.width), int(page.rect.height), 0, lines)
