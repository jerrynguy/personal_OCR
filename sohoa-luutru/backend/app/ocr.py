"""OCR một trang ảnh: PaddleOCR (xoay trang + tìm vùng chữ) + VietOCR (đọc chữ).

Kết quả: danh sách dòng chữ có toạ độ + điểm tin cậy. Toạ độ được giữ lại vì các bước
sau cần biết chữ nằm ở đâu trên trang (góc trên trái = cơ quan ban hành + số ký hiệu,
góc trên phải = quốc hiệu + ngày tháng...).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.config import (
    DEFAULT_DET_MODEL,
    DEFAULT_DET_SIDE,
    DEFAULT_REC_MODEL,
    DOC_ORI_MODEL,
    default_threads,
    paddle_model_dir,
    setup_paddle_env,
)
from app.vietocr_rec import VietOcrRecognizer


@dataclass
class OcrLine:
    text: str
    score: float
    box: list[int]  # [x0, y0, x1, y1]
    poly: list[list[int]]  # 4 điểm của khung chữ

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def cy(self) -> float:
        return (self.box[1] + self.box[3]) / 2

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


@dataclass
class OcrPage:
    image: str
    width: int
    height: int
    rotated_angle: int  # góc trang đã được xoay lại (0/90/180/270), -1 nếu không kiểm tra
    lines: list[OcrLine]
    timings: dict = field(default_factory=dict)  # giây: orientation / det / rec

    def to_dict(self) -> dict:
        d = asdict(self)
        d["text"] = lines_to_text(self.lines)
        return d


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Sắp 4 điểm theo thứ tự: trên-trái, trên-phải, dưới-phải, dưới-trái."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def crop_line(img_bgr: np.ndarray, poly, pad_y: float = 0.15, pad_x: float = 0.3) -> Image.Image:
    """Cắt và nắn thẳng một dòng chữ, chừa lề để không mất dấu trên/dưới (ộ, ậ, ự...)."""
    tl, tr, br, bl = _order_points(np.array(poly, dtype=np.float32))
    w = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    h = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    w, h = max(int(round(w)), 1), max(int(round(h)), 1)
    px, py = int(round(h * pad_x)), int(round(h * pad_y))

    dst = np.array([[px, py], [px + w, py], [px + w, py + h], [px, py + h]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl]), dst)
    crop = cv2.warpPerspective(
        img_bgr, m, (w + 2 * px, h + 2 * py), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    if crop.shape[0] >= crop.shape[1] * 1.5:  # chữ dọc -> xoay ngang
        crop = np.rot90(crop)
    return Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))


class OcrEngine:
    def __init__(
        self,
        det_model: str = DEFAULT_DET_MODEL,
        rec_model: str = DEFAULT_REC_MODEL,
        det_side: int = DEFAULT_DET_SIDE,
        use_doc_orientation: bool = True,
        threads: int | None = None,
        mkldnn: bool = True,
    ):
        needed = [det_model] + ([DOC_ORI_MODEL] if use_doc_orientation else [])
        missing = [n for n in needed if not paddle_model_dir(n).exists()]
        if missing:
            raise FileNotFoundError(
                "Chưa có model: " + ", ".join(missing)
                + ". Chạy 'python scripts/download_models.py' một lần khi có mạng."
            )

        threads = threads or default_threads()
        setup_paddle_env(offline=True)
        from paddleocr import DocImgOrientationClassification, TextDetection

        common = dict(device="cpu", cpu_threads=threads, enable_mkldnn=mkldnn)
        self._ori = (
            DocImgOrientationClassification(
                model_name=DOC_ORI_MODEL, model_dir=str(paddle_model_dir(DOC_ORI_MODEL)), **common
            )
            if use_doc_orientation
            else None
        )
        self._det = TextDetection(
            model_name=det_model,
            model_dir=str(paddle_model_dir(det_model)),
            limit_side_len=det_side,
            limit_type="max",
            **common,
        )
        self._rec = VietOcrRecognizer(rec_model, threads=threads)
        self.description = f"{det_model} @{det_side}px + VietOCR {rec_model}, {threads} luồng"

    def run(self, image_path: Path) -> OcrPage:
        timings = {}
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Không đọc được ảnh: {image_path}")

        angle = -1
        if self._ori is not None:
            t0 = time.perf_counter()
            angle = int(self._ori.predict(img)[0]["label_names"][0])
            if angle != 0:
                from paddlex.inference.pipelines.components import rotate_image

                img = rotate_image(img, angle)
                cv2.imwrite(str(image_path), img)  # lưu bản đã xoay thẳng để toạ độ khớp ảnh
            timings["orientation"] = round(time.perf_counter() - t0, 2)

        t0 = time.perf_counter()
        det = self._det.predict(img)[0]
        polys = [np.array(p).reshape(-1, 2) for p in det["dt_polys"]]
        timings["det"] = round(time.perf_counter() - t0, 2)

        t0 = time.perf_counter()
        crops = [crop_line(img, p) for p in polys]
        results = self._rec.recognize(crops)
        timings["rec"] = round(time.perf_counter() - t0, 2)

        lines = []
        for poly, (text, prob) in zip(polys, results):
            text = text.strip()
            if not text:
                continue
            xs, ys = poly[:, 0], poly[:, 1]
            lines.append(
                OcrLine(
                    text=text,
                    score=round(prob, 4),
                    box=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                    poly=[[int(x), int(y)] for x, y in poly],
                )
            )
        h, w = img.shape[:2]
        return OcrPage(str(image_path), w, h, angle, lines, timings)


def group_rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    """Gom các dòng có cùng độ cao trên trang thành một hàng, xếp trái -> phải.

    Văn bản hành chính có tiêu đề 2 cột (cơ quan | quốc hiệu) nên OCR trả về
    2 khung riêng nằm ngang nhau; gom lại giúp đọc đúng thứ tự.
    """
    rows: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda l: l.cy):
        if rows:
            last = rows[-1]
            ref_cy = sum(l.cy for l in last) / len(last)
            ref_h = max(l.height for l in last)
            if abs(line.cy - ref_cy) <= max(ref_h, line.height) * 0.5:
                last.append(line)
                continue
        rows.append([line])
    return [sorted(r, key=lambda l: l.box[0]) for r in rows]


def lines_to_text(lines: list[OcrLine]) -> str:
    return "\n".join("   |   ".join(l.text for l in row) for row in group_rows(lines))
