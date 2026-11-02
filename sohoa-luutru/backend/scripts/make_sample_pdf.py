"""Tạo một PDF "scan" mẫu (nội dung giả) để thử pipeline mà chưa cần dùng tài liệu thật.

    python scripts/make_sample_pdf.py
    -> data/samples/mau_ho_so.pdf  (3 trang ảnh, trang 3 bị lật ngược để thử tự xoay)
"""

import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR  # noqa: E402

FONT_CANDIDATES = [
    ("C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/timesbd.ttf"),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ),
    ("/Library/Fonts/Times New Roman.ttf", "/Library/Fonts/Times New Roman Bold.ttf"),
]

# Mỗi trang: danh sách (x, y, cỡ chữ, đậm?, căn giữa trong khoảng [x, x2]?, nội dung)
PAGES = [
    [
        (60, 60, 12, False, 260, "ỦY BAN NHÂN DÂN"),
        (60, 76, 12, True, 260, "TỈNH AN BÌNH"),
        (60, 104, 13, False, 260, "Số: 125/QĐ-UBND"),
        (270, 60, 12, True, 560, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"),
        (270, 76, 13, True, 560, "Độc lập - Tự do - Hạnh phúc"),
        (270, 104, 13, False, 560, "An Bình, ngày 15 tháng 3 năm 2025"),
        (60, 150, 14, True, 535, "QUYẾT ĐỊNH"),
        (60, 170, 14, True, 535, "Về việc thành lập Tổ công tác số hóa tài liệu lưu trữ"),
        (60, 200, 14, True, 535, "CHỦ TỊCH ỦY BAN NHÂN DÂN TỈNH AN BÌNH"),
        (80, 235, 13, False, None, "Căn cứ Luật Lưu trữ ngày 21 tháng 6 năm 2024;"),
        (80, 255, 13, False, None, "Căn cứ Thông tư số 05/2025/TT-BNV ngày 14 tháng 5 năm 2025;"),
        (80, 275, 13, False, None, "Theo đề nghị của Giám đốc Sở Nội vụ."),
        (60, 310, 14, True, 535, "QUYẾT ĐỊNH:"),
        (80, 340, 13, False, None, "Điều 1. Thành lập Tổ công tác số hóa tài liệu lưu trữ của tỉnh."),
        (80, 360, 13, False, None, "Điều 2. Tổ công tác có nhiệm vụ số hóa toàn bộ hồ sơ giai đoạn"),
        (60, 380, 13, False, None, "2015 - 2024 đang bảo quản tại Kho lưu trữ chuyên dụng."),
        (520, 800, 11, False, None, "1"),
    ],
    [
        (80, 70, 13, False, None, "Điều 3. Quyết định này có hiệu lực kể từ ngày ký."),
        (60, 120, 12, True, None, "Nơi nhận:"),
        (60, 136, 11, False, None, "- Như Điều 3;"),
        (60, 150, 11, False, None, "- Lưu: VT, NV."),
        (330, 120, 13, True, 560, "CHỦ TỊCH"),
        (330, 200, 13, True, 560, "Nguyễn Văn An"),
        (520, 800, 11, False, None, "2"),
    ],
    [
        (60, 60, 12, False, 260, "SỞ NỘI VỤ"),
        (60, 76, 12, True, 260, "TỈNH AN BÌNH"),
        (60, 104, 13, False, 260, "Số: 47/SNV-VTLT"),
        (60, 122, 11, False, 260, "V/v hướng dẫn chỉnh lý tài liệu"),
        (270, 60, 12, True, 560, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"),
        (270, 76, 13, True, 560, "Độc lập - Tự do - Hạnh phúc"),
        (270, 104, 13, False, 560, "An Bình, ngày 02 tháng 4 năm 2025"),
        (200, 170, 14, False, None, "Kính gửi: Các cơ quan, tổ chức thuộc nguồn nộp lưu."),
        (80, 210, 13, False, None, "Thực hiện Quyết định số 125/QĐ-UBND ngày 15/3/2025 của"),
        (60, 230, 13, False, None, "UBND tỉnh, Sở Nội vụ hướng dẫn chỉnh lý tài liệu như sau..."),
        (360, 300, 13, True, 560, "GIÁM ĐỐC"),
        (360, 380, 13, True, 560, "Trần Thị Bình"),
        (520, 800, 11, False, None, "3"),
    ],
]


def find_fonts() -> tuple[str, str]:
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            return regular, bold
    raise FileNotFoundError("Không tìm thấy font có dấu tiếng Việt (Times New Roman / DejaVu).")


def main() -> None:
    regular, bold = find_fonts()
    out_dir = DATA_DIR / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Dựng PDF chữ (A4)
    text_doc = pymupdf.open()
    for items in PAGES:
        page = text_doc.new_page(width=595, height=842)
        page.insert_font(fontname="reg", fontfile=regular)
        page.insert_font(fontname="bold", fontfile=bold)
        for x, y, size, is_bold, x2, text in items:
            font = "bold" if is_bold else "reg"
            if x2 is not None:
                w = pymupdf.Font(fontfile=bold if is_bold else regular).text_length(text, size)
                x = x + (x2 - x - w) / 2
            page.insert_text((x, y), text, fontname=font, fontsize=size)

    # 2) Chuyển thành PDF chỉ có ảnh (giống file scan), trang 3 lật ngược
    scan_doc = pymupdf.open()
    for i, page in enumerate(text_doc):
        pix = page.get_pixmap(dpi=200, alpha=False)
        new_page = scan_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, pixmap=pix, rotate=180 if i == 2 else 0)

    out_path = out_dir / "mau_ho_so.pdf"
    scan_doc.save(out_path, deflate=True)
    print(f"Đã tạo: {out_path}  ({scan_doc.page_count} trang, font: {Path(regular).name})")


if __name__ == "__main__":
    main()
