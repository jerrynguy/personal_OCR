"""Lưu Phông / Hồ sơ / Tài liệu vào SQLite (data/sohoa.db).

Giá trị các trường lưu dạng JSON để khi sửa danh sách trường trong tt05.json
không phải đổi cấu trúc bảng. Mỗi hồ sơ xác định bằng mã hồ sơ (duy nhất).
CSDL cũ (tạo ở Bước 4) được tự nâng cấp khi mở — không mất dữ liệu.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.config import DATA_DIR
from app.tt05 import defaults

DB_PATH = DATA_DIR / "sohoa.db"
SCHEMA_VERSION = 2

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

# Nâng cấp từ phiên bản 1 (Bước 4) lên 2 (Bước 5).
MIGRATIONS = {
    2: [
        "ALTER TABLE ho_so ADD COLUMN so_trang INTEGER DEFAULT 0",
        "ALTER TABLE ho_so ADD COLUMN trang_thai TEXT DEFAULT 'moi'",
        "ALTER TABLE ho_so ADD COLUMN loi TEXT DEFAULT ''",
        "ALTER TABLE ho_so ADD COLUMN tao_luc TEXT DEFAULT ''",
        "ALTER TABLE tai_lieu ADD COLUMN da_soat INTEGER DEFAULT 0",
        "UPDATE ho_so SET trang_thai = 'xong' WHERE trang_thai = 'moi' "
        "AND EXISTS (SELECT 1 FROM tai_lieu t WHERE t.ho_so_id = ho_so.id)",
    ]
}

TRANG_THAI = {"moi": "Mới tạo", "cho": "Đang chờ", "dang_xu_ly": "Đang xử lý", "xong": "Xong", "loi": "Lỗi"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


@contextmanager
def connect(db_path: Path | None = None):
    db_path = db_path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    version = conn.execute("PRAGMA user_version").fetchone()[0] or 1
    for v in range(version + 1, SCHEMA_VERSION + 1):
        for sql in MIGRATIONS[v]:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e):
                    raise
        conn.execute(f"PRAGMA user_version = {v}")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _upsert_phong(conn, phong: dict) -> int | None:
    if not phong.get("ma_phong"):
        return None
    conn.execute(
        "INSERT INTO phong (ma_phong, du_lieu) VALUES (?, ?) "
        "ON CONFLICT(ma_phong) DO UPDATE SET du_lieu = excluded.du_lieu",
        (phong["ma_phong"], _dump(phong)),
    )
    return conn.execute("SELECT id FROM phong WHERE ma_phong = ?", (phong["ma_phong"],)).fetchone()[0]


# ------------------------------------------------------------------ hồ sơ
def create_ho_so(phong: dict, ho_so: dict, db_path: Path | None = None) -> int:
    ma = (ho_so.get("ma_ho_so") or "").strip()
    if not ma:
        raise ValueError("Thiếu mã hồ sơ")
    with connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM ho_so WHERE ma_ho_so = ?", (ma,)).fetchone():
            raise ValueError(f"Mã hồ sơ '{ma}' đã tồn tại")
        phong_id = _upsert_phong(conn, {**defaults("phong"), **phong})
        cur = conn.execute(
            "INSERT INTO ho_so (phong_id, ma_ho_so, du_lieu, cap_nhat, tao_luc, trang_thai) "
            "VALUES (?, ?, ?, ?, ?, 'moi')",
            (phong_id, ma, _dump({**defaults("ho_so"), **ho_so, "ma_ho_so": ma}), _now(), _now()),
        )
        return cur.lastrowid


def update_ho_so_info(ho_so_id: int, phong: dict | None, ho_so: dict | None, db_path: Path | None = None) -> None:
    """Sửa thông tin nhập tay của phông / hồ sơ (trường tự tính sẽ được tính lại sau)."""
    with connect(db_path) as conn:
        row = _get_row(conn, ho_so_id)
        data = json.loads(row["du_lieu"])
        if ho_so:
            new_ma = (ho_so.get("ma_ho_so") or data["ma_ho_so"]).strip()
            if new_ma != row["ma_ho_so"] and conn.execute(
                "SELECT 1 FROM ho_so WHERE ma_ho_so = ?", (new_ma,)
            ).fetchone():
                raise ValueError(f"Mã hồ sơ '{new_ma}' đã tồn tại")
            data.update(ho_so)
            data["ma_ho_so"] = new_ma
            conn.execute("UPDATE ho_so SET ma_ho_so = ? WHERE id = ?", (new_ma, ho_so_id))
        phong_id = row["phong_id"]
        if phong is not None:
            phong_id = _upsert_phong(conn, {**defaults("phong"), **phong})
        conn.execute(
            "UPDATE ho_so SET du_lieu = ?, phong_id = ?, cap_nhat = ? WHERE id = ?",
            (_dump(data), phong_id, _now(), ho_so_id),
        )


def set_pdf(ho_so_id: int, path: str, so_trang: int, db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE ho_so SET tep_pdf = ?, so_trang = ?, trang_thai = 'moi', loi = '', cap_nhat = ? WHERE id = ?",
            (path, so_trang, _now(), ho_so_id),
        )


def set_status(ho_so_id: int, trang_thai: str, loi: str = "", db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE ho_so SET trang_thai = ?, loi = ?, cap_nhat = ? WHERE id = ?",
            (trang_thai, loi, _now(), ho_so_id),
        )


def delete_ho_so(ho_so_id: int, db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM ho_so WHERE id = ?", (ho_so_id,))


def _get_row(conn, ho_so_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM ho_so WHERE id = ?", (ho_so_id,)).fetchone()
    if row is None:
        raise KeyError(f"Không có hồ sơ id={ho_so_id}")
    return row


# ------------------------------------------------------------------ tài liệu
def replace_tai_lieu(ho_so_id: int, docs: list[dict], ho_so_data: dict, db_path: Path | None = None) -> None:
    """Ghi toàn bộ danh sách tài liệu (sau khi xử lý) + dữ liệu hồ sơ đã tính lại."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM tai_lieu WHERE ho_so_id = ?", (ho_so_id,))
        for doc in docs:
            data = {k: v for k, v in doc.items() if not k.startswith("_") and k != "da_soat"}
            conn.execute(
                "INSERT INTO tai_lieu (ho_so_id, stt, du_lieu, nguon, da_soat) VALUES (?, ?, ?, ?, ?)",
                (ho_so_id, doc["stt"], _dump(data), _dump(doc.get("_nguon", {})), int(bool(doc.get("da_soat")))),
            )
        conn.execute("UPDATE ho_so SET du_lieu = ?, cap_nhat = ? WHERE id = ?", (_dump(ho_so_data), _now(), ho_so_id))


def update_tai_lieu(ho_so_id: int, stt: int, changes: dict, da_soat: bool | None = None,
                    db_path: Path | None = None) -> dict:
    """Người dùng sửa tay một tài liệu. Trường bị sửa được đánh dấu nguồn 'sửa tay'."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tai_lieu WHERE ho_so_id = ? AND stt = ?", (ho_so_id, stt)).fetchone()
        if row is None:
            raise KeyError(f"Không có tài liệu số {stt}")
        data, nguon = json.loads(row["du_lieu"]), json.loads(row["nguon"] or "{}")
        for k, v in changes.items():
            if k in ("stt", "trang_pdf"):
                continue  # không sửa tay được; đổi ranh giới văn bản bằng chức năng tách lại
            if data.get(k) != v:
                data[k] = v
                nguon[k] = "sửa tay"
        flag = row["da_soat"] if da_soat is None else int(da_soat)
        conn.execute(
            "UPDATE tai_lieu SET du_lieu = ?, nguon = ?, da_soat = ? WHERE id = ?",
            (_dump(data), _dump(nguon), flag, row["id"]),
        )
        return {**data, "_nguon": nguon, "da_soat": bool(flag)}


def write_docs(ho_so_id: int, docs: list[dict], db_path: Path | None = None) -> None:
    """Ghi lại giá trị + nguồn của các tài liệu đã có (giữ cờ đã soát)."""
    with connect(db_path) as conn:
        for doc in docs:
            data = {k: v for k, v in doc.items() if not k.startswith("_") and k != "da_soat"}
            conn.execute(
                "UPDATE tai_lieu SET du_lieu = ?, nguon = ?, da_soat = COALESCE(?, da_soat) "
                "WHERE ho_so_id = ? AND stt = ?",
                (_dump(data), _dump(doc.get("_nguon", {})),
                 None if "da_soat" not in doc else int(bool(doc["da_soat"])), ho_so_id, doc["stt"]),
            )


# ------------------------------------------------------------------ đọc
def load_ho_so(ho_so_id: int, db_path: Path | None = None) -> dict:
    """{'id', 'phong', 'ho_so', 'tai_lieu', 'tep_pdf', 'so_trang', 'trang_thai', 'loi'}."""
    with connect(db_path) as conn:
        row = _get_row(conn, ho_so_id)
        phong = defaults("phong")
        if row["phong_id"]:
            p = conn.execute("SELECT du_lieu FROM phong WHERE id = ?", (row["phong_id"],)).fetchone()
            phong.update(json.loads(p["du_lieu"]))
        docs = []
        for t in conn.execute("SELECT * FROM tai_lieu WHERE ho_so_id = ? ORDER BY stt", (ho_so_id,)):
            d = json.loads(t["du_lieu"])
            d["_nguon"] = json.loads(t["nguon"] or "{}")
            d["da_soat"] = bool(t["da_soat"])
            docs.append(d)
    return {
        "id": row["id"],
        "phong": phong,
        "ho_so": {**defaults("ho_so"), **json.loads(row["du_lieu"])},
        "tai_lieu": docs,
        "tep_pdf": row["tep_pdf"],
        "so_trang": row["so_trang"] or 0,
        "trang_thai": row["trang_thai"],
        "loi": row["loi"] or "",
        "cap_nhat": row["cap_nhat"],
    }


def list_ho_so(db_path: Path | None = None) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT h.id, h.ma_ho_so, h.cap_nhat, h.tep_pdf, h.so_trang, h.trang_thai, h.loi, "
            "json_extract(h.du_lieu, '$.tieu_de_ho_so') AS tieu_de, "
            "(SELECT COUNT(*) FROM tai_lieu t WHERE t.ho_so_id = h.id) AS so_tai_lieu, "
            "(SELECT COUNT(*) FROM tai_lieu t WHERE t.ho_so_id = h.id AND t.da_soat = 1) AS da_soat, "
            "(SELECT COUNT(*) FROM tai_lieu t WHERE t.ho_so_id = h.id "
            " AND json_extract(t.du_lieu, '$.can_kiem_tra') != '') AS can_kiem_tra "
            "FROM ho_so h ORDER BY h.cap_nhat DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ dùng cho Bước 4 (dòng lệnh)
def save_result(result: dict, pdf_path: str = "", db_path: Path | None = None) -> int:
    """Lưu kết quả {'phong', 'ho_so', 'tai_lieu'} của Bước 3 (tạo mới hoặc ghi đè theo mã hồ sơ)."""
    phong, ho_so, docs = result["phong"], result["ho_so"], result["tai_lieu"]
    ma = (ho_so.get("ma_ho_so") or "").strip()
    if not ma:
        raise ValueError("Hồ sơ chưa có mã hồ sơ — nhập 'ma_ho_so' trong file thông tin hồ sơ.")
    with connect(db_path) as conn:
        row = conn.execute("SELECT id FROM ho_so WHERE ma_ho_so = ?", (ma,)).fetchone()
    ho_so_id = row[0] if row else create_ho_so(phong, ho_so, db_path)
    update_ho_so_info(ho_so_id, phong, ho_so, db_path)
    if pdf_path:
        set_pdf(ho_so_id, pdf_path, sum(d.get("so_luong_trang", 0) for d in docs), db_path)
    replace_tai_lieu(ho_so_id, docs, ho_so, db_path)
    set_status(ho_so_id, "xong", "", db_path)
    return ho_so_id
