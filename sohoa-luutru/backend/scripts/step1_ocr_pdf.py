"""BƯỚC 1 — Kiểm tra OCR offline trên một file PDF scan nhiều trang.

    python scripts/step1_ocr_pdf.py <file.pdf> [--pages 1-3] [--dpi 300] [--no-orientation]

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

from app.config import DATA_DIR  # noqa: E402
from app.ocr import OcrEngine, lines_to_text  # noqa: E402
from app.pdf_render import render_pdf  # noqa: E402

LOW_SCORE = 0.80  # dòng có điểm dưới mức này sẽ được đánh dấu để soát lại


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR offline một file PDF scan.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", help="Ví dụ: 1-3,5 (mặc định: tất cả)")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--threads", type=int, help="Số luồng CPU cho OCR")
    parser.add_argument(
        "--no-orientation", action="store_true", help="Tắt tự xoay trang (nhanh hơn chút)"
    )
    parser.add_argument("--out", type=Path, default=DATA_DIR / "step1")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"Không thấy file: {args.pdf}")
        return 1

    out_dir = args.out / args.pdf.stem
    t0 = time.perf_counter()
    images = render_pdf(args.pdf, out_dir, dpi=args.dpi, pages=args.pages)
    t_render = time.perf_counter() - t0
    print(f"Đã tách {len(images)} trang ({t_render:.1f}s) -> {out_dir}")

    t0 = time.perf_counter()
    engine = OcrEngine(use_doc_orientation=not args.no_orientation, cpu_threads=args.threads)
    t_load = time.perf_counter() - t0
    print(f"Nạp model OCR: {t_load:.1f}s\n")

    summary = {"pdf": str(args.pdf), "dpi": args.dpi, "load_seconds": round(t_load, 2), "pages": []}
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
        print(
            f"=== {img.name}: {len(page.lines)} dòng, {dt:.1f}s, "
            f"điểm TB {avg:.2f}, {len(low)} dòng < {LOW_SCORE}{rot}"
        )
        print("\n".join(text.splitlines()[:8]))
        for l in low[:5]:
            print(f"   ? ({l.score:.2f}) {l.text}")
        print()

        summary["pages"].append(
            {
                "image": img.name,
                "seconds": round(dt, 2),
                "lines": len(page.lines),
                "avg_score": round(avg, 4),
                "low_score_lines": len(low),
                "rotated_angle": page.rotated_angle,
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
