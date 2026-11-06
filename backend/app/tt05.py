"""Đọc cấu trúc trường dữ liệu TT 05/2025/TT-BNV từ app/schema/tt05.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "tt05.json"
LEVELS = ("phong", "ho_so", "tai_lieu", "bo_sung")


@lru_cache(maxsize=1)
def load_schema() -> dict:
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for level in LEVELS:
        keys = [f["key"] for f in data[level]]
        if len(keys) != len(set(keys)):
            raise ValueError(f"tt05.json: trùng key trong nhóm '{level}'")
    return data


def fields(level: str) -> list[dict]:
    return load_schema()[level]


def keys(level: str) -> list[str]:
    return [f["key"] for f in fields(level)]


def labels(level: str) -> dict[str, str]:
    return {f["key"]: f["label"] for f in fields(level)}


def defaults(level: str) -> dict[str, str]:
    """Giá trị ban đầu của một bản ghi: 'mac_dinh' nếu có, còn lại rỗng."""
    return {f["key"]: f.get("mac_dinh", "") for f in fields(level)}


def inherited_keys() -> list[str]:
    """Trường tài liệu lấy giá trị từ hồ sơ (cùng key)."""
    return [f["key"] for f in fields("tai_lieu") if f["nguon"] == "ke_thua_ho_so"]
