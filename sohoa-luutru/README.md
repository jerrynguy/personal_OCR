# Số hóa Lưu trữ (offline)

App desktop đọc **PDF scan hồ sơ lưu trữ**, OCR bằng **PaddleOCR**, trích xuất trường
dữ liệu theo **Thông tư 05/2025/TT-BNV** (Phông → Hồ sơ → Tài liệu) bằng **LLM chạy
trong máy** (llama.cpp + Gemma 4), rồi xuất **.xlsx / .csv**.
Toàn bộ chạy offline: không gửi ảnh hay dữ liệu ra internet.

Máy mục tiêu: HP ZBook Firefly G8 (i7-1185G7, 32GB RAM, Intel Iris Xe, Windows).

## Lộ trình — làm xong bước nào mới sang bước tiếp theo

| Bước | Nội dung | Trạng thái |
|---|---|---|
| **1** | Môi trường Python, tách PDF thành ảnh, OCR tiếng Việt offline | ⏳ đang làm |
| 2 | llama.cpp + Gemma 4 26B-A4B, đo tốc độ, LLM trả JSON theo schema | |
| 3 | Schema TT05 + luật trích xuất (số/ký hiệu, ngày, tên loại, cơ quan, độ mật, tờ số) + tách PDF thành từng văn bản | |
| 4 | Pipeline đầy đủ + SQLite + xuất Excel (chạy bằng dòng lệnh) | |
| 5 | Backend FastAPI | |
| 6 | Giao diện React (Phông/Hồ sơ, tải PDF, hàng đợi, màn soát, xuất file) | |
| 7 | Electron + đóng gói bộ cài Windows | |

## Cấu trúc thư mục

```
sohoa-luutru/
├─ backend/
│  ├─ requirements.txt
│  ├─ app/
│  │  ├─ config.py        đường dẫn, tên model, chế độ offline
│  │  ├─ pdf_render.py    PDF -> ảnh PNG từng trang
│  │  └─ ocr.py           PaddleOCR -> dòng chữ + toạ độ + điểm tin cậy
│  └─ scripts/
│     ├─ download_models.py   tải model OCR (1 lần, cần mạng)
│     ├─ make_sample_pdf.py   tạo PDF scan mẫu (nội dung giả)
│     └─ step1_ocr_pdf.py     chạy thử Bước 1
├─ models/   (tự tạo, không commit)  model OCR + LLM
└─ data/     (tự tạo, không commit)  ảnh, kết quả — có thể chứa tài liệu mật
```

---

## Bước 1 — OCR offline trên PDF scan

### 1.1 Cài Python 3.12

Tải tại python.org → *Windows installer (64-bit)*. Khi cài, **tick "Add python.exe to PATH"**.
Kiểm tra trong PowerShell:

```powershell
py -3.12 --version
```

### 1.2 Tạo môi trường và cài thư viện

```powershell
cd sohoa-luutru\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> Nếu PowerShell báo không cho chạy script, chạy một lần:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 1.3 Tải model OCR (cần mạng, chỉ một lần)

```powershell
python scripts\download_models.py
```

Kết quả mong đợi: 3 dòng `[OK]` (PP-OCRv6_medium_det, PP-OCRv6_medium_rec,
PP-LCNet_x1_0_doc_ori). Model nằm trong `sohoa-luutru\models\`. Từ đây có thể ngắt mạng.

### 1.4 Chạy thử với PDF mẫu

```powershell
python scripts\make_sample_pdf.py
python scripts\step1_ocr_pdf.py ..\data\samples\mau_ho_so.pdf
```

PDF mẫu có 3 trang, **trang 3 bị lật ngược** để kiểm tra chức năng tự xoay.

### 1.5 Chạy với PDF thật của bạn

```powershell
python scripts\step1_ocr_pdf.py "D:\duong\dan\ho_so.pdf"
python scripts\step1_ocr_pdf.py "D:\duong\dan\ho_so.pdf" --pages 1-5
```

Kết quả nằm ở `sohoa-luutru\data\step1\<tên file>\`: ảnh từng trang, `.txt` (văn bản
theo bố cục, 2 cột tiêu đề cách nhau bằng `|`), `.ocr.json` (toạ độ từng dòng), và
`summary.json` (thời gian từng trang).

### ✅ Bước 1 coi là xong khi

1. Lệnh 1.3 in đủ 3 dòng `[OK]`.
2. PDF mẫu: trang 3 báo `đã xoay 180°` và chữ đọc ra đúng dấu tiếng Việt.
3. Với 1 PDF thật (5–10 trang): mở các file `.txt` và đánh giá **số/ký hiệu, ngày tháng,
   trích yếu** đọc ra có đúng không, đặc biệt là dấu tiếng Việt.
4. Ghi lại thời gian trung bình mỗi trang (dòng `Tổng OCR` cuối cùng).

Gửi lại kết quả (2–3 trang `.txt` mẫu, nhớ che thông tin mật, cùng thời gian mỗi trang)
để quyết định có cần thêm VietOCR hay không, rồi sang Bước 2.

### Lỗi hay gặp

| Lỗi | Cách xử lý |
|---|---|
| `Chưa có model OCR` | Chạy lại bước 1.3 khi có mạng |
| Lỗi oneDNN / `mkldnn` khi chạy OCR | Báo lại nội dung lỗi; tạm thời thêm `enable_mkldnn=False` trong `app/ocr.py` |
| Chạy chậm | Thử `--dpi 200` hoặc `--threads 8` |
