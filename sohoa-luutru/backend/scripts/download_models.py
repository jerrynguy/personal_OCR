"""Tải model OCR về thư mục sohoa-luutru/models/ — CHỈ CẦN CHẠY MỘT LẦN KHI CÓ MẠNG.

Sau khi tải xong, app chạy hoàn toàn offline. Có thể chép nguyên thư mục models/
sang máy khác qua USB.

    python scripts/download_models.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import OCR_MODELS, PADDLE_MODELS_DIR, ocr_model_dir, setup_paddle_env  # noqa: E402


def dir_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024


def main() -> int:
    setup_paddle_env(offline=False)
    from paddleocr import PaddleOCR

    print(f"Đang tải model vào: {PADDLE_MODELS_DIR}")
    PaddleOCR(
        text_detection_model_name=OCR_MODELS["det"],
        text_recognition_model_name=OCR_MODELS["rec"],
        doc_orientation_classify_model_name=OCR_MODELS["doc_ori"],
        use_doc_orientation_classify=True,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="cpu",
    )

    ok = True
    for key, name in OCR_MODELS.items():
        d = ocr_model_dir(key)
        if d.exists():
            print(f"  [OK] {name:28s} {dir_size_mb(d):7.1f} MB")
        else:
            print(f"  [THIẾU] {name}")
            ok = False
    print("Xong. Từ giờ có thể ngắt mạng." if ok else "Có model chưa tải được, chạy lại.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
