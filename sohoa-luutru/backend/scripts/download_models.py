"""Tải toàn bộ model OCR về sohoa-luutru/models/ — CHỈ CẦN CHẠY MỘT LẦN KHI CÓ MẠNG.

Sau khi tải xong, app chạy hoàn toàn offline. Có thể chép nguyên thư mục models/
sang máy khác qua USB. Chạy lại nhiều lần cũng không sao: model nào có rồi sẽ bỏ qua.

    python scripts/download_models.py
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import (  # noqa: E402
    DET_MODELS,
    DOC_ORI_MODEL,
    VIETOCR_DIR,
    VIETOCR_MODELS,
    VIETOCR_WEIGHTS_URL,
    paddle_model_dir,
    setup_paddle_env,
    vietocr_weights_path,
)


def dir_size_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / 1024 / 1024
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024


def download_file(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r    {done / total:6.1%}  {done / 1048576:6.1f} MB", end="")
    print()
    tmp.replace(dest)


def main() -> int:
    setup_paddle_env(offline=False)
    from paddleocr import DocImgOrientationClassification, TextDetection

    print("== PaddleOCR (xoay trang + tìm vùng chữ)")
    if not paddle_model_dir(DOC_ORI_MODEL).exists():
        DocImgOrientationClassification(model_name=DOC_ORI_MODEL, device="cpu")
    for name in DET_MODELS:
        if not paddle_model_dir(name).exists():
            TextDetection(model_name=name, device="cpu")

    print("== VietOCR (đọc chữ tiếng Việt)")
    VIETOCR_DIR.mkdir(parents=True, exist_ok=True)
    for name, (_, filename) in VIETOCR_MODELS.items():
        dest = vietocr_weights_path(name)
        if dest.exists():
            continue
        url = VIETOCR_WEIGHTS_URL.format(filename)
        print(f"  Đang tải {url}")
        try:
            download_file(url, dest)
        except Exception as e:  # noqa: BLE001
            print(f"  LỖI: {e}")

    print("\n== Kết quả")
    ok = True
    items = [(n, paddle_model_dir(n)) for n in [DOC_ORI_MODEL, *DET_MODELS]]
    items += [(f"VietOCR {n}", vietocr_weights_path(n)) for n in VIETOCR_MODELS]
    for label, path in items:
        if path.exists():
            print(f"  [OK]   {label:28s} {dir_size_mb(path):7.1f} MB")
        else:
            print(f"  [THIẾU] {label}")
            ok = False
    if ok:
        print("Xong. Từ giờ có thể ngắt mạng.")
    else:
        print(
            "Có model chưa tải được. Chạy lại lệnh này. Nếu VietOCR vẫn lỗi, tải tay file .pth\n"
            f"từ {VIETOCR_WEIGHTS_URL.format('<tên file>')} rồi chép vào {VIETOCR_DIR}"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
