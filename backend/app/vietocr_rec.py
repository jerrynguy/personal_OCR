"""Đọc chữ tiếng Việt bằng VietOCR (https://github.com/pbcquoc/vietocr, Apache-2.0).

Chạy hoàn toàn offline: config lấy từ app/vietocr_configs/ (bản sao từ repo VietOCR),
trọng số lấy từ models/vietocr/. Không gọi mạng để tải config hay trọng số ImageNet.
"""

from __future__ import annotations

import yaml
from PIL import Image

from app.config import VIETOCR_CONFIG_DIR, VIETOCR_MODELS, vietocr_weights_path


def load_vietocr_config(name: str, max_width: int) -> dict:
    with open(VIETOCR_CONFIG_DIR / "base.yml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open(VIETOCR_CONFIG_DIR / VIETOCR_MODELS[name][0], encoding="utf-8") as f:
        cfg.update(yaml.safe_load(f))

    cfg["device"] = "cpu"
    cfg["weights"] = str(vietocr_weights_path(name))
    cfg["pretrain"] = None
    cfg["cnn"]["pretrained"] = False  # không tải trọng số ImageNet từ internet
    cfg["predictor"]["beamsearch"] = False
    # Dòng văn bản hành chính dài cả trang: mặc định 512px sẽ ép chữ quá hẹp.
    cfg["dataset"]["image_max_width"] = max_width
    return cfg


class VietOcrRecognizer:
    def __init__(self, name: str, max_width: int = 1600, threads: int | None = None):
        weights = vietocr_weights_path(name)
        if not weights.exists():
            raise FileNotFoundError(
                f"Chưa có trọng số VietOCR: {weights}. Chạy 'python scripts/download_models.py'."
            )

        import torch
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        if threads:
            torch.set_num_threads(threads)
        self.name = name
        self._predictor = Predictor(Cfg(load_vietocr_config(name, max_width)))

    def recognize(self, crops: list[Image.Image]) -> list[tuple[str, float]]:
        if not crops:
            return []
        texts, probs = self._predictor.predict_batch(crops, return_prob=True)
        return [(t, float(p)) for t, p in zip(texts, probs)]
