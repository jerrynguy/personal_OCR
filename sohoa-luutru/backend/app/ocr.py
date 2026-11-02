"""Bọc PaddleOCR: ảnh trang -> danh sách dòng chữ có toạ độ + điểm tin cậy.

Toạ độ được giữ lại vì các bước sau cần biết chữ nằm ở đâu trên trang
(góc trên trái = cơ quan ban hành + số ký hiệu, góc trên phải = quốc hiệu + ngày tháng...).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import OCR_MODELS, ocr_model_dir, setup_paddle_env


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

    def to_dict(self) -> dict:
        d = asdict(self)
        d["text"] = lines_to_text(self.lines)
        return d


class OcrEngine:
    def __init__(self, use_doc_orientation: bool = True, cpu_threads: int | None = None):
        missing = [
            OCR_MODELS[k]
            for k in (["det", "rec"] + (["doc_ori"] if use_doc_orientation else []))
            if not ocr_model_dir(k).exists()
        ]
        if missing:
            raise FileNotFoundError(
                "Chưa có model OCR: "
                + ", ".join(missing)
                + ". Chạy 'python scripts/download_models.py' một lần khi có mạng."
            )

        setup_paddle_env(offline=True)
        from paddleocr import PaddleOCR  # import sau khi đặt biến môi trường

        kwargs = dict(
            text_detection_model_name=OCR_MODELS["det"],
            text_detection_model_dir=str(ocr_model_dir("det")),
            text_recognition_model_name=OCR_MODELS["rec"],
            text_recognition_model_dir=str(ocr_model_dir("rec")),
            use_doc_orientation_classify=use_doc_orientation,
            use_doc_unwarping=False,  # ảnh scan phẳng, không cần nắn cong
            use_textline_orientation=False,
            device="cpu",
        )
        if use_doc_orientation:
            kwargs["doc_orientation_classify_model_name"] = OCR_MODELS["doc_ori"]
            kwargs["doc_orientation_classify_model_dir"] = str(ocr_model_dir("doc_ori"))
        if cpu_threads:
            kwargs["cpu_threads"] = cpu_threads

        self._ocr = PaddleOCR(**kwargs)

    def run(self, image_path: Path) -> OcrPage:
        res = self._ocr.predict(str(image_path))[0]

        pre = res.get("doc_preprocessor_res") or {}
        angle = int(pre.get("angle", -1))
        out_img = pre.get("output_img")
        if angle not in (-1, 0) and out_img is not None:
            # Trang bị xoay: ghi đè ảnh bằng bản đã xoay thẳng để toạ độ khớp với ảnh.
            import cv2

            cv2.imwrite(str(image_path), out_img)  # output_img là BGR, đúng định dạng cv2

        if out_img is not None:
            height, width = out_img.shape[:2]
        else:
            import cv2

            height, width = cv2.imread(str(image_path)).shape[:2]

        lines = [
            OcrLine(
                text=str(text),
                score=round(float(score), 4),
                box=[int(v) for v in box],
                poly=[[int(x), int(y)] for x, y in poly],
            )
            for text, score, box, poly in zip(
                res["rec_texts"], res["rec_scores"], res["rec_boxes"], res["rec_polys"]
            )
            if str(text).strip()
        ]
        return OcrPage(
            image=str(image_path), width=width, height=height, rotated_angle=angle, lines=lines
        )


def group_rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    """Gom các dòng có cùng độ cao trên trang thành một hàng, xếp trái -> phải.

    Văn bản hành chính có tiêu đề 2 cột (cơ quan | quốc hiệu) nên PaddleOCR trả về
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
