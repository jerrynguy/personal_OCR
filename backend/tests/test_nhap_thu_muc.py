"""Kiểm thử API nhập thư mục + hàng đợi + xuất gộp. Cần server_gia.py đang chạy ở cổng 8765:

    python tests/test_nhap_thu_muc.py <thư mục dữ liệu thử> <thư mục data của server>
"""

import io
import sys
import time
import zipfile
from pathlib import Path

import requests
from openpyxl import load_workbook

BASE = "http://127.0.0.1:8765/api"
TESTDATA = Path(sys.argv[1]).resolve()
s = requests.Session()
s.trust_env = False


def call(method, path, **kw):
    r = s.request(method, BASE + path, timeout=120, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"LỖI {method} {path}: {r.status_code} {r.text[:400]}")
    return r


def check(cond, msg):
    print(("  OK  " if cond else "  SAI ") + msg)
    if not cond:
        global failed
        failed += 1


failed = 0
root = TESTDATA / "Đà Lạt 1L"
sid = call("POST", "/nhap/quet", json={"duong_dan": str(root)}).json()["id"]
while True:
    sc = call("GET", f"/nhap/quet/{sid}").json()
    if sc["xong"]:
        break
    time.sleep(0.2)
check(not sc["loi"], f"quét xong, lỗi: {sc['loi']!r}")
kq = sc["ket_qua"]
print(f"  {kq['so_ho_so']} hồ sơ, {kq['so_file']} file, {kq['so_trang']} trang, {kq['so_file_goi_y_gop']} gợi ý gộp")
by = {f["ten"]: f for f in kq["ho_so"]}
check([f["ten"] for f in kq["ho_so"]] == ["1", "2", "3", "4", "5", "6", "10"], "thứ tự thư mục tự nhiên 1..6, 10")
check(by["1"]["ma_goi_y"] == "H01.15.01", f"mã thư mục 1 = {by['1']['ma_goi_y']}")
check(by["2"]["ma_goi_y"] == "Đà Lạt 1L.2", f"mã thư mục 2 (1 file) = {by['2']['ma_goi_y']}")
check(by["4"]["ma_goi_y"] == "Đà Lạt 1L.4" and by["4"]["ma_tu"] == "thu_muc_vi_trung", f"thư mục 4 trùng 'Scan' -> {by['4']['ma_goi_y']}")
g1 = {x["ten"]: x.get("goi_y_gop") for x in by["1"]["files"]}
check(g1 == {"H01.15.01.1.pdf": ["H01.15.01.100001.pdf", "H01.15.01.100002.pdf"],
             "H01.15.01.100001.pdf": None, "H01.15.01.100002.pdf": None}, f"gợi ý gộp thư mục 1: {g1}")
g3 = {x["ten"]: bool(x.get("goi_y_gop")) for x in by["3"]["files"]}
check(g3 == {"H01.15.03.1.pdf": True, "H01.15.03.100001.pdf": False, "H01.15.03.100002.pdf": False,
             "H01.15.03.100003.pdf": False}, f"gợi ý gộp thư mục 3 (ảnh nén lại): {g3}")
g6 = {x["ten"]: (bool(x.get("goi_y_gop")), x["loi"]) for x in by["6"]["files"]}
check(sum(v[0] for v in g6.values()) == 0 and g6["H01.15.06.100004.pdf"][1], f"thư mục 6: không gộp, file hỏng báo lỗi {g6}")

# Chọn: bỏ file gộp ở thư mục 1 và 3 (như người dùng bấm "bỏ tích file gợi ý gộp"), bỏ thư mục 5
chon = []
for i, f in enumerate(kq["ho_so"]):
    if f["ten"] == "5":
        continue
    files = [k for k, x in enumerate(f["files"]) if not x.get("goi_y_gop") and not x["loi"]]
    chon.append({"i": i, "ma_ho_so": f["ma_goi_y"], "tieu_de_ho_so": f"Hồ sơ thư mục {f['ten']}", "files": files})
res = call("POST", "/nhap/tao", json={"quet_id": sid, "chon": chon, "lo": kq["ten_lo"], "khong_llm": False,
                                      "phong": {"ma_phong": "P01", "ten_phong": "UBND TP Đà Lạt"},
                                      "ho_so": {"thoi_han_luu_tru": "Vĩnh viễn", "muc_do_tiep_can": "Công khai"}}).json()
check(res["da_tao"] == 6 and not res["loi"], f"tạo 6 hồ sơ: {res['da_tao']} lỗi {res['loi']}")
ids = res["ids"]

# tạo lại -> mã trùng
res2 = call("POST", "/nhap/tao", json={"quet_id": sid, "chon": chon[:1], "lo": kq["ten_lo"]}).json()
check(res2["da_tao"] == 0 and "đã tồn tại" in res2["loi"][0]["loi"], f"tạo trùng bị chặn: {res2['loi']}")

q = call("GET", "/hang-doi").json()
check(q["so_cho"] + (1 if q["dang_chay"] else 0) == 6, f"hàng đợi có 6 hồ sơ (chờ {q['so_cho']}, ước tính {q['uoc_tinh_giay']}s)")

# tạm dừng giữa chừng rồi chạy tiếp
time.sleep(1.5)
call("POST", "/hang-doi/tam-dung")
time.sleep(0.5)
q = call("GET", "/hang-doi").json()
check(q["tam_dung"] and q["dang_chay"] is None, "tạm dừng: không còn hồ sơ đang chạy")
d0 = call("GET", f"/ho-so/{ids[0]}").json()
print("  hồ sơ 1 sau tạm dừng:", d0["trang_thai"], d0["tien_do"] and d0["tien_do"]["message"])
call("POST", "/hang-doi/tiep-tuc")

t0 = time.time()
while time.time() - t0 < 120:
    rows = call("GET", "/ho-so", params={"lo": kq["ten_lo"], "moi_trang": 100}).json()["ho_so"]
    if all(r["trang_thai"] == "xong" for r in rows):
        break
    time.sleep(1)
check(all(r["trang_thai"] == "xong" for r in rows), "mọi hồ sơ của lô đã xong: " + str([r["trang_thai"] for r in rows]))

d1 = call("GET", f"/ho-so/{ids[0]}").json()
check(len(d1["tai_lieu"]) == 2, f"hồ sơ 1 có 2 tài liệu (mỗi file 1): {[d['trang_pdf'] for d in d1['tai_lieu']]}")
t = d1["tai_lieu"]
check([x["tep_tin_tai_lieu"] for x in t] == ["H01.15.01.100001.pdf", "H01.15.01.100002.pdf"],
      f"cột Tệp tin = tên file gốc: {[x['tep_tin_tai_lieu'] for x in t]}")
check(t[0]["ma_luu_tru_tai_lieu"] == "H01.15.01.01", f"mã lưu trữ {t[0]['ma_luu_tru_tai_lieu']}")
check(t[0]["ten_loai_tai_lieu"] == "Quyết định" and t[0]["so_cua_tai_lieu"] == "101", f"luật đọc: {t[0]['ten_loai_tai_lieu']} {t[0]['so_cua_tai_lieu']}/{t[0]['ky_hieu_cua_tai_lieu']}")
check(t[0]["ai_trang_thai"] == "xong" and t[0]["trich_yeu_noi_dung"], f"AI: {t[0]['ai_trang_thai']} '{t[0]['trich_yeu_noi_dung']}'")
check(t[0]["muc_do_tiep_can"] == "Công khai", "thông tin chung xuống tài liệu")
check(d1["nguon_pdf"][1]["trang_dau"] == 3 and d1["so_trang"] == 3, f"trang liên tục qua 2 file: {d1['nguon_pdf']}")
check(d1["lo"] == "Đà Lạt 1L", "lô")

# ảnh: trang đã OCR -> JPEG nhỏ, không còn PNG 300 DPI
pdir = Path(sys.argv[2]) / "ho_so" / str(ids[0]) / "trang"
check(not list(pdir.glob("*.png")) and len(list(pdir.glob("page_*[0-9].jpg"))) == 3, f"chỉ giữ JPEG xem: {sorted(p.name for p in pdir.iterdir())}")
r = call("GET", f"/ho-so/{ids[0]}/trang/3/anh")
check(r.headers["content-type"] == "image/jpeg" and len(r.content) < 400_000, f"ảnh trang 3: {len(r.content)//1024} KB")
r = call("GET", f"/ho-so/{ids[0]}/trang/3/anh", params={"nho": 1})
check(r.headers["content-type"] == "image/jpeg", "ảnh nhỏ")

# xuất 1 hồ sơ: zip PDF = file gốc nguyên vẹn
r = call("GET", f"/ho-so/{ids[0]}/xuat/pdf")
zf = zipfile.ZipFile(io.BytesIO(r.content))
orig = (root / "1" / "H01.15.01.100001.pdf").read_bytes()
check(sorted(zf.namelist()) == ["H01.15.01.100001.pdf", "H01.15.01.100002.pdf"] and zf.read("H01.15.01.100001.pdf") == orig,
      f"zip PDF chép nguyên file gốc: {zf.namelist()}")

# xuất gộp
r = call("GET", "/xuat/xlsx", params={"lo": kq["ten_lo"]})
wb = load_workbook(io.BytesIO(r.content))
ws = wb.active
check(ws.max_column == 23, f"Excel gộp 23 cột ({ws.max_column})")
n_docs = sum(len(call("GET", f"/ho-so/{i}").json()["tai_lieu"]) for i in ids)
check(ws.max_row - 1 == n_docs, f"Excel gộp {ws.max_row - 1} dòng = {n_docs} tài liệu")
codes = [ws.cell(row=k, column=2).value for k in range(2, ws.max_row + 1)]
check(codes[:3] == ["H01.15.01.01", "H01.15.01.02", "Đà Lạt 1L.2.01"], f"thứ tự theo hồ sơ: {codes[:4]}")
check(ws.cell(row=1, column=22).value == "Tệp tin tài liệu" and ws.cell(row=2, column=22).value == "H01.15.01.100001.pdf", "cột 22")
r = call("GET", "/xuat/xlsx-zip", params={"ids": ",".join(map(str, ids[:3]))})
zf = zipfile.ZipFile(io.BytesIO(r.content))
check(len(zf.namelist()) == 3 and "H01.15.01.xlsx" in zf.namelist(), f"zip mỗi hồ sơ 1 file: {zf.namelist()}")

# danh sách lọc + phân trang
lst = call("GET", "/ho-so", params={"lo": kq["ten_lo"], "moi_trang": 2, "trang": 2}).json()
check(lst["tong"] == 6 and len(lst["ho_so"]) == 2, f"phân trang: tổng {lst['tong']}, trang 2 có {len(lst['ho_so'])}")
lst = call("GET", "/ho-so", params={"q": "Scan"}).json()
check(lst["tong"] == 0, "tìm theo mã")
lst = call("GET", "/ho-so", params={"q": "H01.15.03"}).json()
check(lst["tong"] == 1, "tìm H01.15.03")
check(any(x["lo"] == "Đà Lạt 1L" and x["so_ho_so"] == 6 for x in call("GET", "/lo").json()), "danh sách lô")

# quét lại -> thư mục đã nhập được đánh dấu
sid2 = call("POST", "/nhap/quet", json={"duong_dan": str(root)}).json()["id"]
while not (sc2 := call("GET", f"/nhap/quet/{sid2}").json())["xong"]:
    time.sleep(0.2)
da = {f["ten"]: bool(f["da_nhap"]) for f in sc2["ket_qua"]["ho_so"]}
check(da == {"1": True, "2": True, "3": True, "4": True, "5": False, "6": True, "10": True}, f"đã nhập: {da}")

# chạy lại chỉ luật cho cả lô ('bỏ qua AI'), giữ ô sửa tay
call("PUT", f"/ho-so/{ids[0]}/tai-lieu/1", json={"thay_doi": {"ghi_chu": "sửa tay"}, "da_soat": True})
n = call("POST", "/hang-doi/them", json={"loc": {"lo": kq["ten_lo"]}, "khong_llm": True}).json()["da_xep"]
check(n == 6, f"xếp lại {n} hồ sơ")
t0 = time.time()
while time.time() - t0 < 60:
    if all(r["trang_thai"] == "xong" for r in call("GET", "/ho-so", params={"lo": kq["ten_lo"]}).json()["ho_so"]):
        break
    time.sleep(0.5)
d1 = call("GET", f"/ho-so/{ids[0]}").json()["tai_lieu"][0]
check(d1["ghi_chu"] == "sửa tay" and d1["da_soat"], "giữ ô sửa tay + đã soát khi chạy lại")
check(d1["ai_trang_thai"] == "tat", "chạy lại không AI")

print(f"\n{'TẤT CẢ ĐẠT' if not failed else f'{failed} KIỂM TRA SAI'}")
sys.exit(1 if failed else 0)
