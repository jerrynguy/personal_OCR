"""BƯỚC 5 — Kiểm tra backend qua API, đúng như giao diện sẽ gọi.

Cửa sổ PowerShell 1:   python scripts/run_server.py --dev
Cửa sổ PowerShell 2:   python scripts/step5_api_test.py [file.pdf]

Tạo hồ sơ thử (mã TEST-<giờ phút giây>), tải PDF lên, xử lý, theo dõi tiến độ,
sửa tay 1 tài liệu, tải file Excel về data/step5/.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path, nargs="?", default=DATA_DIR / "samples" / "mau_ho_so.pdf")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--token", default="", help="Không cần khi server chạy --dev")
    args = parser.parse_args()

    s = requests.Session()
    s.trust_env = False  # gọi thẳng 127.0.0.1, không qua proxy
    s.headers["X-Token"] = args.token
    api = args.url + "/api"

    def call(method: str, path: str, **kw):
        r = s.request(method, api + path, timeout=60, **kw)
        if r.status_code >= 400:
            raise SystemExit(f"LỖI {method} {path}: {r.status_code} {r.text[:300]}")
        return r

    try:
        call("GET", "/health")
    except requests.ConnectionError:
        print(f"Không kết nối được {args.url}. Mở cửa sổ khác và chạy: python scripts/run_server.py --dev")
        return 1

    he_thong = call("GET", "/he-thong").json()
    if he_thong.get("nguon_dien"):
        print(f"!!! CẢNH BÁO: máy {he_thong['nguon_dien']} -> sẽ chạy chậm hơn nhiều lần")
    print("Model OCR:", ", ".join(f"{k} {'OK' if v else 'THIẾU'}" for k, v in he_thong["model_ocr"].items()))
    print("Model LLM:", he_thong["model_llm"] or "(chưa chọn)")

    info_file = args.pdf.with_suffix(".ho_so.json")
    info = json.loads(info_file.read_text(encoding="utf-8")) if info_file.exists() else {"phong": {}, "ho_so": {}}
    info["ho_so"]["ma_ho_so"] = "TEST-" + datetime.now().strftime("%H%M%S")
    ho_so = call("POST", "/ho-so", json=info).json()
    hid = ho_so["id"]
    print(f"\n1) Tạo hồ sơ {ho_so['ho_so']['ma_ho_so']} (id {hid})")

    with open(args.pdf, "rb") as f:
        up = call("POST", f"/ho-so/{hid}/pdf", files={"file": (args.pdf.name, f, "application/pdf")}).json()
    print(f"2) Tải PDF lên: {up['so_trang']} trang" + (f" — {up['canh_bao']}" if up["canh_bao"] else ""))

    job = call("POST", f"/ho-so/{hid}/xu-ly", json={}).json()
    print(f"3) Bắt đầu xử lý (mã {job['id']}). Tiến độ:")
    last = None
    t0 = time.time()
    while True:
        p = call("GET", f"/ho-so/{hid}/tien-do").json()
        key = (p["stage"], p["current"], p["message"])
        if key != last:  # chỉ in khi giai đoạn / tiến độ thay đổi
            line = f"   [{p['elapsed']:4d}s] {p['stage_label']}"
            if p["total"]:
                line += f" {p['current']}/{p['total']}"
            if p["message"]:
                line += f" — {p['message']}"
            print(line)
            last = key
        if p["done"]:
            break
        time.sleep(1)
    if p["stage"] != "xong":
        print(f"   Không thành công: {p['stage_label']} {p['error']}")
        return 1
    print(f"   Xong sau {time.time() - t0:.0f}s. Thời gian từng giai đoạn:")
    for name, sec in p["thoi_gian_giai_doan"].items():
        print(f"      {name:30s} {sec:6.1f}s")

    detail = call("GET", f"/ho-so/{hid}").json()
    print(f"\n4) Kết quả: {len(detail['tai_lieu'])} tài liệu")
    for d in detail["tai_lieu"]:
        so = "/".join(filter(None, [d["so_cua_tai_lieu"], d["ky_hieu_cua_tai_lieu"]]))
        print(f"   {d['stt']}. [trang {d['trang_pdf']}] {d['ten_loai_tai_lieu']} {so} ngày {d['ngay_ban_hanh']}"
              f" — {d['trich_yeu_noi_dung'][:60]}")
        if d["can_kiem_tra"]:
            print(f"      cần kiểm tra: {d['can_kiem_tra']}")

    upd = call("PUT", f"/ho-so/{hid}/tai-lieu/1",
               json={"thay_doi": {"ghi_chu": "Đã soát bằng script Bước 5"}, "da_soat": True}).json()
    print(f"\n5) Sửa tay tài liệu 1: ghi chú = '{upd['tai_lieu']['ghi_chu']}', "
          f"nguồn = {upd['tai_lieu']['_nguon'].get('ghi_chu')}, đã soát = {upd['tai_lieu']['da_soat']}")

    out = DATA_DIR / "step5"
    out.mkdir(parents=True, exist_ok=True)
    r = call("GET", f"/ho-so/{hid}/xuat/xlsx")
    xlsx = out / f"{detail['ho_so']['ma_ho_so']}.xlsx"
    xlsx.write_bytes(r.content)
    print(f"6) Tải Excel: {xlsx} ({len(r.content) // 1024} KB)")

    print("\nDanh sách hồ sơ trong CSDL:")
    for h in call("GET", "/ho-so", params={"moi_trang": 500}).json()["ho_so"]:
        print(f"   [{h['id']}] {h['ma_ho_so']:18s} {h['trang_thai']:10s} {h['so_tai_lieu']} tài liệu, "
              f"{h['can_kiem_tra']} cần kiểm tra, {h['da_soat']} đã soát")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
