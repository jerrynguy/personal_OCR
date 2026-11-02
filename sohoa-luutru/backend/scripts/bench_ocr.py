"""So sánh các cấu hình OCR trên MỘT trang để chọn cấu hình tốt nhất cho máy.

    python scripts/bench_ocr.py <file.pdf> [--page 1]

In ra thời gian từng phần + văn bản đọc được của từng cấu hình.
Văn bản đầy đủ lưu ở data/bench/<tên file>_p<trang>/<cấu hình>.txt
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR  # noqa: E402
from app.ocr import OcrEngine, lines_to_text  # noqa: E402
from app.pdf_render import render_pdf  # noqa: E402

# (model tìm vùng chữ, cạnh dài tối đa, model đọc chữ)
CONFIGS = [
    ("PP-OCRv5_mobile_det", 1920, "vgg_seq2seq"),
    ("PP-OCRv5_mobile_det", 1280, "vgg_seq2seq"),
    ("PP-OCRv6_medium_det", 1920, "vgg_seq2seq"),
    ("PP-OCRv5_mobile_det", 1920, "vgg_transformer"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--threads", type=int)
    args = parser.parse_args()

    out_dir = DATA_DIR / "bench" / f"{args.pdf.stem}_p{args.page}"
    src = render_pdf(args.pdf, out_dir, pages=str(args.page))[0]

    rows = []
    for det, side, rec in CONFIGS:
        name = f"{det}_{side}_{rec}"
        img = out_dir / f"{name}.png"
        shutil.copy(src, img)  # mỗi cấu hình một bản ảnh riêng (ảnh có thể bị xoay lại)

        t0 = time.perf_counter()
        engine = OcrEngine(det_model=det, rec_model=rec, det_side=side, threads=args.threads)
        load = time.perf_counter() - t0

        engine.run(img)  # chạy nháp 1 lần để "làm nóng", không tính giờ
        shutil.copy(src, img)
        t0 = time.perf_counter()
        page = engine.run(img)
        total = time.perf_counter() - t0

        text = lines_to_text(page.lines)
        (out_dir / f"{name}.txt").write_text(text, encoding="utf-8")
        avg = sum(l.score for l in page.lines) / len(page.lines) if page.lines else 0
        rows.append((name, load, total, page.timings, len(page.lines), avg))

        print(f"\n######## {engine.description}")
        print(f"tổng {total:.1f}s  {page.timings}  {len(page.lines)} dòng  điểm TB {avg:.2f}")
        print("\n".join(text.splitlines()[:12]))

    print("\n==================== TÓM TẮT ====================")
    print(f"{'cấu hình':52s} {'giây/trang':>10s} {'det':>6s} {'rec':>6s} {'dòng':>5s}")
    for name, _load, total, t, n, _avg in rows:
        print(f"{name:52s} {total:10.1f} {t.get('det', 0):6.1f} {t.get('rec', 0):6.1f} {n:5d}")
    print(f"\nVăn bản đầy đủ: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
