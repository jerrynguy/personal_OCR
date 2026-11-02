# Số hóa Lưu trữ (offline)

App desktop đọc **PDF scan hồ sơ lưu trữ**, OCR bằng **PaddleOCR** (tìm vùng chữ) +
**VietOCR** (đọc chữ tiếng Việt), trích xuất trường
dữ liệu theo **Thông tư 05/2025/TT-BNV** (Phông → Hồ sơ → Tài liệu) bằng **LLM chạy
trong máy** (llama.cpp + Gemma 4), rồi xuất **.xlsx / .csv**.
Toàn bộ chạy offline: không gửi ảnh hay dữ liệu ra internet.

Máy mục tiêu: HP ZBook Firefly G8 (i7-1185G7, 32GB RAM, Intel Iris Xe, Windows).

## Lộ trình — làm xong bước nào mới sang bước tiếp theo

| Bước | Nội dung | Trạng thái |
|---|---|---|
| **1** | Môi trường Python, tách PDF thành ảnh, OCR tiếng Việt offline (PaddleOCR + VietOCR) | ⏳ đang làm |
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
│  │  ├─ config.py          đường dẫn, tên model, chế độ offline
│  │  ├─ pdf_render.py      PDF -> ảnh PNG từng trang
│  │  ├─ ocr.py             xoay trang + tìm vùng chữ (PaddleOCR) + đọc chữ (VietOCR)
│  │  ├─ vietocr_rec.py     bọc VietOCR chạy offline
│  │  └─ vietocr_configs/   config VietOCR (bản sao, để không phải tải qua mạng)
│  └─ scripts/
│     ├─ download_models.py   tải model (1 lần, cần mạng)
│     ├─ make_sample_pdf.py   tạo PDF scan mẫu (nội dung giả)
│     ├─ step1_ocr_pdf.py     OCR cả file PDF
│     └─ bench_ocr.py         so sánh các cấu hình OCR trên 1 trang
├─ models/   (tự tạo, không commit)  model OCR + LLM
└─ data/     (tự tạo, không commit)  ảnh, kết quả — có thể chứa tài liệu mật
```

---

## Bước 1 — OCR offline trên PDF scan

**Vì sao PaddleOCR + VietOCR?** Model đọc chữ của PaddleOCR (PP-OCRv6) thiếu các chữ Việt
có dấu nặng/hỏi/mũ+dấu (ộ, ậ, ự, ủ, ữ...) nên đọc "Cộng hòa" thành "Cng hòa". PaddleOCR
vẫn rất tốt ở việc tìm vùng chữ và xoay trang, nên giữ phần đó; phần đọc chữ giao cho
VietOCR — model được huấn luyện riêng cho tiếng Việt.

### 1.1 Cài Python 3.12

Tải tại python.org → *Windows installer (64-bit)*. Khi cài, **tick "Add python.exe to PATH"**.

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
pip install --no-deps vietocr==0.3.13
```

> VietOCR phải cài với `--no-deps`: nó ghim các bản pillow/numpy rất cũ, cài kèm sẽ làm
> hỏng môi trường. Các thư viện nó thực sự cần đã có trong `requirements.txt`.
>
> Nếu PowerShell không cho chạy script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 1.3 Tải model (cần mạng, chỉ một lần)

```powershell
python scripts\download_models.py
```

Kết quả mong đợi: 5 dòng `[OK]` — PP-LCNet_x1_0_doc_ori, PP-OCRv5_mobile_det,
PP-OCRv6_medium_det, VietOCR vgg_seq2seq, VietOCR vgg_transformer.
Model nằm trong `sohoa-luutru\models\`. Từ đây có thể ngắt mạng.

### 1.4 So sánh cấu hình trên 1 trang

```powershell
python scripts\make_sample_pdf.py
python scripts\bench_ocr.py ..\data\samples\mau_ho_so.pdf --page 1
```

Chạy 4 cấu hình, in thời gian + văn bản của từng cấu hình và bảng tóm tắt cuối cùng.
Nên chạy thêm với 1 trang của PDF thật: `python scripts\bench_ocr.py "D:\...\ho_so.pdf" --page 1`

### 1.5 OCR cả file PDF

```powershell
python scripts\step1_ocr_pdf.py ..\data\samples\mau_ho_so.pdf
python scripts\step1_ocr_pdf.py "D:\duong\dan\ho_so.pdf" --pages 1-5
```

Tuỳ chọn: `--det PP-OCRv6_medium_det`, `--det-side 1280`, `--rec vgg_transformer`,
`--threads 8`, `--no-mkldnn`, `--no-orientation`.

Kết quả nằm ở `sohoa-luutru\data\step1\<tên file>\`: ảnh từng trang, `.txt` (văn bản
theo bố cục, 2 cột tiêu đề cách nhau bằng `|`), `.ocr.json` (toạ độ từng dòng), và
`summary.json` (thời gian từng trang).

### ✅ Bước 1 coi là xong khi

1. Lệnh 1.3 in đủ 5 dòng `[OK]`.
2. PDF mẫu: chữ có dấu đọc đúng (ộ, ậ, ự, ủ...), trang 3 báo `đã xoay 180°`.
3. Thời gian mỗi trang chấp nhận được (mục tiêu: dưới ~15 giây/trang).
4. Với 1 PDF thật: số/ký hiệu, ngày tháng, trích yếu đọc ra đúng.

### Lỗi hay gặp

| Lỗi | Cách xử lý |
|---|---|
| `Chưa có model` / `Chưa có trọng số VietOCR` | Chạy lại bước 1.3 khi có mạng |
| `No module named 'vietocr'` | Chạy `pip install --no-deps vietocr==0.3.13` |
| Lỗi oneDNN / `mkldnn` | Thêm `--no-mkldnn` |
| Chạy chậm | Thử `--det-side 1280` hoặc `--threads 8` |
