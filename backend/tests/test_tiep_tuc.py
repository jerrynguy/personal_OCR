"""Kiểm thử: PDF dài -> đọc chữ trước -> gợi ý trang đầu; tắt app giữa chừng -> mở lại làm tiếp; file gốc mất.
Tự bật / tắt server_gia.py ở cổng 8766:

    python tests/test_tiep_tuc.py <thư mục dữ liệu thử> <thư mục tạm>
"""

import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8766/api"
TESTDATA = Path(sys.argv[1]).resolve()
WORK = Path(sys.argv[2]).resolve()
DATA = WORK / "data_tiep_tuc"
s = requests.Session()
s.trust_env = False
failed = 0


def check(cond, msg):
    global failed
    print(("  OK  " if cond else "  SAI ") + msg)
    failed += not cond


def call(method, path, ok=True, **kw):
    r = s.request(method, BASE + path, timeout=120, **kw)
    if ok and r.status_code >= 400:
        raise SystemExit(f"LỖI {method} {path}: {r.status_code} {r.text[:400]}")
    return r


def start(ocr="0.1", llm="0.6"):
    p = subprocess.Popen([sys.executable, str(HERE / "server_gia.py"), str(DATA), str(TESTDATA), "8766", ocr, llm],
                         stdout=open(WORK / "server_tiep_tuc.log", "a"), stderr=subprocess.STDOUT)
    for _ in range(50):
        try:
            if s.get(BASE + "/health", timeout=1).ok:
                return p
        except requests.RequestException:
            time.sleep(0.2)
    raise SystemExit("server không chạy")


def wait(hid, timeout=90, until=("xong", "loi", "moi")):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = call("GET", f"/ho-so/{hid}").json()
        if d["trang_thai"] in until and not (d["tien_do"] and not d["tien_do"]["done"]):
            return d
        time.sleep(0.3)
    return d


shutil.rmtree(DATA, ignore_errors=True)
DATA.mkdir(parents=True)
srv = start()

# ---- PDF dài: tải lên, đọc chữ trước, gợi ý
hid = call("POST", "/ho-so", json={"ho_so": {"ma_ho_so": "DAI-01"}}).json()["id"]
with open(TESTDATA / "ho_so_dai.pdf", "rb") as f:
    up = call("POST", f"/ho-so/{hid}/pdf", files={"file": ("ho_so_dai.pdf", f, "application/pdf")}).json()
check(up["so_trang"] == 27, f"tải lên 27 trang ({up['so_trang']})")
g = call("GET", f"/ho-so/{hid}/goi-y").json()
check(g["da_doc"] == 0 and g["goi_y"] == [], f"chưa đọc chữ -> chưa có gợi ý ({g})")
r = call("GET", f"/ho-so/{hid}/trang/5/anh", params={"nho": 1})
check(r.headers["content-type"] == "image/jpeg", "ảnh nhỏ trang chưa đọc (vẽ thẳng từ PDF)")
call("POST", f"/ho-so/{hid}/doc-chu")
d = wait(hid)
check(d["trang_thai"] == "moi" and not d["tai_lieu"], f"đọc chữ xong, chưa tách: {d['trang_thai']} {len(d['tai_lieu'])}")
g = call("GET", f"/ho-so/{hid}/goi-y").json()
# 14 tài liệu, số trang 1 + k % 3
expect, page = [], 1
for k in range(14):
    expect.append(page)
    page += 1 + k % 3
check(g["goi_y"] == expect and g["da_doc"] == 27, f"gợi ý = trang đầu thật: {g['goi_y']}")
call("POST", f"/ho-so/{hid}/xu-ly", json={"ranh_gioi": g["goi_y"]})
d = wait(hid)
check(len(d["tai_lieu"]) == 14, f"14 tài liệu sau khi xác nhận gợi ý ({len(d['tai_lieu'])})")
check(d["tai_lieu"][1]["tep_tin_tai_lieu"] == "DAI-01.02.pdf", f"PDF tải lên: tên tệp app tạo ({d['tai_lieu'][1]['tep_tin_tai_lieu']})")
check(all(x["ai_trang_thai"] == "xong" for x in d["tai_lieu"]), "AI xong mọi văn bản")

# ---- tắt app giữa lúc AI đang chạy -> mở lại làm tiếp, không đọc lại văn bản AI đã xong
call("POST", f"/ho-so/{hid}/xu-ly", json={"ranh_gioi": g["goi_y"][:10]})  # đổi tách -> AI chạy lại 10 văn bản
t0 = time.time()
while time.time() - t0 < 30:
    d = call("GET", f"/ho-so/{hid}").json()
    done = sum(x.get("ai_trang_thai") == "xong" for x in d["tai_lieu"])
    if d["tien_do"] and d["tien_do"]["stage"] == "trich_xuat" and done >= 3 and len(d["tai_lieu"]) == 10:
        break
    time.sleep(0.2)
print(f"  tắt app khi đã AI xong {done}/10 văn bản")
srv.send_signal(signal.SIGKILL)  # như mất điện
srv.wait()
srv = start()
d = call("GET", f"/ho-so/{hid}").json()
check(d["trang_thai"] in ("cho", "dang_xu_ly"), f"mở lại: hồ sơ tự xếp lại hàng ({d['trang_thai']})")
d = wait(hid)
check(d["trang_thai"] == "xong" and len(d["tai_lieu"]) == 10 and all(x["ai_trang_thai"] == "xong" for x in d["tai_lieu"]),
      f"làm tiếp xong: {d['trang_thai']}, {len(d['tai_lieu'])} tài liệu")

# ---- hủy khi đang chờ / đang chạy
call("POST", "/hang-doi/tam-dung")
call("POST", f"/ho-so/{hid}/xu-ly", json={"ocr_lai": False})
d = call("GET", f"/ho-so/{hid}").json()
check(d["trang_thai"] == "cho" and d["tien_do"]["stage"] == "cho" and d["hang_doi_tam_dung"], "tạm dừng: hồ sơ chờ")
r = call("PUT", f"/ho-so/{hid}", json={"ho_so": {"tieu_de_ho_so": "Sửa khi đang chờ"}})
check(r.ok, "sửa thông tin được khi hồ sơ chỉ đang chờ")
call("POST", f"/ho-so/{hid}/huy")
d = call("GET", f"/ho-so/{hid}").json()
check(d["trang_thai"] == "xong", f"bỏ khỏi hàng: {d['trang_thai']}")
call("POST", "/hang-doi/tiep-tuc")

# ---- file gốc bị di chuyển
lo = WORK / "du_lieu_tam" / "Lô thử"
shutil.rmtree(lo.parent, ignore_errors=True)
shutil.copytree(TESTDATA / "Đà Lạt 1L" / "6", lo / "6")
sid = call("POST", "/nhap/quet", json={"duong_dan": str(lo)}).json()["id"]
while not (sc := call("GET", f"/nhap/quet/{sid}").json())["xong"]:
    time.sleep(0.2)
f = sc["ket_qua"]["ho_so"][0]
call("POST", "/hang-doi/tam-dung")
res = call("POST", "/nhap/tao", json={"quet_id": sid, "lo": "Lô thử", "khong_llm": True,
                                      "chon": [{"i": 0, "ma_ho_so": f["ma_goi_y"], "files": [0, 1, 2]}]}).json()
h2 = res["ids"][0]
(lo / "6" / "H01.15.06.100002.pdf").rename(lo / "6" / "doi_ten.pdf")
d = call("GET", f"/ho-so/{h2}").json()
check(d["file_thieu"] == ["H01.15.06.100002.pdf"] and d["co_pdf"], f"báo file thiếu: {d['file_thieu']}")
call("POST", "/hang-doi/tiep-tuc")
d = wait(h2)
check(d["trang_thai"] == "loi" and "H01.15.06.100002.pdf" in d["loi"], f"lỗi rõ ràng: {d['loi'][:120]}")
q = call("GET", "/hang-doi").json()
check(q["so_cho"] == 0 and q["dang_chay"] is None, "hồ sơ lỗi không kẹt trong hàng đợi")
(lo / "6" / "doi_ten.pdf").rename(lo / "6" / "H01.15.06.100002.pdf")
call("POST", f"/ho-so/{h2}/xu-ly", json={})
d = wait(h2)
check(d["trang_thai"] == "xong" and len(d["tai_lieu"]) == 3, f"để file về chỗ cũ -> xử lý được ({d['trang_thai']}, {len(d['tai_lieu'])})")
call("DELETE", f"/ho-so/{h2}")
check((lo / "6" / "H01.15.06.100001.pdf").exists(), "xóa hồ sơ không xóa file gốc")

srv.terminate()
print(f"\n{'TẤT CẢ ĐẠT' if not failed else f'{failed} KIỂM TRA SAI'}")
sys.exit(1 if failed else 0)
