"""Lưu Phông / Hồ sơ / Tài liệu vào SQLite (data/sohoa.db).

Giá trị các trường lưu dạng JSON để khi sửa danh sách trường trong tt05.json
không phải đổi cấu trúc bảng. Mỗi hồ sơ xác định bằng mã hồ sơ; lưu lại cùng mã
hồ sơ sẽ GHI ĐÈ danh sách tài liệu cũ của hồ sơ đó.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.config import DATA_DIR

DB_PATH = DATA_DIR / "sohoa.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS phong (
    id INTEGER PRIMARY KEY,
    ma_phong TEXT UNIQUE,
    du_lieu TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ho_so (
    id INTEGER PRIMARY KEY,
    phong_id INTEGER REFERENCES phong(id),
    ma_ho_so TEXT UNIQUE NOT NULL,
    tep_pdf TEXT,
    du_lieu TEXT NOT NULL,
    cap_nhat TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tai_lieu (
    id INTEGER PRIMARY KEY,
    ho_so_id INTEGER NOT NULL REFERENCES ho_so(id) ON DELETE CASCADE,
    stt INTEGER NOT NULL,
    du_lieu TEXT NOT NULL,
    nguon TEXT,
    UNIQUE (ho_so_id, stt)
);
"""


@contextmanager
def connect(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _dump(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


def save_result(result: dict, pdf_path: str = "", db_path: Path = DB_PATH) -> int:
    """Lưu kết quả {'phong', 'ho_so', 'tai_lieu'} của Bước 3. Trả về id hồ sơ."""
    phong, ho_so, docs = result["phong"], result["ho_so"], result["tai_lieu"]
    ma_ho_so = ho_so.get("ma_ho_so") or ""
    if not ma_ho_so:
        raise ValueError("Hồ sơ chưa có mã hồ sơ — nhập 'ma_ho_so' trong file thông tin hồ sơ.")

    with connect(db_path) as conn:
        phong_id = None
        if phong.get("ma_phong"):
            conn.execute(
                "INSERT INTO phong (ma_phong, du_lieu) VALUES (?, ?) "
                "ON CONFLICT(ma_phong) DO UPDATE SET du_lieu = excluded.du_lieu",
                (phong["ma_phong"], _dump(phong)),
            )
            phong_id = conn.execute("SELECT id FROM phong WHERE ma_phong = ?", (phong["ma_phong"],)).fetchone()[0]

        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO ho_so (phong_id, ma_ho_so, tep_pdf, du_lieu, cap_nhat) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(ma_ho_so) DO UPDATE SET phong_id = excluded.phong_id, tep_pdf = excluded.tep_pdf, "
            "du_lieu = excluded.du_lieu, cap_nhat = excluded.cap_nhat",
            (phong_id, ma_ho_so, pdf_path, _dump(ho_so), now),
        )
        ho_so_id = conn.execute("SELECT id FROM ho_so WHERE ma_ho_so = ?", (ma_ho_so,)).fetchone()[0]

        conn.execute("DELETE FROM tai_lieu WHERE ho_so_id = ?", (ho_so_id,))
        for doc in docs:
            data = {k: v for k, v in doc.items() if not k.startswith("_")}
            conn.execute(
                "INSERT INTO tai_lieu (ho_so_id, stt, du_lieu, nguon) VALUES (?, ?, ?, ?)",
                (ho_so_id, doc["stt"], _dump(data), _dump(doc.get("_nguon", {}))),
            )
    return ho_so_id


def load_ho_so(ho_so_id: int, db_path: Path = DB_PATH) -> dict:
    """Đọc lại một hồ sơ, cùng dạng {'phong', 'ho_so', 'tai_lieu'} như kết quả Bước 3."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM ho_so WHERE id = ?", (ho_so_id,)).fetchone()
        if row is None:
            raise KeyError(f"Không có hồ sơ id={ho_so_id}")
        phong = {}
        if row["phong_id"]:
            p = conn.execute("SELECT du_lieu FROM phong WHERE id = ?", (row["phong_id"],)).fetchone()
            phong = json.loads(p["du_lieu"])
        docs = []
        for t in conn.execute("SELECT * FROM tai_lieu WHERE ho_so_id = ? ORDER BY stt", (ho_so_id,)):
            d = json.loads(t["du_lieu"])
            d["_nguon"] = json.loads(t["nguon"] or "{}")
            docs.append(d)
    return {"phong": phong, "ho_so": json.loads(row["du_lieu"]), "tai_lieu": docs, "tep_pdf": row["tep_pdf"]}


def list_ho_so(db_path: Path = DB_PATH) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT h.id, h.ma_ho_so, h.cap_nhat, h.tep_pdf, json_extract(h.du_lieu, '$.tieu_de_ho_so') AS tieu_de, "
            "(SELECT COUNT(*) FROM tai_lieu t WHERE t.ho_so_id = h.id) AS so_tai_lieu "
            "FROM ho_so h ORDER BY h.cap_nhat DESC"
        ).fetchall()
    return [dict(r) for r in rows]
