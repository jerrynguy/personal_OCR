"""Đường dẫn và cấu hình chung của backend.

Mọi thứ (model, dữ liệu) nằm trong thư mục project, không rải ra thư mục người dùng,
để sau này đóng gói và mang sang máy không có mạng cho dễ.
"""

import os
from pathlib import Path

# sohoa-luutru/
ROOT_DIR = Path(__file__).resolve().parents[2]

MODELS_DIR = Path(os.environ.get("SOHOA_MODELS_DIR", ROOT_DIR / "models"))
DATA_DIR = Path(os.environ.get("SOHOA_DATA_DIR", ROOT_DIR / "data"))

# PaddleOCR (PaddleX) lưu model vào <PADDLE_HOME>/official_models/<tên model>
PADDLE_HOME = MODELS_DIR / "paddlex"
PADDLE_MODELS_DIR = PADDLE_HOME / "official_models"

# PP-OCRv6 có hỗ trợ tiếng Việt (lang="vi").
OCR_MODELS = {
    "det": "PP-OCRv6_medium_det",  # tìm vùng chữ
    "rec": "PP-OCRv6_medium_rec",  # đọc chữ
    "doc_ori": "PP-LCNet_x1_0_doc_ori",  # nhận biết trang bị xoay 90/180/270 độ
}


def setup_paddle_env(offline: bool = True) -> None:
    """Phải gọi TRƯỚC khi import paddleocr (PaddleX đọc biến môi trường lúc import).

    offline=True: không bao giờ kết nối mạng, chỉ dùng model có sẵn trong MODELS_DIR.
    offline=False: chỉ dùng cho script tải model lần đầu.
    """
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(PADDLE_HOME)
    if offline:
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    else:
        os.environ.pop("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", None)


def ocr_model_dir(key: str) -> Path:
    return PADDLE_MODELS_DIR / OCR_MODELS[key]
