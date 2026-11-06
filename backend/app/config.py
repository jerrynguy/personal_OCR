"""Đường dẫn và cấu hình chung của backend.

Mọi thứ (model, dữ liệu) nằm trong thư mục project, không rải ra thư mục người dùng,
để sau này đóng gói và mang sang máy không có mạng cho dễ.
"""

import os
from pathlib import Path

# thư mục gốc của repo (chứa backend/, frontend/, models/, data/)
ROOT_DIR = Path(__file__).resolve().parents[2]

MODELS_DIR = Path(os.environ.get("SOHOA_MODELS_DIR", ROOT_DIR / "models"))
DATA_DIR = Path(os.environ.get("SOHOA_DATA_DIR", ROOT_DIR / "data"))

# ---------------------------------------------------------------- PaddleOCR
# PaddleOCR CHỈ dùng để: (1) nhận biết trang bị xoay, (2) tìm vùng dòng chữ.
# KHÔNG dùng PaddleOCR để đọc chữ: bảng ký tự của nó thiếu các chữ Việt như
# ộ, ậ, ự, ủ, ữ... (đã kiểm chứng ở lần chạy thử đầu tiên).
PADDLE_HOME = MODELS_DIR / "paddlex"
PADDLE_MODELS_DIR = PADDLE_HOME / "official_models"

DOC_ORI_MODEL = "PP-LCNet_x1_0_doc_ori"
DET_MODELS = ["PP-OCRv5_mobile_det", "PP-OCRv6_medium_det"]
DEFAULT_DET_MODEL = "PP-OCRv5_mobile_det"
# Ảnh được thu nhỏ để cạnh dài nhất bằng giá trị này trước khi tìm vùng chữ.
# Mặc định của PaddleOCR là KHÔNG thu nhỏ -> rất chậm với ảnh scan 300 DPI.
DEFAULT_DET_SIDE = 1920

# ---------------------------------------------------------------- VietOCR
# Model đọc chữ tiếng Việt (đủ 134 chữ cái có dấu).
VIETOCR_DIR = MODELS_DIR / "vietocr"
VIETOCR_CONFIG_DIR = Path(__file__).resolve().parent / "vietocr_configs"
VIETOCR_MODELS = {
    # tên: (file config, file trọng số)
    "vgg_seq2seq": ("vgg-seq2seq.yml", "vgg_seq2seq.pth"),
    "vgg_transformer": ("vgg-transformer.yml", "vgg_transformer.pth"),
}
VIETOCR_WEIGHTS_URL = "https://vocr.vn/data/vietocr/{}"
# Bench (PDF mẫu): seq2seq + cắt dòng CER 0.86% (~4s/trang); transformer + cắt dòng CER 0.34%
# (~11s/trang). Chênh lệch chỉ ở dấu câu cuối dòng (; . :), không ảnh hưởng trường dữ liệu
# -> chọn seq2seq vì nhanh gấp ~2.5 lần.
DEFAULT_REC_MODEL = "vgg_seq2seq"
# Dòng rộng hơn N lần chiều cao sẽ được cắt tại khoảng trắng giữa các từ trước khi đọc.
DEFAULT_SPLIT_RATIO = 12.0


# ---------------------------------------------------------------- LLM (llama.cpp)
LLAMA_CPP_DIR = MODELS_DIR / "llama.cpp"  # chứa các bản build: cpu/, vulkan/
LLM_DIR = MODELS_DIR / "llm"  # chứa file .gguf
ACTIVE_LLM_FILE = LLM_DIR / "active.json"  # model đang dùng: {"path": "...gguf"}
DEFAULT_LLM_NAME = "gpt-oss-20b-MXFP4.gguf"  # model mặc định (đóng gói kèm bộ cài ở Bước 7)
LLM_CTX = 8192  # độ dài ngữ cảnh (token): đủ cho văn bản vài trang + schema
LOGS_DIR = DATA_DIR / "logs"


def paddle_model_dir(name: str) -> Path:
    return PADDLE_MODELS_DIR / name


def vietocr_weights_path(name: str) -> Path:
    return VIETOCR_DIR / VIETOCR_MODELS[name][1]


def default_threads() -> int:
    """Số nhân thật của CPU (i7-1185G7: 4). Dùng số nhân thật thường nhanh hơn số luồng."""
    try:
        import psutil

        return psutil.cpu_count(logical=False) or 4
    except Exception:
        return 4


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
