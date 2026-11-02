"""BƯỚC 4 — Lưu kết quả Bước 3 vào SQLite và xuất Excel / CSV / PDF từng tài liệu.

    python scripts/step4_export.py <file.pdf>          # dùng data/step3/<tên file>/ket_qua.json
    python scripts/step4_export.py --danh-sach         # xem các hồ sơ đã lưu trong CSDL

Kết quả ở data/xuat/<mã hồ sơ>/:
    <mã hồ sơ>.xlsx            4 sheet: Phông, Hồ sơ, Tài liệu, Mục lục văn bản
    csv/<mã hồ sơ>_*.csv       cùng nội dung, mỗi sheet một file CSV (UTF-8, mở được bằng Excel)
    tai_lieu/<mã lưu trữ>.pdf  PDF hồ sơ tách thành từng tài liệu
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR  # noqa: E402
from app.db import DB_PATH, list_ho_so, load_ho_so, save_result  # noqa: E402
from app.export import export_csv, export_xlsx, split_pdf  # noqa: E402


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", s).strip() or "ho_so"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path, nargs="?")
    parser.add_argument("--ket-qua", type=Path, help="File ket_qua.json (mặc định: của Bước 3)")
    parser.add_argument("--danh-sach", action="store_true", help="Liệt kê hồ sơ đã lưu")
    args = parser.parse_args()

    if args.danh_sach:
        rows = list_ho_so()
        print(f"CSDL: {DB_PATH} — {len(rows)} hồ sơ")
        for r in rows:
            print(f"  [{r['id']}] {r['ma_ho_so']:20s} {r['so_tai_lieu']:3d} tài liệu  {r['cap_nhat']}  {r['tieu_de'] or ''}")
        return 0
    if not args.pdf:
        parser.error("cần đường dẫn PDF (hoặc --danh-sach)")

    result_file = args.ket_qua or DATA_DIR / "step3" / args.pdf.stem / "ket_qua.json"
    if not result_file.exists():
        print(f"Chưa có {result_file}. Chạy Bước 3 trước: python scripts/step3_extract_pdf.py {args.pdf}")
        return 1
    result = json.loads(result_file.read_text(encoding="utf-8"))

    ho_so_id = save_result(result, str(args.pdf.resolve()))
    saved = load_ho_so(ho_so_id)  # đọc lại từ CSDL để chắc chắn đã lưu đủ
    ma = saved["ho_so"]["ma_ho_so"]
    print(f"Đã lưu vào CSDL: hồ sơ {ma} (id {ho_so_id}), {len(saved['tai_lieu'])} tài liệu -> {DB_PATH}")

    out_dir = DATA_DIR / "xuat" / safe_name(ma)
    xlsx = export_xlsx(saved, out_dir / f"{safe_name(ma)}.xlsx")
    print(f"Excel : {xlsx}")
    for p in export_csv(saved, out_dir / "csv", safe_name(ma)):
        print(f"CSV   : {p}")
    for p in split_pdf(args.pdf, saved["tai_lieu"], out_dir / "tai_lieu"):
        print(f"PDF   : {p}")

    warn = [d for d in saved["tai_lieu"] if d.get("can_kiem_tra")]
    if warn:
        print(f"\n{len(warn)} tài liệu cần kiểm tra (ô tô vàng trong sheet 'Tài liệu'):")
        for d in warn:
            print(f"  {d['stt']:3d}. {d['can_kiem_tra']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
