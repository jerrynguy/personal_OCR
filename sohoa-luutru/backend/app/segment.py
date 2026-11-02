"""Tách PDF nhiều trang thành từng văn bản.

Một trang là TRANG ĐẦU của văn bản mới nếu vùng đầu trang có quốc hiệu
('CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM' / 'Độc lập - Tự do - Hạnh phúc') hoặc dòng 'Số: ...'.
Các trang còn lại được nối vào văn bản phía trước. Người dùng sửa lại ở màn soát nếu sai.
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
