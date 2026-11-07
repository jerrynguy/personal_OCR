> **Tài liệu dành cho người phát triển** — ghi lại kiến trúc và quá trình làm từng bước (OCR, AI,
> backend, giao diện), cách chạy từng phần bằng dòng lệnh để thử nghiệm. **Người dùng thường xem
> [README](../README.md).** Các lệnh dưới đây chạy trong thư mục gốc của repo.

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
| **1** | Môi trường Python, tách PDF thành ảnh, OCR tiếng Việt offline (PaddleOCR + VietOCR) | ✅ xong (tinh chỉnh thêm khi có tài liệu thật) |
| **2** | llama.cpp + LLM offline, đo tốc độ, LLM trả JSON theo schema | ✅ xong (gpt-oss-20b: 8/8 trường) |
| **3** | Schema TT05 + luật trích xuất (số/ký hiệu, ngày, tên loại, cơ quan, độ mật, tờ số) + tách PDF thành từng văn bản | ✅ xong (16/16 trường trên ZBook) |
| **4** | Lưu SQLite + xuất Excel / CSV + tách PDF từng tài liệu (chạy bằng dòng lệnh) | ✅ xong |
| **5** | Backend FastAPI (hàng đợi xử lý, tiến độ, sửa tay, xuất file) | ✅ xong (3 trang / 2 văn bản: 94s trên ZBook) |
| **6** | Giao diện: hồ sơ, tải PDF, tiến độ, màn soát, tách văn bản, xuất file, model AI, kiểm tra máy | ✅ xong (chờ chạy thử trên Windows) |
| **6b** | Xử lý hàng loạt: nhập cả thư mục, hàng đợi bền (qua đêm), PDF dài (gợi ý trang đầu, phím tắt), xuất Excel gộp | ✅ xong (thử bằng OCR/AI giả — chờ dữ liệu thật) |
| 7 | Electron + đóng gói bộ cài Windows | |

## Cấu trúc thư mục

```
personal_OCR/
├─ backend/
│  ├─ requirements.txt
│  ├─ app/
│  │  ├─ config.py          đường dẫn, tên model, chế độ offline
│  │  ├─ pdf_render.py      PDF -> ảnh PNG từng trang
│  │  ├─ ocr.py             xoay trang + tìm vùng chữ (PaddleOCR) + đọc chữ (VietOCR)
│  │  ├─ vietocr_rec.py     bọc VietOCR chạy offline
│  │  ├─ metrics.py         tính tỉ lệ lỗi ký tự (CER) so với đáp án
│  │  ├─ llm.py             bật/tắt llama-server, gọi LLM ép JSON schema
│  │  ├─ schema/tt05.json   danh sách trường TT05 (Phông/Hồ sơ/Tài liệu) — sửa không cần code
│  │  ├─ tt05.py            đọc schema
│  │  ├─ rules.py           luật: số, ký hiệu, ngày, tên loại, cơ quan, độ mật/khẩn, tờ số
│  │  ├─ segment.py         tách PDF nhiều trang thành từng văn bản
│  │  ├─ extract.py         luật + LLM -> bản ghi TT05, đối chiếu, tính dữ liệu hồ sơ
│  │  ├─ db.py              lưu Phông / Hồ sơ / Tài liệu vào SQLite (data/sohoa.db)
│  │  ├─ export.py          xuất Excel / CSV, tách PDF thành từng tài liệu
│  │  ├─ services.py        giữ OCR / LLM trong bộ nhớ; LLM tự tắt sau 10 phút không dùng
│  │  ├─ jobs.py            hàng đợi BỀN trong CSDL (mỗi lần 1 hồ sơ), tạm dừng, tiếp tục khi mở lại, ước tính
│  │  ├─ sources.py         nhiều file PDF của 1 hồ sơ = 1 dãy trang liên tục; khóa dùng chung cho PyMuPDF
│  │  ├─ batch.py           nhập thư mục: quét, gợi ý mã hồ sơ, gợi ý file gộp, tạo hàng loạt, hộp chọn thư mục
│  │  ├─ pipeline.py        xử lý trọn 1 hồ sơ; giữ ô sửa tay khi xử lý lại
│  │  ├─ api.py             API cho giao diện (FastAPI), có token
│  │  ├─ hardware.py        nhận diện CPU / RAM / card đồ họa, chọn cách chạy LLM
│  │  └─ winperf.py         chặn Windows hạ tốc độ tiến trình nền
│  │  └─ vietocr_configs/   config VietOCR (bản sao, để không phải tải qua mạng)
│  ├─ tests/              kiểm thử không cần model thật (OCR giả + AI giả) — xem tests/README.md
│  └─ scripts/
│     ├─ download_models.py   tải model (1 lần, cần mạng)
│     ├─ make_sample_pdf.py   tạo PDF scan mẫu (nội dung giả)
│     ├─ step1_ocr_pdf.py     OCR cả file PDF
│     ├─ bench_ocr.py         so sánh các cấu hình OCR trên 1 trang
│     ├─ download_llama_cpp.py  tải llama.cpp (llama-server) bản Windows
│     ├─ download_llm.py        tìm / tải / chọn model GGUF
│     ├─ step2_llm_test.py      kiểm tra LLM: tốc độ + trích xuất thử
│     ├─ step3_extract_pdf.py   PDF -> từng văn bản -> trường TT05
│     ├─ step4_export.py        lưu CSDL + xuất Excel / CSV / PDF từng tài liệu
│     ├─ run_server.py          chạy backend (API)
│     ├─ step5_api_test.py      kiểm tra backend qua API
│     └─ kiem_tra_may.py        phần cứng máy này + cấu hình app sẽ dùng + còn thiếu gì
├─ frontend/  giao diện (Next.js, xuất ra file tĩnh frontend/out/ — backend phục vụ trực tiếp)
│  ├─ app/page.js            danh sách hồ sơ (lọc theo lô / trạng thái, phân trang) + hàng đợi + xuất cả lô
│  ├─ app/nhap/page.js       nhập cả thư mục: bảng xem trước, gợi ý file gộp, tạo hàng loạt
│  ├─ app/ho-so/page.js      chi tiết hồ sơ: tải PDF, tiến độ, soát tài liệu, thông tin hồ sơ, tách văn bản, xuất
│  ├─ app/model-ai/page.js   chọn / tải lên model AI
│  ├─ app/may/page.js        kiểm tra máy
│  └─ components/            form trường TT05, khung xem ảnh trang (tô sáng chữ)
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
cd backend
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
Model nằm trong `models\`. Từ đây có thể ngắt mạng.

### 1.4 So sánh cấu hình trên 1 trang

```powershell
python scripts\make_sample_pdf.py
python scripts\bench_ocr.py ..\data\samples\mau_ho_so.pdf --page 1
```

Chạy 4 cấu hình (seq2seq / transformer, có / không cắt dòng dài), in thời gian và
**tỉ lệ lỗi ký tự (CER)** so với đáp án có sẵn của PDF mẫu, kèm các từ bị đọc sai.

> **Cắt dòng dài:** VietOCR được huấn luyện với ảnh dòng rộng tối đa ~16 lần chiều cao;
> dòng dài cả trang sẽ bị đọc sót chữ. App cắt các dòng rộng hơn 12 lần chiều cao tại
> khoảng trắng giữa các từ (không bao giờ cắt giữa chữ), đọc từng đoạn rồi ghép lại.
Nên chạy thêm với 1 trang của PDF thật: `python scripts\bench_ocr.py "D:\...\ho_so.pdf" --page 1`

### 1.5 OCR cả file PDF

```powershell
python scripts\step1_ocr_pdf.py ..\data\samples\mau_ho_so.pdf
python scripts\step1_ocr_pdf.py "D:\duong\dan\ho_so.pdf" --pages 1-5
```

Tuỳ chọn: `--rec vgg_transformer`, `--no-split` (không cắt dòng dài), `--det-side 1280`,
`--threads 8`, `--no-mkldnn`, `--no-orientation`. Với PDF mẫu, mỗi trang in thêm tỉ lệ lỗi.

Kết quả nằm ở `data\step1\<tên file>\`: ảnh từng trang, `.txt` (văn bản
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

**Cấu hình đã chốt** (bench trên PDF mẫu): `PP-OCRv5_mobile_det` @1920px + VietOCR
`vgg_seq2seq` + cắt dòng dài → CER 0.86%, ~4 giây/trang. Bản `vgg_transformer` (CER 0.34%,
~11 giây/trang) chỉ hơn ở dấu câu cuối dòng nên không dùng mặc định (`--rec vgg_transformer`).

---

## Bước 2 — LLM offline (llama.cpp + Gemma 4)

LLM chạy bằng **llama.cpp** (`llama-server.exe`), chỉ nghe trên `127.0.0.1` với khóa API
ngẫu nhiên mỗi lần chạy. Output bị **ép đúng JSON schema** (llama.cpp chuyển schema thành
grammar) nên model không thể trả sai cấu trúc.

Model mặc định: **Gemma 4 26B-A4B, bản Q4 QAT** (~15–18 GB). Là MoE: mỗi token chỉ chạy
~4B tham số nên chạy được trên CPU; bản QAT ít mất chất lượng khi nén Q4.

> **RAM:** model chiếm ~16–18 GB. Tắt các app nặng khác trước khi chạy — đặc biệt **tắt app
> Magnitude** nếu nó đang giữ model trong RAM, nếu không sẽ thiếu RAM.

### 2.1 Tải llama.cpp (cần mạng, một lần)

```powershell
python scripts\download_llama_cpp.py
```

Kết quả mong đợi: `[OK] ...\models\llama.cpp\cpu\llama-server.exe` và dòng `version: ...`.

### 2.2 Chọn model

**Cách A — dùng file GGUF đã có sẵn** (ví dụ app Magnitude đã tải). Tìm file trên máy:

```powershell
Get-ChildItem -Path C:\Users, D:\ -Recurse -Filter *.gguf -ErrorAction SilentlyContinue | Select-Object FullName, @{n='GB';e={[math]::Round($_.Length/1GB,1)}}
```

Rồi chọn file đó (không sao chép, không tốn thêm ổ cứng):

```powershell
python scripts\download_llm.py --use "C:\duong\dan\gemma-4-26b-a4b-....gguf"
```

**Cách B — tải từ Hugging Face** (cần mạng, ~15–18 GB):

```powershell
python scripts\download_llm.py --search "gemma-4-26B-A4B"
python scripts\download_llm.py --repo <tên repo> --file <tên file .gguf>
```

Ưu tiên file **Q4 có chữ QAT**, sau đó Q4_K_M. Repo có nhãn `[CẦN ĐĂNG NHẬP...]` thì chọn repo khác.

### 2.3 Kiểm tra

```powershell
python scripts\step2_llm_test.py
```

- **Test 1:** trả lời 1 câu ngắn → đo tốc độ sinh chữ (token/s).
- **Test 2:** đưa văn bản OCR của Quyết định mẫu cho LLM trích xuất 8 trường (số/ký hiệu,
  ngày, tên loại, trích yếu, cơ quan ban hành, người ký, chức vụ, độ mật) → tự chấm đúng/sai,
  in tốc độ đọc prompt và sinh chữ.

Thử với văn bản OCR thật: `python scripts\step2_llm_test.py --text-file ..\data\step1\<tên>\page_001.txt`

Thử GPU Iris Xe (không bắt buộc): `python scripts\download_llama_cpp.py --variant vulkan` rồi
`python scripts\step2_llm_test.py --variant vulkan --ngl 99`

### ✅ Bước 2 coi là xong khi

1. Test 2 đúng ít nhất 7/8 trường.
2. Ghi lại: thời gian nạp model, token/s đọc prompt, token/s sinh chữ, tổng thời gian Test 2.

Nếu lỗi, log đầy đủ của llama-server nằm ở `data\logs\llama-server.log`.

**Kết quả trên ZBook** (llama.cpp b12034, bản CPU, `gpt-oss-20b-MXFP4` 12.1 GB):
nạp model 14–30s; Test 2 đúng **8/8 trường** trong 45.9s — đọc prompt 631 token @ 22.1 token/s
(~28s, phần chậm nhất), sinh 150 token @ 8.6 token/s (~17s). Gemma 4 26B-A4B sẽ so sánh sau
với cùng bài test.

---

## Bước 3 — Trường dữ liệu TT05, tách văn bản, luật + LLM

**Cấu trúc dữ liệu** theo Điều 4 TT 05/2025/TT-BNV, nằm trong `backend/app/schema/tt05.json`
(sửa nhãn, thứ tự, giá trị mặc định ở đây — không cần sửa code):

| Nhóm | Số trường | Ghi chú |
|---|---|---|
| Phông (điểm a) | 10 | nhập tay |
| Hồ sơ (điểm b) | 19 | nhập tay + tự tính (thời gian bắt đầu/kết thúc, tổng số tài liệu, số tờ/trang, từ khóa) |
| Tài liệu (điểm c) | 23 | luật + LLM + kế thừa từ hồ sơ; "quy trình xử lý" chỉ cho tài liệu gốc điện tử nên để trống |
| Bổ sung | 8 | trang trong PDF, độ mật, độ khẩn, người ký, chức vụ, tờ số, điểm OCR, **cần kiểm tra** |

**Cách lấy từng trường của tài liệu:**

- **Luật** (theo thể thức NĐ 30, chịu được lỗi dấu của OCR): tên loại, số, ký hiệu, ngày ban hành,
  độ mật, độ khẩn, tờ số. Giữ NGUYÊN số/ký hiệu gốc.
- **LLM**: cơ quan ban hành (chuẩn hóa viết hoa), trích yếu, từ khóa, người ký, chức vụ. Chỉ khi
  luật KHÔNG đọc được tên loại / số ký hiệu / ngày thì mới hỏi thêm LLM, và đánh dấu "Cần kiểm tra".
  LLM chỉ nhận đoạn trích cần thiết (cơ quan, đầu văn bản, khối chữ ký) và trả JSON tên trường ngắn
  — để nhanh (mỗi token LLM ~0,1 giây trên CPU).
- **Kế thừa từ hồ sơ**: thời hạn lưu trữ, mức độ tiếp cận, mức độ tin cậy, tình trạng vật lý,
  ký hiệu thông tin, chế độ/tình trạng dự phòng.
- **Tự tính**: mã lưu trữ tài liệu (= mã hồ sơ + số thứ tự), số trang, số tờ, tệp tin.

**Tách văn bản:** trang có quốc hiệu hoặc dòng "Số: ..." ở đầu trang = trang đầu văn bản mới;
các trang khác nối vào văn bản phía trước.

### 3.1 Chạy

```powershell
python scripts\make_sample_pdf.py
python scripts\step3_extract_pdf.py ..\data\samples\mau_ho_so.pdf
```

PDF mẫu có 2 văn bản (Quyết định 2 trang + Công văn 1 trang) kèm đáp án → script tự chấm điểm.
Thông tin nhập tay của phông/hồ sơ lấy từ `mau_ho_so.ho_so.json` (nằm cạnh PDF) — làm file
tương tự cho PDF thật, hoặc truyền `--ho-so duong_dan.json`.

Tuỳ chọn: `--no-llm` (chỉ chạy luật), `--pages 1-10`, `--ocr-lai` (mặc định dùng lại kết quả OCR đã lưu).
Kết quả đầy đủ: `data\step3\<tên file>\ket_qua.json`.

### ✅ Bước 3 coi là xong khi

1. PDF mẫu: tách đúng 2 văn bản, chấm điểm 16/16 (hoặc chỉ lệch nhẹ ở trích yếu/cơ quan).
2. Ghi lại thời gian mỗi văn bản.

**Kết quả trên ZBook** (OCR thật + gpt-oss-20b): **16/16 trường**, tách đúng 2 văn bản. OCR ~6s/trang,
LLM ~30–60s/văn bản. LLM đọc nhầm tên loại văn bản 2 thành "Quyết định" (vì nội dung có nhắc
Quyết định 125) — luật đọc đúng "Công văn", giá trị luật được giữ và ghi vào "Cần kiểm tra".

---

## Bước 4 — Lưu CSDL, xuất Excel / CSV, tách PDF từng tài liệu

```powershell
python scripts\step4_export.py ..\data\samples\mau_ho_so.pdf
python scripts\step4_export.py --danh-sach
```

Dùng kết quả `ket_qua.json` của Bước 3 (không chạy lại OCR/LLM), rồi:

1. **Lưu vào SQLite** `data\sohoa.db` (bảng phong / ho_so / tai_lieu). Lưu lại cùng mã hồ sơ sẽ ghi đè.
2. **Xuất** vào `data\xuat\<mã hồ sơ>\`:
   - `<mã hồ sơ>.xlsx` — **chỉ dữ liệu tài liệu**: 23 cột theo **điểm c khoản 1 Điều 4 TT 05/2025/TT-BNV**,
     đúng thứ tự và tên trong Thông tư, mỗi văn bản một dòng (xem bảng "File xuất ra có gì?" ở cuối)
   - `<mã hồ sơ>.csv` — cùng nội dung (UTF-8 có BOM, Excel mở đúng tiếng Việt)
   - `tai_lieu\<mã lưu trữ>.pdf` — PDF hồ sơ tách thành từng tài liệu (cột "Tệp tin tài liệu")

Cần cài thêm thư viện Excel: `pip install -r requirements.txt` (thêm `openpyxl`).

### ✅ Bước 4 coi là xong khi

1. Mở được file `.xlsx` bằng Excel, tiếng Việt hiển thị đúng, đủ 23 cột điểm c.
2. Thư mục `tai_lieu\` có 2 file PDF (2 trang và 1 trang).

---

## Bước 5 — Backend (API)

Backend FastAPI là lớp nằm giữa giao diện (Bước 6) và toàn bộ phần xử lý ở các bước trước.

- **Chỉ nghe 127.0.0.1.** Mọi request phải kèm token ngẫu nhiên (header `X-Token`), trừ chế độ `--dev`.
- **Hàng đợi xử lý:** mỗi lần chỉ chạy 1 hồ sơ (OCR và LLM đều dùng hết CPU), các hồ sơ khác chờ.
  Có tiến độ theo giai đoạn (tách trang → OCR → tách văn bản → nạp AI → trích xuất → lưu),
  ước tính thời gian còn lại, và nút hủy.
- **Giữ model trong bộ nhớ:** OCR nạp 1 lần; LLM tự tắt sau 10 phút không dùng để trả RAM.
- **Dùng lại OCR:** xử lý lại một hồ sơ không OCR lại (trừ khi chọn `ocr_lai`).
- **Không mất công soát:** khi xử lý lại, văn bản nào vẫn đúng các trang như cũ thì giữ các ô
  đã sửa tay và cờ "đã soát".
- **Sửa thông tin hồ sơ** (thời hạn lưu trữ, mã hồ sơ...) thì tự cập nhật xuống các tài liệu,
  trừ ô đã sửa tay; các trường tự tính của hồ sơ được tính lại.
- CSDL cũ (tạo ở Bước 4) được tự nâng cấp, không mất dữ liệu.

**Tốc độ** (lần chạy đầu trên ZBook mất 9 phút cho 3 trang — máy vừa sập nguồn vì hết pin nên
bị hạ xung, mọi giai đoạn chậm 3–5 lần so với Bước 3). Đã sửa:

- **Nạp sẵn OCR + LLM ngay khi mở backend** (luồng nền) → bấm xử lý không phải chờ nạp model.
  LLM giữ trong RAM 30 phút sau lần dùng cuối.
- **Không cho Windows hạ tốc độ tiến trình nền** (power throttling / EcoQoS) cho backend và llama-server;
  backend cảnh báo khi máy chạy bằng pin hoặc đang bật Battery saver.
- OCR dùng `vgg_seq2seq` (nhanh gấp ~2,5 lần).
- LLM đọc ít hơn (đoạn trích thay vì cả trang) và viết ít hơn (5 trường, tên ngắn, không đọc lại
  số/ký hiệu/ngày khi luật đã có); đọc prompt bằng mọi luồng CPU (`-tb`).
- Script kiểm tra in thời gian thực tế của từng giai đoạn.

Kết quả sau khi sửa (ZBook, cắm sạc, gpt-oss-20b, PDF mẫu 3 trang / 2 văn bản): **94 giây**
(trước: 543 giây) — tách trang 0,8s, OCR 7,9s, AI văn bản 1 ~52s (lần đầu phải đọc cả phần
hướng dẫn), văn bản 2 ~33s; đúng cả 2 văn bản, không ô nào cần kiểm tra.

Dữ liệu mỗi hồ sơ: `data\ho_so\<id>\` (PDF gốc, ảnh + OCR từng trang, file xuất).

### 5.1 Cài thêm thư viện

```powershell
pip install -r requirements.txt
```

### 5.2 Chạy thử (2 cửa sổ PowerShell, cùng ở thư mục `backend` và đã bật `.venv`)

Cửa sổ 1 — chạy backend:

```powershell
python scripts\run_server.py --dev
```

Cửa sổ 2 — gọi API giống hệt giao diện sẽ gọi (tạo hồ sơ, tải PDF, xử lý, theo dõi tiến độ,
sửa tay, tải Excel):

```powershell
python scripts\step5_api_test.py
```

Xem danh sách API: mở `http://127.0.0.1:8765/docs` trong trình duyệt (chỉ có ở chế độ `--dev`).

### ✅ Bước 5 coi là xong khi

1. Script in đủ 6 bước, tách đúng 2 tài liệu, tải được file Excel về `data\step5\`.
2. Tắt backend (Ctrl+C ở cửa sổ 1) thì llama-server cũng tắt theo (Task Manager không còn `llama-server.exe`).

---

## Chạy trên máy khác (laptop, workstation...)

App **không ghép cứng cấu hình theo một máy**. Khi chạy, nó dò phần cứng và tự chọn:

| Máy | LLM chạy bằng | Model |
|---|---|---|
| Có card NVIDIA, VRAM đủ (vd. RTX 4090 24 GB) | llama.cpp **CUDA**, toàn bộ trên GPU | lớn |
| Card NVIDIA VRAM ít (vd. RTX 3060 12 GB) | CUDA, phần "chuyên gia" của model MoE ở RAM (`--cpu-moe`) | lớn |
| Card rời AMD / Intel Arc | llama.cpp **Vulkan** trên GPU | theo RAM |
| Chỉ GPU tích hợp (Iris Xe, UHD...) | **CPU** (AVX2 / AVX-512) | RAM ≥ 24 GB: lớn, ≥ 12 GB: nhỏ |
| RAM < 12 GB | CPU — cảnh báo: không đủ RAM cho LLM | nhỏ |

Bản phù hợp chưa được cài thì tự lùi về bản CPU (vẫn chạy, chỉ chậm hơn). Có thể ghi đè trong
`models\llm\active.json` bằng các khóa `variant`, `gpu_layers`, `extra_args`.

```powershell
python scripts\kiem_tra_may.py                 # xem app nhận diện máy thế nào, còn thiếu gì
python scripts\download_llama_cpp.py --auto    # tải đúng bản llama.cpp cho máy này (+ bản CPU dự phòng)
```

Bản cài đặt `.exe` (Bước 7) sẽ đóng gói sẵn cả 3 bản llama.cpp (CPU, CUDA, Vulkan), model OCR
và model LLM, để cài được trên máy **không có mạng** và tự chạy đúng bản cho từng máy.

---

## Bước 6 — Giao diện

| Màn hình | Làm được gì |
|---|---|
| **Hồ sơ** | **Kéo thả PDF** ngay trên trang đầu → hộp thoại chỉ hỏi **Mã hồ sơ** (lấy sẵn từ tên file) + Tiêu đề (không bắt buộc); thông tin khác thu gọn, nhớ theo lần trước → **Tạo và tải lên** → sang màn **Tách văn bản**. Danh sách hồ sơ (trạng thái, số tài liệu, cần kiểm tra, đã soát) |
| **Chi tiết hồ sơ** | Kéo thả PDF → tự xử lý; thanh tiến độ theo giai đoạn + thời gian còn lại + Hủy; xuất Excel / CSV / PDF từng tài liệu; xóa |
| ↳ Soát tài liệu | Danh sách văn bản · ảnh trang (bấm vào ô nào thì **chữ tương ứng trên ảnh sáng vàng**, dòng OCR kém tin cậy viền đỏ) · trước hết chỉ hiện **các trường đọc từ văn bản** (tên loại, số, ký hiệu, ngày, cơ quan, trích yếu, từ khóa, người ký...); các trường quản lý tự điền gom trong mục thu gọn; nhãn nguồn từng ô; nút **"Đã soát, sang văn bản tiếp"** |
| ↳ Thông tin hồ sơ | 4 trường chính (mã, tiêu đề, thời hạn, mức độ tiếp cận) + bảng "App tự tính"; trường khác thu gọn. Sửa → tự cập nhật xuống tài liệu (trừ ô đã sửa tay) |
| ↳ Tách văn bản | **Người dùng tự tách** (app không tự đoán ranh giới): ảnh thu nhỏ các trang, bấm vào **trang đầu của từng tài liệu**; nút nhanh "Cả file là 1 tài liệu" (mặc định) / "Mỗi trang 1 tài liệu" → **Xử lý**. Xử lý lại giữ cách tách cũ và công soát |
| **Model AI** | Xem model đang dùng; **dùng file .gguf có sẵn** (dán đường dẫn, không sao chép) hoặc **tải file lên**; nạp thử ngay, lỗi thì tự quay về model cũ; **Về mặc định** (`gpt-oss-20b-MXFP4.gguf`); xóa model đã tải lên |
| **Kiểm tra máy** | Phần cứng, cách app chạy AI trên máy này, model đã có, cảnh báo chạy bằng pin |

**Kết quả hiện dần:** ngay sau OCR (vài giây/trang), kết quả của luật (tên loại, số, ký hiệu, ngày...)
đã hiện để soát; AI điền cơ quan, trích yếu, từ khóa, người ký cho từng văn bản ở nền.

### 6.1 Cài Node.js (một lần)

Tải bản **LTS** tại nodejs.org (nếu máy chưa có — kiểm tra bằng `node -v`).

### 6.2 Build giao diện (mỗi khi giao diện thay đổi)

```powershell
cd frontend
npm install
npm run build
```

Kết quả ở `frontend\out\` — backend tự tìm thấy thư mục này.

### 6.3 Chạy

```powershell
cd ..\backend
python scripts\run_server.py
```

Trình duyệt tự mở giao diện (địa chỉ có kèm token, in ra ở cửa sổ PowerShell). Giữ cửa sổ
PowerShell mở trong lúc dùng; tắt bằng Ctrl+C. (Bước 7 sẽ thay cửa sổ này bằng app desktop có icon.)

### ✅ Bước 6 coi là xong khi

Đi trọn một vòng trên giao diện: tạo hồ sơ → kéo thả PDF → xem kết quả hiện dần → soát, sửa,
đánh dấu đã soát → xuất Excel; đổi model AI rồi về mặc định.

---

## Bước 6b — Xử lý hàng loạt

Người dùng có dữ liệu thật dạng: thư mục lớn (vd. `Đà Lạt 1L`) -> ~1000 thư mục con -> mỗi thư mục con là 1 hồ sơ,
mỗi file PDF là 1 tài liệu (tên file không theo quy tắc cố định); có thư mục chứa thêm 1 file là bản gộp của các file kia.
Và có PDF 1 hồ sơ chứa hàng trăm tài liệu.

### Quyết định người dùng chọn (2026-11-07)

| Câu hỏi | Người dùng chọn |
|---|---|
| Mã hồ sơ điền sẵn | Phần giống nhau ở đầu tên các file (cắt tại `.` `_` `-` khoảng trắng); thư mục 1 file / không có phần chung / bị trùng giữa các thư mục -> *tên thư mục cha + thư mục con*. Sửa được ở bảng xem trước |
| File gộp | App **gợi ý** (so nội dung trang), vẫn để tích; có nút bỏ tích hết file được gợi ý |
| Cột 22 "Tệp tin tài liệu" | **Tên file gốc** khi tài liệu trùng đúng 1 file (nhập thư mục); còn lại: mã lưu trữ + `.pdf` |
| Xuất nhiều hồ sơ | **Cả hai**: 1 file Excel gộp, và `.zip` mỗi hồ sơ 1 file Excel (đều đúng 23 cột) |

### Thiết kế

- **Không sao chép file gốc** (hàng nghìn file sẽ tốn gấp đôi ổ cứng): `ho_so.ds_pdf` = danh sách file
  `{duong_dan, ten, so_trang}`; trang của hồ sơ đánh số liên tục qua các file (`sources.PdfSet`). Hồ sơ tải lên vẫn
  dùng `goc.pdf` như cũ. File gốc bị di chuyển -> lỗi rõ ràng (`SourceMissing`), giao diện báo file thiếu.
- **Không giữ ảnh 300 DPI**: mỗi trang render 300 DPI -> OCR -> lưu `page_NNN.jpg` (~150 DPI, ~100–200 KB, đã xoay
  thẳng, toạ độ OCR vẫn theo ảnh gốc — giao diện tự co theo `width/height` trong OCR) -> xóa PNG. Trước đây giữ
  PNG 300 DPI: 30.000 trang ≈ hàng trăm GB. Hồ sơ cũ có `page_NNN.png` vẫn xem được.
- **Hàng đợi bền** (`jobs.py`): hồ sơ chờ = `trang_thai='cho'` + tham số trong `cho_xu_ly`; thứ tự `uu_tien DESC,
  cho_luc` (việc người dùng bấm trên 1 hồ sơ = 1, hàng loạt = 0). Mở app: hồ sơ `dang_xu_ly` dở -> xếp lại đầu hàng
  với `tiep_tuc` (văn bản AI đã đọc xong thì giữ, không đọc lại). Tạm dừng = dừng NGAY hồ sơ đang chạy và xếp lại
  đúng chỗ cũ; trạng thái tạm dừng lưu trong bảng `cai_dat`. Lỗi / hủy luôn đưa hồ sơ ra khỏi hàng (không kẹt).
  Còn việc -> `SetThreadExecutionState` giữ Windows không ngủ. Ước tính thời gian theo tốc độ đo được (lưu lại).
- **Ranh giới**: nhập thư mục -> mỗi file 1 tài liệu (`ranh_gioi` = trang đầu từng file). Chưa xử lý lần nào ->
  mặc định cũng là trang đầu từng file (`pipeline.default_starts`). Vẫn không tự tách theo nội dung.
- **Gợi ý file gộp** (`batch.merged_suggestions`, chỉ thư mục >= 3 file): (1) dấu vân tay = md5 luồng ảnh scan lớn
  nhất của trang (không giải nén -> rất nhanh); file M được gợi ý khi mọi trang của M trùng trang của >= 2 file khác.
  (2) Không trùng byte (file gộp đã lưu lại) -> chỉ khi số trang M = tổng các file kia: so ảnh 48x68 xám từng trang
  theo đúng thứ tự ghép.
- **Gợi ý trang đầu** (màn Tách văn bản): `segment.is_first_page` (quốc hiệu / dòng "Số:") trên kết quả OCR, hoặc lớp
  chữ có sẵn của PDF. Cần OCR trước -> job `kind='ocr'` (POST `/doc-chu`), kết quả OCR dùng lại khi xử lý.
- **PyMuPDF không an toàn đa luồng** -> mọi thao tác PDF qua `sources.pdf_lock` (luồng xử lý, luồng quét, request ảnh).
- **Xuất Excel lớn**: openpyxl `write_only` (~8 giây / 30.000 dòng).

### Đo trên máy cloud (OCR / AI giả, chỉ để xem phần khung có chịu tải không)

1000 thư mục / 3.333 file / 333 file gộp: quét 5 giây (tìm đủ 333 file gộp), tạo 1000 hồ sơ 1 giây; danh sách,
hàng đợi 3–5 ms; xóa cả lô 2 giây. Thời gian thật do OCR (~3–5 giây/trang) và AI (~30–60 giây/tài liệu) quyết định:
vd. 7.000 trang ≈ 6–10 giờ chỉ riêng OCR -> chạy qua nhiều đêm, hoặc "bỏ qua AI" trước rồi chạy AI sau.

---

## File xuất ra có gì? (23 cột — điểm c khoản 1 Điều 4 TT 05/2025/TT-BNV)

Mỗi văn bản trong PDF là **một dòng**. Chỉ xuất dữ liệu **tài liệu** (điểm c); thông tin phông / hồ sơ
chỉ dùng trong app để nhập một lần các giá trị chung.

| # | Cột | Lấy từ đâu |
|---|---|---|
| 1 | Mã định danh tài liệu | nhập tay (văn bản giấy thường không có) |
| 2 | Mã lưu trữ tài liệu | tự tính: mã hồ sơ + số thứ tự (vd. H01.2025.01.15.01) |
| 3 | Thời hạn lưu trữ | nhập 1 lần cho cả hồ sơ |
| 4 | Tên loại tài liệu | **OCR + luật** (AI đọc thay nếu luật không thấy) |
| 5 | Số của tài liệu | **OCR + luật** |
| 6 | Ký hiệu của tài liệu | **OCR + luật** |
| 7 | Ngày tháng năm ban hành tài liệu | **OCR + luật** |
| 8 | Tên cơ quan, tổ chức, cá nhân ban hành tài liệu | **OCR + AI** (chuẩn hóa viết hoa) |
| 9 | Trích yếu nội dung | **OCR + AI** |
| 10 | Ngôn ngữ | **OCR + luật** |
| 11 | Số lượng trang | tự đếm từ PDF |
| 12 | Số lượng tờ (đối với tài liệu số hóa) | tự đếm (= số trang nếu scan 1 mặt) |
| 13 | Ký hiệu thông tin | nhập 1 lần cho cả hồ sơ |
| 14 | Từ khóa | **OCR + AI** |
| 15 | Mức độ tiếp cận | nhập 1 lần cho cả hồ sơ |
| 16 | Mức độ tin cậy | nhập 1 lần cho cả hồ sơ (mặc định "Số hóa") |
| 17 | Bút tích (đối với tài liệu số hóa) | nhập tay khi soát |
| 18 | Tình trạng vật lý (đối với tài liệu số hóa) | nhập 1 lần cho cả hồ sơ (mặc định "Bình thường") |
| 19 | Quy trình xử lý (đối với tài liệu gốc điện tử) | để trống — không áp dụng cho tài liệu số hóa |
| 20 | Chế độ lập tài liệu lưu trữ dự phòng | nhập 1 lần cho cả hồ sơ |
| 21 | Tình trạng lập tài liệu lưu trữ dự phòng | nhập 1 lần cho cả hồ sơ |
| 22 | Tệp tin tài liệu | tự tính: tên file PDF tách riêng của văn bản (nhập thư mục: tên file gốc) |
| 23 | Ghi chú | nhập tay khi soát |

**OCR + AI đọc được từ ảnh scan: 8 cột** (4–10, 14). 4 cột tự tính/tự đếm. 7 cột không có trên
văn bản nên nhập một lần cho cả hồ sơ. 4 cột nhập tay hoặc để trống.
