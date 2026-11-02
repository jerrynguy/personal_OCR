"""BƯỚC 1 — Kiểm tra OCR offline trên một file PDF scan nhiều trang.

    python scripts/step1_ocr_pdf.py <file.pdf> [--pages 1-3] [--det ...] [--rec ...]

Kết quả nằm ở data/step1/<tên file>/:
    page_001.png        ảnh trang (đã xoay thẳng nếu bị ngược)
    page_001.ocr.json   từng dòng chữ + toạ độ + điểm tin cậy
    page_001.txt        văn bản đã sắp theo bố cục trang
    summary.json        thời gian xử lý từng trang
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import (  # noqa: E402
    DATA_DIR,
    DEFAULT_DET_MODEL,
    DEFAULT_DET_SIDE,
    DEFAULT_REC_MODEL,
    DET_MODELS,
    VIETOCR_MODELS,
)
from app.metrics import cer, load_truth, word_diffs  # noqa: E402
from app.ocr import OcrEngine, lines_to_text  # noqa: E402
from app.pdf_render import low_dpi_warning, render_pdf  # noqa: E402

LOW_SCORE = 0.80  # dòng có điểm dưới mức này sẽ được đánh dấu để soát lại


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR offline một file PDF scan.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", help="Ví dụ: 1-3,5 (mặc định: tất cả)")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--det", choices=DET_MODELS, default=DEFAULT_DET_MODEL)
    parser.add_argument("--det-side", type=int, default=DEFAULT_DET_SIDE)
    parser.add_argument("--rec", choices=list(VIETOCR_MODELS), default=DEFAULT_REC_MODEL)
    parser.add_argument("--threads", type=int, help="Số luồng CPU (mặc định: số nhân thật)")
    parser.add_argument("--no-mkldnn", action="store_true", help="Tắt tăng tốc oneDNN của Paddle")
    parser.add_argument("--no-orientation", action="store_true", help="Tắt tự xoay trang")
    parser.add_argument("--no-split", action="store_true", help="Không cắt dòng dài trước khi đọc")
    parser.add_argument("--out", type=Path, default=DATA_DIR / "step1")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"Không thấy file: {args.pdf}")
        return 1

    warning = low_dpi_warning(args.pdf)
    if warning:
        print(f"\n!!! {warning}\n")
    out_dir = args.out / args.pdf.stem
    t0 = time.perf_counter()
    images = render_pdf(args.pdf, out_dir, dpi=args.dpi, pages=args.pages)
    print(f"Đã tách {len(images)} trang ({time.perf_counter() - t0:.1f}s) -> {out_dir}")

    t0 = time.perf_counter()
    engine = OcrEngine(
        det_model=args.det,
        rec_model=args.rec,
        det_side=args.det_side,
        use_doc_orientation=not args.no_orientation,
        threads=args.threads,
        mkldnn=not args.no_mkldnn,
        **({"split_ratio": None} if args.no_split else {}),
    )
    truth_pages = load_truth(args.pdf)
    t_load = time.perf_counter() - t0
    print(f"Nạp model ({engine.description}): {t_load:.1f}s\n")

    summary = {
        "pdf": str(args.pdf),
        "dpi": args.dpi,
        "engine": engine.description,
        "load_seconds": round(t_load, 2),
        "pages": [],
    }
    for img in images:
        t0 = time.perf_counter()
        page = engine.run(img)
        dt = time.perf_counter() - t0

        img.with_suffix(".ocr.json").write_text(
            json.dumps(page.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        text = lines_to_text(page.lines)
        img.with_suffix(".txt").write_text(text, encoding="utf-8")

        low = [l for l in page.lines if l.score < LOW_SCORE]
        avg = sum(l.score for l in page.lines) / len(page.lines) if page.lines else 0
        rot = f", đã xoay {page.rotated_angle}°" if page.rotated_angle > 0 else ""
        parts = ", ".join(f"{k} {v}s" for k, v in page.timings.items())
        print(
            f"=== {img.name}: {len(page.lines)} dòng, {dt:.1f}s ({parts}), "
            f"điểm TB {avg:.2f}, {len(low)} dòng < {LOW_SCORE}{rot}"
        )
        print(text)
        for l in low[:5]:
            print(f"   ? ({l.score:.2f}) {l.text}")
        page_no = int(img.stem.split("_")[1])
        err = None
        if truth_pages and page_no <= len(truth_pages):
            err = cer(text, truth_pages[page_no - 1])
            print(f"   Tỉ lệ lỗi ký tự so với đáp án: {err:.2%}")
            for d in word_diffs(text, truth_pages[page_no - 1], limit=5):
                print(f"   sai: {d}")
        print()

        summary["pages"].append(
            {
                "image": img.name,
                "seconds": round(dt, 2),
                "timings": page.timings,
                "lines": len(page.lines),
                "avg_score": round(avg, 4),
                "low_score_lines": len(low),
                "rotated_angle": page.rotated_angle,
                "cer": None if err is None else round(err, 4),
            }
        )

    total = sum(p["seconds"] for p in summary["pages"])
    summary["ocr_total_seconds"] = round(total, 2)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if images:
        print(f"Tổng OCR: {total:.1f}s cho {len(images)} trang (~{total / len(images):.1f}s/trang)")
    print(f"Xem kết quả: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
