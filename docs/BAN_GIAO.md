# Bàn giao — đọc file này trước khi làm tiếp

Tài liệu để một phiên làm việc mới (người hoặc AI) nắm ngay bối cảnh. Cập nhật: 2026-11-07.

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
  app/pipeline.py     xử lý 1 hồ sơ: tách trang -> OCR -> chia tài liệu theo ranh giới -> luật -> AI (hiện dần)
  app/jobs.py         hàng đợi: mỗi lần 1 hồ sơ, tiến độ theo giai đoạn, hủy
  app/api.py          API cho giao diện; app/db.py SQLite; app/export.py Excel/CSV 23 cột + tách PDF
  app/schema/tt05.json  danh sách trường (phông 10, hồ sơ 19, tài liệu 23 — nhãn nguyên văn TT05)
frontend/  Next.js xuất file tĩnh (frontend/out), backend phục vụ trực tiếp
cai-dat.bat (+ tools/cai-dat.ps1), mo-app.bat   bấm đúp để cài / mở app (CHƯA chạy thử trên Windows)
models/, data/   (không commit) model OCR + LLM, CSDL + file hồ sơ
```

- Model AI mặc định: `gpt-oss-20b-MXFP4.gguf` (đổi được ở trang Model AI). Trên ZBook: ~30–60 giây/tài liệu
  cho phần AI, OCR ~3–5 giây/trang. PDF mẫu 3 trang / 2 tài liệu: ~94 giây.
- Kiểm thử trong môi trường cloud: không tải được model thật (HuggingFace/Paddle bị chặn) → dùng OCR giả và
  llama-server giả (xem cách làm trong lịch sử commit); kiểm thử giao diện bằng Playwright.

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

## 4. VIỆC TIẾP THEO (yêu cầu chính, chưa làm)

Người dùng: *"Đây là làm cho từng tài liệu riêng lẻ. Làm cả 1 thư mục hàng trăm file đã số hóa được không?
Hoặc 1 file PDF của 1 hồ sơ có hàng chục, hàng trăm file tài liệu bên trong được không?"*

Dữ liệu thật (theo mô tả của người dùng):
- Một thư mục lớn (vd. **"Đà Lạt 1L"**) chứa các **thư mục con đánh số** (1, 2, … ~1000). **Mỗi thư mục con
  là 1 hồ sơ.**
- Trong thư mục con: các file PDF đã số hóa, **thường mỗi file là 1 tài liệu** (1 trang như giấy khen, hoặc
  nhiều trang như quyết định). Tên file kiểu `H..xx.yy.1.pdf`, `H..xx.yy.100001.pdf`… (không cố định).
- Có thư mục chứa **thêm 1 file là bản gộp** của các file còn lại (vd. `…1.pdf` = `…100001.pdf` +
  `…100002.pdf`). Thư mục chỉ có 1 file `…1.pdf` thì đó là file bình thường.

Hướng đề xuất (CẦN HỎI người dùng xác nhận trước khi làm, đặc biệt mục c):
a. **Nhập cả thư mục**: chọn thư mục cha → mỗi thư mục con = 1 hồ sơ, mỗi file PDF = 1 tài liệu (ranh giới
   theo file, không tự chia). Bảng xem trước (thư mục, mã hồ sơ sửa được, số file/trang, tích chọn từng file)
   → tạo hàng loạt + xếp hàng xử lý (chạy qua đêm). Đường dẫn thư mục: dán đường dẫn (bản desktop Bước 7 sẽ có
   hộp chọn thư mục). Backend đọc trực tiếp file trên máy, không cần tải lên.
b. **1 PDF có hàng trăm tài liệu**: màn tách phải nhanh cho file dài — xem nhiều trang/lưới lớn, phím tắt,
   app **gợi ý** trang có thể là trang đầu (có quốc hiệu/dòng "Số:") để người dùng xác nhận nhanh (không tự áp).
c. **File gộp trong thư mục**: KHÔNG tự loại theo tên. Cách an toàn: ở bảng xem trước, người dùng bỏ tích file
   gộp; có thể **gợi ý** "file này trùng nội dung với các file khác ghép lại" (so ảnh từng trang) nhưng để người
   dùng quyết định. Hỏi người dùng có muốn gợi ý này không.
d. Quy mô: hàng nghìn tài liệu × 30–60 giây AI = nhiều giờ → hàng đợi bền (sống qua khi tắt app), tiếp tục
   khi mở lại, có thể tạm dừng; cân nhắc chế độ "chỉ luật, không AI" để nhanh; danh sách hồ sơ/tài liệu phân
   trang; xuất Excel gộp nhiều hồ sơ một lần.

## 5. Việc khác còn treo

- **Bước 7**: đóng gói thành file cài đặt `.exe` (Electron + backend đóng gói + model), cài được trên máy
  không có mạng, có hộp chọn thư mục/file gốc của Windows.
- `cai-dat.bat` / `mo-app.bat` chưa được chạy thử trên Windows — chờ người dùng báo kết quả.
- Model AI thay thế (Gemma 4 26B-A4B…) chưa so sánh; người dùng đang dùng gpt-oss-20b.
