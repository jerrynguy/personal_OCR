"""So sánh các cấu hình OCR trên MỘT trang để chọn cấu hình tốt nhất cho máy.

    python scripts/bench_ocr.py <file.pdf> [--page 1]

In ra thời gian từng phần + văn bản đọc được của từng cấu hình. Nếu cạnh PDF có file
đáp án <tên>.truth.json (PDF mẫu có sẵn), in thêm tỉ lệ lỗi ký tự (CER) và các từ sai.
Văn bản đầy đủ lưu ở data/bench/<tên file>_p<trang>/<cấu hình>.txt
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR  # noqa: E402
from app.metrics import cer, load_truth, word_diffs  # noqa: E402
from app.ocr import OcrEngine, group_rows, lines_to_text  # noqa: E402
from app.pdf_render import low_dpi_warning, render_pdf  # noqa: E402

# (model tìm vùng chữ, cạnh dài tối đa, model đọc chữ, cắt dòng dài > N lần chiều cao)
# PP-OCRv6_medium_det đã bị loại: chậm gấp ~13 lần (9.4s so với 0.7s) mà không đúng hơn.
CONFIGS = [
    ("PP-OCRv5_mobile_det", 1920, "vgg_seq2seq", None),
    ("PP-OCRv5_mobile_det", 1920, "vgg_seq2seq", 12.0),
    ("PP-OCRv5_mobile_det", 1920, "vgg_transformer", None),
    ("PP-OCRv5_mobile_det", 1920, "vgg_transformer", 12.0),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--threads", type=int)
    args = parser.parse_args()

    warning = low_dpi_warning(args.pdf)
    if warning:
        print(f"\n!!! {warning}\n")
    truth_pages = load_truth(args.pdf)
    truth = truth_pages[args.page - 1] if truth_pages else None

    out_dir = DATA_DIR / "bench" / f"{args.pdf.stem}_p{args.page}"
    src = render_pdf(args.pdf, out_dir, pages=str(args.page))[0]

    rows = []
    for det, side, rec, split in CONFIGS:
        name = f"{rec}_{'cat' + format(split, 'g') if split else 'khongcat'}"
        img = out_dir / f"{name}.png"
        shutil.copy(src, img)  # mỗi cấu hình một bản ảnh riêng (ảnh có thể bị xoay lại)

        engine = OcrEngine(
            det_model=det, rec_model=rec, det_side=side, threads=args.threads, split_ratio=split
        )
        engine.run(img)  # chạy nháp 1 lần để "làm nóng", không tính giờ
        shutil.copy(src, img)
        t0 = time.perf_counter()
        page = engine.run(img)
        total = time.perf_counter() - t0

        text = lines_to_text(page.lines)
        (out_dir / f"{name}.txt").write_text(text, encoding="utf-8")
        err = cer(text, truth) if truth else None
        rows.append((name, total, page.timings, len(page.lines), err))

        print(f"\n######## {engine.description}")
        print(f"tổng {total:.1f}s  {page.timings}  {len(page.lines)} dòng")
        if truth:
            print(f"Tỉ lệ lỗi ký tự (CER): {err:.2%}")
            for d in word_diffs(text, truth):
                print(f"   sai: {d}")
        else:  # không có đáp án: in kèm điểm tin cậy từng dòng (0..1)
            for row in group_rows(page.lines):
                print("   |   ".join(f"{l.text} [{l.score:.2f}]" for l in row))

    print("\n==================== TÓM TẮT ====================")
    head = f"{'cấu hình':28s} {'giây/trang':>10s} {'det':>6s} {'rec':>6s} {'dòng':>5s}"
    print(head + ("   CER" if truth else ""))
    for name, total, t, n, err in rows:
        line = f"{name:28s} {total:10.1f} {t.get('det', 0):6.1f} {t.get('rec', 0):6.1f} {n:5d}"
        print(line + (f" {err:6.2%}" if err is not None else ""))
    print(f"\nVăn bản đầy đủ: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
