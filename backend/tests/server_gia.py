"""Chạy backend thật với OCR giả + AI giả (môi trường cloud không tải được model).

OCR giả: trả về các dòng chữ trong <file>.truth.json (do gen_data.py tạo) theo đúng toạ độ trên ảnh.
AI giả: trả JSON đúng schema sau một chút chờ.
    python tests/server_gia.py <thư mục data> <thư mục dữ liệu thử> [cổng] [giây OCR/trang] [giây AI/văn bản]
"""

import json
import os
import re
import sys
import time
from pathlib import Path

DATA = Path(sys.argv[1]).resolve()
TESTDATA = Path(sys.argv[2]).resolve()
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8765
OCR_DELAY = float(sys.argv[4]) if len(sys.argv) > 4 else 0.15
LLM_DELAY = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
os.environ["SOHOA_DATA_DIR"] = str(DATA)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402
from PIL import Image  # noqa: E402

from app import db  # noqa: E402
from app.api import create_app  # noqa: E402
from app.ocr import OcrLine, OcrPage  # noqa: E402
from app.sources import PdfSet  # noqa: E402


class FakeOcr:
    def run(self, img: Path) -> OcrPage:
        time.sleep(OCR_DELAY)
        hid = int(img.parts[-3])
        n = int(re.search(r"page_(\d+)", img.name).group(1))
        info = db.load_ho_so(hid)
        src, idx = PdfSet(info["nguon_pdf"]).locate(n)
        truth = Path(src["duong_dan"]).with_suffix(".truth.json")
        if not truth.exists():
            truth = TESTDATA / (Path(src["ten"]).stem + ".truth.json")
        lines = []
        with Image.open(img) as im:
            w, h = im.size
        if truth.exists():
            k = w / 595
            for l in json.loads(truth.read_text(encoding="utf-8"))["pages"][idx]:
                x0, y0, x1, y1 = (int(v * k) for v in l["box"])
                lines.append(OcrLine(l["text"], 0.95 if "Nội dung" not in l["text"] else 0.75,
                                     [x0, y0, x1, y1], [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]))
        return OcrPage(str(img), w, h, 0, lines, {"det": OCR_DELAY})


class FakeClient:
    def extract_json(self, system, user, schema, max_tokens=0):
        time.sleep(LLM_DELAY)
        props = schema["properties"]
        out = {}
        for k, v in props.items():
            out[k] = [] if v["type"] == "array" else ""
        m = re.search(r"\[CƠ QUAN\] (.*)", user)
        out["co_quan"] = (m.group(1).title() if m else "")[:150]
        lines = [l for l in user.splitlines() if l.strip() and not l.startswith("[")]
        out["trich_yeu"] = next((l.strip() for l in lines if l.strip().startswith(("Về", "V/v", "Kết quả", "Đã"))), "")
        out["tu_khoa"] = ["lưu trữ", "chỉnh lý tài liệu"]
        out["nguoi_ky"] = next((l.strip() for l in lines if l.strip().startswith("Nguyễn")), "")
        out["chuc_vu"] = "Chủ tịch" if out["nguoi_ky"] else ""
        return out, {"prompt_n": 100, "predicted_n": 40, "prompt_ms": 1, "predicted_ms": 1}


class FakeLlm:
    loading = False
    last_error = ""
    model_name = "gia.gguf"

    def __init__(self):
        self._on = False

    def client(self):
        if not self._on:
            time.sleep(0.5)
            self._on = True
        return FakeClient()

    @property
    def running(self):
        return self._on

    def touch(self):
        pass

    def stop(self):
        self._on = False

    def switch_model(self, path, on_done=None):
        pass


app = create_app(token="", dev=True, ocr_factory=FakeOcr, frontend_dir=ROOT / "frontend" / "out",
                 warmup=False, llm_service=FakeLlm())
print(f"http://127.0.0.1:{PORT}/", flush=True)
uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
