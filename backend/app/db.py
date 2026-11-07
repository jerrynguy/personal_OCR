"""Lưu Phông / Hồ sơ / Tài liệu vào SQLite (data/sohoa.db).

Giá trị các trường lưu dạng JSON để khi sửa danh sách trường trong tt05.json
không phải đổi cấu trúc bảng. Mỗi hồ sơ xác định bằng mã hồ sơ (duy nhất).
CSDL cũ được tự nâng cấp khi mở — không mất dữ liệu.

File PDF của hồ sơ:
- tải lên: 1 file, chép vào data/ho_so/<id>/goc.pdf (cột tep_pdf);
- nhập thư mục: NHIỀU file, app đọc thẳng file gốc trên máy, không sao chép (cột ds_pdf, JSON).
Hàng đợi xử lý lưu ngay trong bảng ho_so (trang_thai = 'cho' + cho_xu_ly) để sống qua khi tắt app.
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
SCHEMA_VERSION = 3

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
CREATE TABLE IF NOT EXISTS cai_dat (
    khoa TEXT PRIMARY KEY,
    gia_tri TEXT
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
    ],
    # Xử lý hàng loạt: nhiều file nguồn, lô nhập, hàng đợi bền
    3: [
        "ALTER TABLE ho_so ADD COLUMN ds_pdf TEXT",
        "ALTER TABLE ho_so ADD COLUMN lo TEXT DEFAULT ''",
        "ALTER TABLE ho_so ADD COLUMN thu_muc TEXT DEFAULT ''",
        "ALTER TABLE ho_so ADD COLUMN cho_xu_ly TEXT",
        "ALTER TABLE ho_so ADD COLUMN uu_tien INTEGER DEFAULT 0",
        "ALTER TABLE ho_so ADD COLUMN cho_luc TEXT DEFAULT ''",
        "CREATE INDEX IF NOT EXISTS ho_so_cho ON ho_so (trang_thai, uu_tien, cho_luc)",
        "CREATE INDEX IF NOT EXISTS ho_so_lo ON ho_so (lo)",
    ],
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
def create_ho_so(phong: dict, ho_so: dict, db_path: Path | None = None, conn=None,
                 lo: str = "", thu_muc: str = "", ds_pdf: list[dict] | None = None) -> int:
    """Tạo hồ sơ. ds_pdf = [{'duong_dan', 'ten', 'so_trang'}] khi nhập từ thư mục (đọc thẳng file gốc).
    conn: dùng chung kết nối (tạo hàng loạt trong 1 giao dịch)."""
    ma = (ho_so.get("ma_ho_so") or "").strip()
    if not ma:
        raise ValueError("Thiếu mã hồ sơ")
    if conn is None:
        with connect(db_path) as c:
            return create_ho_so(phong, ho_so, conn=c, lo=lo, thu_muc=thu_muc, ds_pdf=ds_pdf)
    if conn.execute("SELECT 1 FROM ho_so WHERE ma_ho_so = ?", (ma,)).fetchone():
        raise ValueError(f"Mã hồ sơ '{ma}' đã tồn tại")
    phong_id = _upsert_phong(conn, {**defaults("phong"), **phong})
    so_trang = sum(int(f["so_trang"]) for f in ds_pdf) if ds_pdf else 0
    cur = conn.execute(
        "INSERT INTO ho_so (phong_id, ma_ho_so, du_lieu, cap_nhat, tao_luc, trang_thai, lo, thu_muc, ds_pdf, so_trang) "
        "VALUES (?, ?, ?, ?, ?, 'moi', ?, ?, ?, ?)",
        (phong_id, ma, _dump({**defaults("ho_so"), **ho_so, "ma_ho_so": ma}), _now(), _now(),
         lo or "", thu_muc or "", _dump(ds_pdf) if ds_pdf else None, so_trang),
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
    """PDF tải lên (thay cho mọi file nguồn cũ, kể cả file nhập từ thư mục)."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE ho_so SET tep_pdf = ?, ds_pdf = NULL, so_trang = ?, trang_thai = 'moi', loi = '', "
            "cho_xu_ly = NULL, cap_nhat = ? WHERE id = ?",
            (path, so_trang, _now(), ho_so_id),
        )


def set_status(ho_so_id: int, trang_thai: str, loi: str = "", db_path: Path | None = None) -> None:
    """Đổi trạng thái. Trạng thái kết thúc (không phải chờ / đang xử lý) -> bỏ khỏi hàng đợi."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE ho_so SET trang_thai = ?, loi = ?, cap_nhat = ?, "
            "cho_xu_ly = CASE WHEN ? IN ('cho', 'dang_xu_ly') THEN cho_xu_ly ELSE NULL END WHERE id = ?",
            (trang_thai, loi, _now(), trang_thai, ho_so_id),
        )


# ------------------------------------------------------------------ hàng đợi (bền, nằm trong CSDL)
def enqueue(ids: list[int], params: dict, uu_tien: int = 0, keep_order: bool = False,
            db_path: Path | None = None) -> int:
    """Xếp hồ sơ vào hàng đợi. Hồ sơ đang xử lý thì bỏ qua. Trả về số hồ sơ đã xếp.
    keep_order: xếp lại hồ sơ VỪA bị dừng giữa chừng (tạm dừng hàng đợi): giữ chỗ cũ trong hàng."""
    now = _now()
    n = 0
    with connect(db_path) as conn:
        for i in ids:
            cur = conn.execute(
                "UPDATE ho_so SET trang_thai = 'cho', cho_xu_ly = ?, loi = '', "
                "uu_tien = CASE WHEN trang_thai = 'cho' THEN MAX(uu_tien, ?) ELSE ? END, "
                "cho_luc = CASE WHEN (trang_thai = 'cho' OR ?) AND cho_luc != '' THEN cho_luc ELSE ? END "
                "WHERE id = ? AND (trang_thai != 'dang_xu_ly' OR ?)",
                (_dump(params), uu_tien, uu_tien, int(keep_order), now, i, int(keep_order)),
            )
            n += cur.rowcount
    return n


def next_pending(db_path: Path | None = None) -> tuple[int, dict, int] | None:
    """Hồ sơ tiếp theo cần xử lý: ưu tiên cao trước (việc người dùng vừa bấm), rồi theo thứ tự xếp."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, cho_xu_ly, uu_tien FROM ho_so WHERE trang_thai = 'cho' "
            "ORDER BY uu_tien DESC, cho_luc, id LIMIT 1"
        ).fetchone()
    return (row["id"], json.loads(row["cho_xu_ly"] or "{}"), row["uu_tien"] or 0) if row else None


def queue_position(ho_so_id: int, db_path: Path | None = None) -> int:
    """Thứ tự của hồ sơ trong hàng chờ (1 = làm tiếp theo), 0 nếu không chờ."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT trang_thai, uu_tien, cho_luc FROM ho_so WHERE id = ?", (ho_so_id,)).fetchone()
        if not row or row["trang_thai"] != "cho":
            return 0
        return conn.execute(
            "SELECT COUNT(*) FROM ho_so WHERE trang_thai = 'cho' AND (uu_tien > ? OR (uu_tien = ? AND "
            "(cho_luc < ? OR (cho_luc = ? AND id <= ?))))",
            (row["uu_tien"], row["uu_tien"], row["cho_luc"], row["cho_luc"], ho_so_id),
        ).fetchone()[0]


def queue_waiting(limit: int = 0, db_path: Path | None = None) -> list[dict]:
    """Các hồ sơ đang chờ (đúng thứ tự sẽ làm): id, mã, số trang, số tài liệu dự kiến, có chạy AI không."""
    sql = ("SELECT id, ma_ho_so, so_trang, cho_xu_ly, "
           "(SELECT COUNT(*) FROM tai_lieu t WHERE t.ho_so_id = ho_so.id) AS so_tai_lieu "
           "FROM ho_so WHERE trang_thai = 'cho' ORDER BY uu_tien DESC, cho_luc, id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    with connect(db_path) as conn:
        rows = conn.execute(sql).fetchall()
    out = []
    for r in rows:
        p = json.loads(r["cho_xu_ly"] or "{}")
        docs = len(p.get("ranh_gioi") or []) or r["so_tai_lieu"] or 1
        out.append({"id": r["id"], "ma_ho_so": r["ma_ho_so"], "so_trang": r["so_trang"] or 0,
                    "so_tai_lieu": docs, "co_ai": not p.get("khong_llm") and p.get("kind", "xu_ly") == "xu_ly",
                    "kind": p.get("kind", "xu_ly")})
    return out


def dequeue(ids: list[int], db_path: Path | None = None) -> int:
    """Bỏ hồ sơ đang CHỜ khỏi hàng đợi (hồ sơ đang chạy thì hủy bằng JobQueue)."""
    n = 0
    with connect(db_path) as conn:
        for i in ids:
            n += conn.execute(
                "UPDATE ho_so SET cho_xu_ly = NULL, cap_nhat = ?, trang_thai = CASE WHEN EXISTS "
                "(SELECT 1 FROM tai_lieu t WHERE t.ho_so_id = ho_so.id) THEN 'xong' ELSE 'moi' END "
                "WHERE id = ? AND trang_thai = 'cho'",
                (_now(), i),
            ).rowcount
    return n


def end_stopped(ho_so_id: int, loi: str, error: bool = False, db_path: Path | None = None) -> None:
    """Kết thúc lần xử lý bị hủy / lỗi: bỏ khỏi hàng đợi; trạng thái 'lỗi', hoặc 'xong'/'mới tạo' khi hủy."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE ho_so SET cho_xu_ly = NULL, loi = ?, cap_nhat = ?, trang_thai = CASE WHEN ? THEN 'loi' "
            "WHEN EXISTS (SELECT 1 FROM tai_lieu t WHERE t.ho_so_id = ho_so.id) THEN 'xong' ELSE 'moi' END "
            "WHERE id = ?",
            (loi, _now(), int(error), ho_so_id),
        )
        conn.execute(
            "UPDATE tai_lieu SET du_lieu = json_set(du_lieu, '$.ai_trang_thai', 'huy') "
            "WHERE ho_so_id = ? AND json_extract(du_lieu, '$.ai_trang_thai') = 'cho'",
            (ho_so_id,),
        )


def code_of(ho_so_id: int, db_path: Path | None = None) -> str:
    with connect(db_path) as conn:
        row = conn.execute("SELECT ma_ho_so FROM ho_so WHERE id = ?", (ho_so_id,)).fetchone()
    return row[0] if row else ""


def recover_interrupted(db_path: Path | None = None) -> int:
    """Mở app sau khi bị tắt giữa chừng: hồ sơ đang xử lý dở -> xếp lại vào đầu hàng, làm tiếp."""
    with connect(db_path) as conn:
        rows = conn.execute("SELECT id, cho_xu_ly FROM ho_so WHERE trang_thai = 'dang_xu_ly'").fetchall()
        for r in rows:
            p = json.loads(r["cho_xu_ly"] or "{}")
            p["tiep_tuc"] = True
            conn.execute("UPDATE ho_so SET trang_thai = 'cho', cho_xu_ly = ?, uu_tien = MAX(uu_tien, 1) "
                         "WHERE id = ?", (_dump(p), r["id"]))
    return len(rows)


def get_setting(key: str, default: str = "", db_path: Path | None = None) -> str:
    with connect(db_path) as conn:
        row = conn.execute("SELECT gia_tri FROM cai_dat WHERE khoa = ?", (key,)).fetchone()
    return row[0] if row and row[0] is not None else default


def set_setting(key: str, value: str, db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute("INSERT INTO cai_dat (khoa, gia_tri) VALUES (?, ?) "
                     "ON CONFLICT(khoa) DO UPDATE SET gia_tri = excluded.gia_tri", (key, value))


def existing_codes(codes: list[str], db_path: Path | None = None) -> set[str]:
    with connect(db_path) as conn:
        found = set()
        for i in range(0, len(codes), 500):
            part = codes[i:i + 500]
            q = ",".join("?" * len(part))
            found |= {r[0] for r in conn.execute(f"SELECT ma_ho_so FROM ho_so WHERE ma_ho_so IN ({q})", part)}
    return found


def imported_folders(db_path: Path | None = None) -> dict[str, tuple[int, str]]:
    """Thư mục đã nhập trước đây: {đường dẫn thư mục (chữ thường): (id, mã hồ sơ)}."""
    with connect(db_path) as conn:
        return {r["thu_muc"].lower(): (r["id"], r["ma_ho_so"])
                for r in conn.execute("SELECT id, ma_ho_so, thu_muc FROM ho_so WHERE thu_muc != ''")}


def delete_ho_so(ho_so_id: int, db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM ho_so WHERE id = ?", (ho_so_id,))


def _resolve_pdf(ho_so_id: int, stored: str | None) -> str | None:
    """Đường dẫn PDF lưu trong CSDL là tuyệt đối. Nếu thư mục data/ đã bị dời đi (vd. đổi cấu trúc
    thư mục, chép sang máy khác) thì tìm lại file ở vị trí tương ứng trong DATA_DIR hiện tại."""
    if not stored or Path(stored).exists():
        return stored
    candidates = [DATA_DIR / "ho_so" / str(ho_so_id) / "goc.pdf"]
    parts = Path(stored.replace("\\", "/")).parts
    if "data" in parts:
        i = len(parts) - 1 - parts[::-1].index("data")
        candidates.append(DATA_DIR.joinpath(*parts[i + 1:]))
    for c in candidates:
        if c.exists():
            return str(c)
    return stored


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
    ho_so = {**defaults("ho_so"), **json.loads(row["du_lieu"])}
    tep_pdf = _resolve_pdf(row["id"], row["tep_pdf"])
    return {
        "id": row["id"],
        "phong": phong,
        "ho_so": ho_so,
        "tai_lieu": docs,
        "tep_pdf": tep_pdf,
        "nguon_pdf": _sources(row, tep_pdf, ho_so),
        "tu_thu_muc": bool(row["ds_pdf"]),
        "thu_muc": row["thu_muc"] or "",
        "lo": row["lo"] or "",
        "so_trang": row["so_trang"] or 0,
        "trang_thai": row["trang_thai"],
        "loi": row["loi"] or "",
        "cho_xu_ly": json.loads(row["cho_xu_ly"]) if row["cho_xu_ly"] else None,
        "cap_nhat": row["cap_nhat"],
    }


def _sources(row, tep_pdf: str | None, ho_so: dict) -> list[dict]:
    """Danh sách file PDF của hồ sơ theo thứ tự trang: [{'duong_dan', 'ten', 'so_trang', 'trang_dau'}].
    Trang của hồ sơ đánh số liên tục qua các file (file 2 bắt đầu sau trang cuối của file 1)."""
    if row["ds_pdf"]:
        files = json.loads(row["ds_pdf"])
    elif tep_pdf:
        files = [{"duong_dan": tep_pdf, "ten": ho_so.get("tep_tin_ho_so") or Path(tep_pdf).name,
                  "so_trang": row["so_trang"] or 0}]
    else:
        return []
    start = 1
    out = []
    for f in files:
        out.append({**f, "trang_dau": start})
        start += int(f["so_trang"])
    return out


LIST_COLS = (
    "SELECT h.id, h.ma_ho_so, h.cap_nhat, h.tep_pdf, h.so_trang, h.trang_thai, h.loi, h.lo, "
    "json_extract(h.du_lieu, '$.tieu_de_ho_so') AS tieu_de, "
    "(SELECT COUNT(*) FROM tai_lieu t WHERE t.ho_so_id = h.id) AS so_tai_lieu, "
    "(SELECT COUNT(*) FROM tai_lieu t WHERE t.ho_so_id = h.id AND t.da_soat = 1) AS da_soat, "
    "(SELECT COUNT(*) FROM tai_lieu t WHERE t.ho_so_id = h.id "
    " AND json_extract(t.du_lieu, '$.can_kiem_tra') != '') AS can_kiem_tra, "
    "(SELECT COUNT(*) FROM tai_lieu t WHERE t.ho_so_id = h.id "
    " AND json_extract(t.du_lieu, '$.ai_trang_thai') IN ('tat', 'huy', 'loi')) AS chua_ai "
    "FROM ho_so h"
)


def _filter_sql(ids=None, lo=None, q=None, trang_thai=None) -> tuple[str, list]:
    where, args = [], []
    if ids is not None:
        ids = [int(i) for i in ids] or [-1]
        where.append(f"h.id IN ({','.join('?' * len(ids))})")
        args += ids
    if lo is not None and lo != "":
        where.append("h.lo = ?")
        args.append("" if lo == "-" else lo)  # '-' = hồ sơ tạo lẻ (không thuộc lô nào)
    if q:
        where.append("(h.ma_ho_so LIKE ? OR json_extract(h.du_lieu, '$.tieu_de_ho_so') LIKE ? OR h.thu_muc LIKE ?)")
        args += [f"%{q}%"] * 3
    if trang_thai == "can_kiem_tra":
        where.append("EXISTS (SELECT 1 FROM tai_lieu t WHERE t.ho_so_id = h.id AND t.da_soat = 0 "
                     "AND json_extract(t.du_lieu, '$.can_kiem_tra') != '')")
    elif trang_thai == "chua_soat":
        where.append("EXISTS (SELECT 1 FROM tai_lieu t WHERE t.ho_so_id = h.id AND t.da_soat = 0)")
    elif trang_thai:
        where.append("h.trang_thai = ?")
        args.append(trang_thai)
    return (" WHERE " + " AND ".join(where)) if where else "", args


def list_ho_so(db_path: Path | None = None) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(LIST_COLS + " ORDER BY h.cap_nhat DESC").fetchall()
    return [dict(r) for r in rows]


def query_ho_so(ids=None, lo=None, q=None, trang_thai=None, offset: int = 0, limit: int = 50,
                order: str = "moi_nhat", db_path: Path | None = None) -> tuple[int, list[dict]]:
    """Danh sách hồ sơ có lọc + phân trang. Trả về (tổng số khớp, các dòng của trang này)."""
    where, args = _filter_sql(ids, lo, q, trang_thai)
    order_sql = " ORDER BY h.cap_nhat DESC, h.id DESC" if order == "moi_nhat" else " ORDER BY h.lo, h.id"
    with connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM ho_so h" + where, args).fetchone()[0]
        sql = LIST_COLS + where + order_sql + (f" LIMIT {int(limit)} OFFSET {int(offset)}" if limit else "")
        rows = conn.execute(sql, args).fetchall()
    return total, [dict(r) for r in rows]


def select_ids(ids=None, lo=None, q=None, trang_thai=None, db_path: Path | None = None) -> list[int]:
    """id các hồ sơ khớp bộ lọc, theo thứ tự lô rồi thứ tự tạo (= thứ tự thư mục khi nhập)."""
    where, args = _filter_sql(ids, lo, q, trang_thai)
    with connect(db_path) as conn:
        return [r[0] for r in conn.execute("SELECT h.id FROM ho_so h" + where + " ORDER BY h.lo, h.id", args)]


def list_lo(db_path: Path | None = None) -> list[dict]:
    """Các lô đã nhập (thư mục cha) + số hồ sơ, số hồ sơ xong / chờ."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT lo, COUNT(*) AS so_ho_so, SUM(trang_thai = 'xong') AS xong, "
            "SUM(trang_thai IN ('cho', 'dang_xu_ly')) AS dang_cho, MAX(tao_luc) AS tao_luc "
            "FROM ho_so GROUP BY lo ORDER BY MAX(tao_luc) DESC"
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
