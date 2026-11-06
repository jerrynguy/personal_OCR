"""Đo độ chính xác OCR so với đáp án (dùng cho PDF mẫu có file .truth.json)."""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path


def normalize(text: str) -> str:
    """Bỏ ký tự phân cột '|' và gộp khoảng trắng; GIỮ nguyên hoa/thường, dấu câu."""
    return re.sub(r"\s+", " ", text.replace("|", " ")).strip()


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ocr_text: str, truth_text: str) -> float:
    """Tỉ lệ lỗi ký tự (Character Error Rate): 0 = đúng tuyệt đối."""
    ocr, truth = normalize(ocr_text), normalize(truth_text)
    return edit_distance(ocr, truth) / max(len(truth), 1)


def word_diffs(ocr_text: str, truth_text: str, limit: int = 10) -> list[str]:
    """Liệt kê các chỗ sai theo từ: 'đáp án' -> 'OCR đọc ra'."""
    ocr, truth = normalize(ocr_text).split(), normalize(truth_text).split()
    out = []
    sm = difflib.SequenceMatcher(a=truth, b=ocr, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            out.append(f"'{' '.join(truth[i1:i2])}' -> '{' '.join(ocr[j1:j2])}'")
    return out[:limit]


def load_truth(pdf_path: Path) -> list[str] | None:
    """Đáp án nằm cạnh PDF: <tên>.truth.json = {"pages": ["văn bản trang 1", ...]}."""
    path = pdf_path.with_suffix(".truth.json")
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["pages"]
