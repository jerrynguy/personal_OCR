"""Tạo dữ liệu thử (nội dung giả): thư mục 'Đà Lạt 1L' kiểu dữ liệu thật + 1 PDF dài nhiều tài liệu.

    python tests/tao_du_lieu_thu.py <thư mục ra>

Mỗi PDF là ảnh scan (không có lớp chữ), kèm <tên>.truth.json = các dòng chữ + toạ độ (pt) từng trang
để OCR giả trả về.
"""

import io
import json
import random
import shutil
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

OUT = Path(sys.argv[1])
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
W, H = 595, 842
DPI = 150
S = DPI / 72
random.seed(7)


def head(co_quan, so, ngay, loai, trich):
    return [
        (60, 60, 12, False, co_quan[0]), (60, 76, 12, True, co_quan[1]), (60, 104, 13, False, f"Số: {so}"),
        (290, 60, 11, True, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"), (320, 76, 12, True, "Độc lập - Tự do - Hạnh phúc"),
        (300, 104, 12, False, f"Đà Lạt, ngày {ngay[0]} tháng {ngay[1]} năm {ngay[2]}"),
        (230, 150, 14, True, loai), (110, 172, 13, True, trich),
    ]


BODY = [
    "Căn cứ Luật Lưu trữ ngày 21 tháng 6 năm 2024;",
    "Căn cứ Thông tư số 05/2025/TT-BNV ngày 14 tháng 5 năm 2025;",
    "Theo đề nghị của Trưởng phòng Nội vụ thành phố.",
    "Điều 1. Giao nhiệm vụ chỉnh lý, số hóa tài liệu lưu trữ của cơ quan.",
    "Điều 2. Thời gian thực hiện từ tháng 3 đến hết tháng 12 năm 2015.",
]


def doc_pages(kind, n_pages, i):
    so = f"{100 + i}/{'QĐ-UBND' if kind == 'QUYẾT ĐỊNH' else 'UBND-NV'}"
    day = (1 + i % 27, 1 + i % 12, 2015 + i % 3)
    trich = {"QUYẾT ĐỊNH": "Về việc chỉnh lý tài liệu lưu trữ năm 2015",
             "BÁO CÁO": "Kết quả công tác văn thư, lưu trữ năm 2015",
             "GIẤY KHEN": "Đã có thành tích xuất sắc trong công tác lưu trữ"}.get(kind, "V/v báo cáo số liệu lưu trữ")
    if kind == "CÔNG VĂN":
        first = head(("ỦY BAN NHÂN DÂN", "THÀNH PHỐ ĐÀ LẠT"), so, day, "", trich)
        first = [l for l in first if l[4]]
    else:
        first = head(("ỦY BAN NHÂN DÂN", "THÀNH PHỐ ĐÀ LẠT"), so, day, kind, trich)
    first += [(80, 215 + 22 * k, 12, False, t) for k, t in enumerate(BODY)]
    pages = [first]
    for p in range(1, n_pages):
        lines = [(80, 70 + 22 * k, 12, False, f"Nội dung trang {p + 1}: {t}") for k, t in enumerate(BODY[2:])]
        if p == n_pages - 1:
            lines += [(360, 300, 13, True, "CHỦ TỊCH"), (350, 380, 13, True, f"Nguyễn Văn {chr(65 + i % 20)}")]
        pages.append(lines)
    return pages


def render_page(lines, noise=0):
    img = Image.new("RGB", (int(W * S), int(H * S)), "white")
    d = ImageDraw.Draw(img)
    truth = []
    for x, y, size, bold, text in lines:
        f = ImageFont.truetype(BOLD if bold else FONT, int(size * S))
        d.text((x * S, y * S), text, font=f, fill=(20, 20, 20))
        bw = d.textlength(text, font=f) / S
        truth.append({"text": text, "box": [x, y, x + bw, y + size * 1.2]})
    if noise:
        px = img.load()
        for _ in range(noise):
            px[random.randrange(img.width), random.randrange(img.height)] = (180, 180, 180)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return buf.getvalue(), truth


def write_pdf(path: Path, pages, noise=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    truths = []
    for lines in pages:
        data, truth = render_page(lines, noise)
        pg = doc.new_page(width=W, height=H)
        pg.insert_image(pg.rect, stream=data)
        truths.append(truth)
    doc.save(path, deflate=True)
    doc.close()
    path.with_suffix(".truth.json").write_text(json.dumps({"pages": truths}, ensure_ascii=False), encoding="utf-8")


def merge(dest: Path, parts: list[Path], reencode=False):
    out = pymupdf.open()
    truths = []
    for p in parts:
        truths += json.loads(p.with_suffix(".truth.json").read_text(encoding="utf-8"))["pages"]
        with pymupdf.open(p) as src:
            if not reencode:
                out.insert_pdf(src)
            else:  # file gộp bị "in lại" -> ảnh khác byte, cùng nội dung
                for page in src:
                    pix = page.get_pixmap(dpi=120)
                    pg = out.new_page(width=W, height=H)
                    pg.insert_image(pg.rect, stream=pix.tobytes("jpeg", jpg_quality=60))
    out.save(dest, deflate=True)
    dest.with_suffix(".truth.json").write_text(json.dumps({"pages": truths}, ensure_ascii=False), encoding="utf-8")


if OUT.exists():
    shutil.rmtree(OUT)
lo = OUT / "Đà Lạt 1L"
i = 0
# 1/: file gộp ghép thẳng (giống từng byte)
f1 = lo / "1"
write_pdf(f1 / "H01.15.01.100001.pdf", doc_pages("QUYẾT ĐỊNH", 2, 1))
write_pdf(f1 / "H01.15.01.100002.pdf", doc_pages("CÔNG VĂN", 1, 2))
merge(f1 / "H01.15.01.1.pdf", [f1 / "H01.15.01.100001.pdf", f1 / "H01.15.01.100002.pdf"])
# 2/: chỉ 1 file (giấy khen)
write_pdf(lo / "2" / "H01.15.02.1.pdf", doc_pages("GIẤY KHEN", 1, 3))
# 3/: file gộp bị lưu lại (ảnh nén lại)
f3 = lo / "3"
write_pdf(f3 / "H01.15.03.100001.pdf", doc_pages("BÁO CÁO", 1, 4))
write_pdf(f3 / "H01.15.03.100002.pdf", doc_pages("QUYẾT ĐỊNH", 2, 5))
write_pdf(f3 / "H01.15.03.100003.pdf", doc_pages("CÔNG VĂN", 1, 6))
merge(f3 / "H01.15.03.1.pdf", [f3 / "H01.15.03.100001.pdf", f3 / "H01.15.03.100002.pdf",
                               f3 / "H01.15.03.100003.pdf"], reencode=True)
# 4/, 5/: tên file kiểu máy scan -> phần chung 'Scan' trùng giữa 2 thư mục
write_pdf(lo / "4" / "Scan_0001.pdf", doc_pages("QUYẾT ĐỊNH", 1, 7))
write_pdf(lo / "4" / "Scan_0002.pdf", doc_pages("CÔNG VĂN", 1, 8))
write_pdf(lo / "5" / "Scan_0001.pdf", doc_pages("BÁO CÁO", 3, 9))
write_pdf(lo / "5" / "Scan_0003.pdf", doc_pages("CÔNG VĂN", 1, 10))
# 6/: 1 file hỏng + 3 file thường (không có file gộp)
write_pdf(lo / "6" / "H01.15.06.100001.pdf", doc_pages("QUYẾT ĐỊNH", 1, 11))
write_pdf(lo / "6" / "H01.15.06.100002.pdf", doc_pages("CÔNG VĂN", 1, 12))
write_pdf(lo / "6" / "H01.15.06.100003.pdf", doc_pages("GIẤY KHEN", 1, 13))
(lo / "6" / "H01.15.06.100004.pdf").write_bytes(b"day khong phai pdf")
# 10/ (sắp xếp tự nhiên: 10 đứng sau 6)
write_pdf(lo / "10" / "H01.15.10.100001.pdf", doc_pages("QUYẾT ĐỊNH", 2, 14))
write_pdf(lo / "10" / "H01.15.10.100002.pdf", doc_pages("BÁO CÁO", 1, 15))

# 1 PDF dài chứa nhiều tài liệu
pages = []
kinds = ["QUYẾT ĐỊNH", "CÔNG VĂN", "BÁO CÁO", "GIẤY KHEN"]
for k in range(14):
    pages += doc_pages(kinds[k % 4], 1 + k % 3, 20 + k)
write_pdf(OUT / "ho_so_dai.pdf", pages, noise=0)
print("pages in long pdf:", len(pages))
print("ok", OUT)
