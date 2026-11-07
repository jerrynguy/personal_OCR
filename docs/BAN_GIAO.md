# Bàn giao — đọc file này trước khi làm tiếp

Tài liệu để một phiên làm việc mới (người hoặc AI) nắm ngay bối cảnh. Cập nhật: 2026-11-07 (sau khi làm xử lý hàng loạt).

## 1. App là gì

**Số hóa Lưu trữ** — app desktop chạy **offline hoàn toàn** trên Windows (tài liệu có thể là tài liệu mật,
không được gửi ra ngoài). Đầu vào: **PDF scan** hồ sơ lưu trữ. Đầu ra: **Excel/CSV đúng 23 cột của điểm c
khoản 1 Điều 4 Thông tư 05/2025/TT-BNV** (dữ liệu tài liệu lưu trữ), mỗi tài liệu một dòng.

- Người dùng: chuyên viên lưu trữ, **không rành công nghệ** → mọi thứ phải bấm được, không gõ lệnh.
- Giao tiếp với người dùng bằng **tiếng Việt**, ngắn gọn, đi từng bước, chờ họ xác nhận rồi mới sang bước sau.
- Máy chính: HP ZBook Firefly G8 (i7-1185G7, 32 GB RAM, Iris Xe, không card rời). App phải chạy được cả trên
  máy khác (có card NVIDIA, máy 16 GB…) → đã có tự nhận diện phần cứng.

## 2. Kiến trúc (xem chi tiết ở `docs/PHAT_TRIEN.md`)

```
backend/   Python (FastAPI, chỉ nghe 127.0.0.1, có token)
  app/ocr.py          PaddleOCR (xoay trang + tìm vùng chữ) + VietOCR vgg_seq2seq (đọc chữ tiếng Việt)
  app/rules.py        luật đọc: tên loại, số, ký hiệu, ngày, cơ quan (thô), độ mật/khẩn
  app/extract.py      luật + LLM -> bản ghi TT05; LLM chỉ điền cơ quan, trích yếu, từ khóa, người ký, chức vụ
  app/llm.py          llama.cpp (llama-server), ép JSON schema; tự chọn bản cpu/cuda/vulkan theo phần cứng
  app/pipeline.py     xử lý 1 hồ sơ: OCR từng trang -> chia tài liệu theo ranh giới -> luật -> AI (hiện dần)
  app/jobs.py         hàng đợi BỀN trong CSDL: mỗi lần 1 hồ sơ, tạm dừng, tự làm tiếp khi mở lại app
  app/sources.py      nhiều file PDF gốc của 1 hồ sơ = 1 dãy trang (nhập thư mục: không sao chép file)
  app/batch.py        nhập thư mục: quét, gợi ý mã hồ sơ / file gộp, tạo hàng loạt, hộp chọn thư mục Windows
  app/api.py          API cho giao diện; app/db.py SQLite; app/export.py Excel/CSV 23 cột + tách PDF
  app/schema/tt05.json  danh sách trường (phông 10, hồ sơ 19, tài liệu 23 — nhãn nguyên văn TT05)
frontend/  Next.js xuất file tĩnh (frontend/out), backend phục vụ trực tiếp; trang Nhập thư mục ở app/nhap/
backend/tests/  kiểm thử KHÔNG cần model thật: OCR giả + AI giả + dữ liệu giả + Playwright (xem tests/README.md)
cai-dat.bat (+ tools/cai-dat.ps1), mo-app.bat   bấm đúp để cài / mở app (CHƯA chạy thử trên Windows)
models/, data/   (không commit) model OCR + LLM, CSDL + file hồ sơ
```

- Model AI mặc định: `gpt-oss-20b-MXFP4.gguf` (đổi được ở trang Model AI). Trên ZBook: ~30–60 giây/tài liệu
  cho phần AI, OCR ~3–5 giây/trang. PDF mẫu 3 trang / 2 tài liệu: ~94 giây.
- Kiểm thử trong môi trường cloud: không tải được model thật (HuggingFace/Paddle bị chặn) → dùng `backend/tests/`
  (server_gia.py = backend thật + OCR giả + AI giả; các test API + giao diện). Chạy lại sau mỗi thay đổi lớn.

## 3. Quyết định người dùng đã chốt (KHÔNG làm ngược lại)

1. **Chỉ xuất dữ liệu tài liệu (điểm c, 23 cột)**, đúng thứ tự + tên cột nguyên văn Thông tư. Không xuất sheet
   phông/hồ sơ/mục lục, không thêm cột phụ vào file xuất.
2. **App KHÔNG tự đoán ranh giới tài liệu theo nội dung.** Sau khi tải PDF lên, **người dùng tự tách** (màn
   "Tách văn bản": bấm trang đầu từng tài liệu; mặc định cả file = 1 tài liệu). Lý do: tự tách theo quốc hiệu/
   dòng "Số:" chia sai với file gộp nhiều thứ (vd. nghị định kèm phụ lục).
3. **Không dựa vào quy tắc đặt tên file** để suy luận (vd. nhận "file gộp"): cách đặt tên của dữ liệu thật
   KHÔNG cố định (người dùng không nhớ chính xác tiền tố/số chữ số 0). Đã thử làm nhận diện file gộp theo tên
   + so nội dung — người dùng thấy phiền, đã bỏ. Nếu cần nhận diện gì, phải **để người dùng quyết định**
   (gợi ý thì được, tự quyết thì không).
4. Code ở **nhánh `main`** của `jerrynguy/personal_OCR`, project nằm ở **gốc repo** (app cũ đã xóa).
5. Ô tạo hồ sơ chỉ hỏi **mã hồ sơ** (+ tiêu đề không bắt buộc); thông tin chung (thời hạn, mức độ tiếp cận,
   phông…) thu gọn, nhớ theo lần trước. Màn soát chỉ hiện trước các trường đọc từ văn bản.
6. Mã lưu trữ tài liệu = mã hồ sơ + số thứ tự 2 chữ số (vd. `H01.2025.01.15.01`) — người dùng đồng ý.
   Số/ký hiệu: "Số: 12/2025/NĐ-CP" -> số `12`, ký hiệu `2025/NĐ-CP`.
7. Xử lý hàng loạt (người dùng chọn 2026-11-07):
   - Nhập thư mục: mỗi thư mục có PDF = 1 hồ sơ, mỗi file PDF = 1 tài liệu (ranh giới theo file).
   - Mã hồ sơ điền sẵn = **phần chung đầu tên các file**; không có / 1 file / trùng giữa thư mục -> *thư mục cha +
     thư mục con*. Người dùng sửa được ở bảng xem trước.
   - File gộp: app **gợi ý** (so nội dung), vẫn để tích, có nút bỏ tích hết — **không tự bỏ**.
   - Cột "Tệp tin tài liệu" của tài liệu nhập từ thư mục = **tên file gốc**.
   - Xuất nhiều hồ sơ: **cả hai** — 1 file Excel gộp và .zip mỗi hồ sơ 1 file (đều đúng 23 cột).
   - PDF dài: app chỉ **gợi ý** trang đầu (quốc hiệu / "Số:") để người dùng xác nhận, **không tự tách**.

## 4. Xử lý hàng loạt — ĐÃ LÀM (2026-11-07), chờ thử với dữ liệu thật

Yêu cầu: *"Làm cả 1 thư mục hàng trăm file đã số hóa được không? Hoặc 1 file PDF của 1 hồ sơ có hàng chục, hàng
trăm file tài liệu bên trong được không?"* Chi tiết thiết kế: `docs/PHAT_TRIEN.md` mục Bước 6b. Hướng dẫn người dùng:
README mục 5, 6.

Đã có:
- **Nhập thư mục** (trang *Nhập thư mục*): nút mở hộp chọn thư mục của Windows (tkinter, chạy tiến trình riêng) hoặc
  dán đường dẫn -> quét nền có tiến độ -> bảng xem trước (sửa mã, tiêu đề; tích / bỏ từng thư mục, từng file; gợi ý
  file gộp; thư mục đã nhập trước được bỏ tích sẵn; mã trùng báo đỏ) -> thông tin chung cho cả lô (nhớ lần trước),
  tên lô, tùy chọn "bỏ qua AI" -> tạo hàng loạt + xếp hàng.
- **Hàng đợi bền**: chạy qua đêm, tạm dừng / chạy tiếp, tắt app (kể cả mất điện) -> mở lại tự làm tiếp, không đọc
  lại văn bản AI đã xong; giữ Windows không ngủ khi còn việc; ước tính giờ xong theo tốc độ đo được.
- **Danh sách hồ sơ**: lọc theo lô / trạng thái (cả "có tài liệu cần kiểm tra", "chưa soát xong") / tìm kiếm, phân
  trang 50; tích chọn; thao tác cho hồ sơ đang tích hoặc đang lọc: Excel gộp, zip mỗi hồ sơ 1 Excel, "Chạy AI phần
  còn thiếu", bỏ khỏi hàng đợi, xóa (không đụng file gốc).
- **PDF dài**: màn Tách văn bản có cỡ ảnh Nhỏ/Vừa/Lớn, phím tắt (← → ↑ ↓, Space/Enter, N), nút "Đọc chữ để gợi ý"
  (job chỉ OCR) -> trang gợi ý viền cam nét đứt + nút "Đánh dấu cả … trang gợi ý". Hồ sơ nhiều file: nhãn tên file ở
  trang đầu mỗi file, nút "Mỗi file 1 tài liệu".
- Ổ cứng: không sao chép file gốc; không giữ ảnh 300 DPI (chỉ JPEG ~150 DPI để xem).

Đã kiểm thử bằng `backend/tests/` (OCR / AI giả): mọi kiểm tra API + giao diện đạt; 1000 thư mục / 3.333 file quét 5 giây.
**CHƯA thử** với OCR / AI thật và dữ liệu thật trên Windows: cần người dùng chạy thử với 1 lô nhỏ (vd. 10–20 thư mục)
và báo: mã hồ sơ gợi ý có đúng ý không, gợi ý file gộp có đúng không (file gộp thật có thể khác kiểu đã thử),
hộp chọn thư mục có hiện không, tốc độ thật.

Có thể làm tiếp (hỏi người dùng trước):
- Đổi đường dẫn thư mục gốc của cả lô khi người dùng đã chuyển thư mục sang ổ khác (hiện phải để file về chỗ cũ).
- Màn soát nhanh cho hàng nghìn tài liệu (vd. bảng sửa trực tiếp nhiều dòng, chỉ hiện tài liệu cần kiểm tra của cả lô).
- Chạy 2 hồ sơ song song trên máy mạnh (hiện mỗi lần 1 hồ sơ vì OCR + AI đều dùng hết CPU của ZBook).

## 5. Việc khác còn treo

- **Bước 7**: đóng gói thành file cài đặt `.exe` (Electron + backend đóng gói + model), cài được trên máy
  không có mạng, có hộp chọn thư mục/file gốc của Windows.
- `cai-dat.bat` / `mo-app.bat`: người dùng thử trên 1 máy khác (2026-11-07) — bước 6 (tải model 12 GB) lỗi giữa
  chừng, chạy lại thì tải lại từ đầu. Nguyên nhân: huggingface_hub bản mới dừng khi mạng im 10 giây và XÓA phần đã
  tải khi lỗi. Đã thay bằng `backend/app/download.py` (tự thử lại, tải tiếp từ file `.dang_tai`, kiểm tra ổ đĩa,
  giữ máy không ngủ, kiểm tra SHA-256). Chờ người dùng báo các bước còn lại.
- Ảnh README cũ (01–11) chụp trước khi có mục "Nhập thư mục" trên thanh trên cùng — chụp lại khi tiện
  (`backend/tests/anh_readme.js` là mẫu cách chụp có đánh số).
- Model AI thay thế (Gemma 4 26B-A4B…) chưa so sánh; người dùng đang dùng gpt-oss-20b.
