# Document Scanner

Quét ảnh tài liệu (hóa đơn, biên lai, hợp đồng, giấy tờ tùy thân, danh thiếp...) ở
tiếng Việt, tiếng Trung, tiếng Anh hoặc ngôn ngữ khác, và trích xuất thông tin ra
một JSON có cấu trúc chuẩn (loại tài liệu, ngày, bên phát hành, số tiền...) bằng
Claude API — không cần OCR engine riêng.

Đây là công cụ **mã nguồn mở, tự chạy (self-hosted)**: mỗi người tự clone repo,
tự dùng API key Anthropic của riêng mình, dữ liệu và ảnh không rời khỏi máy bạn.

## Cài đặt

```bash
git clone <đường dẫn repo của bạn>
cd document-scanner
npm install
cp .env.example .env.local
```

Mở `.env.local`, điền API key của bạn (lấy tại
[platform.claude.com/settings/keys](https://platform.claude.com/settings/keys)):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Chạy dự án:

```bash
npm run dev
```

Mở [http://localhost:3000](http://localhost:3000), thả ảnh vào để thử.

## Cách hoạt động

Dự án có 2 công cụ, chuyển qua lại bằng thanh menu trên cùng:

**1. Quét tài liệu (`/`)** — mỗi ảnh xử lý độc lập, trả về JSON có cấu trúc
(loại tài liệu, ngày, bên phát hành, tổng tiền...). Phù hợp hóa đơn, biên lai,
giấy tờ tùy thân, danh thiếp — xử lý từng tờ một cách độc lập.

**2. Mục lục lưu trữ (`/muc-luc`)** — thả toàn bộ ảnh scan của **một hồ sơ**
cùng lúc (tối đa 20 ảnh), bấm "Lập mục lục". Cả hồ sơ được gửi trong **một**
lần gọi API để Claude sắp xếp và gộp trùng đúng cách theo nghiệp vụ lưu trữ,
trả về một bảng Markdown — có thể tải về dạng `.md` hoặc `.csv`.

Cả hai đều gửi ảnh (base64) tới API route riêng của mỗi công cụ (`/api/scan`
hoặc `/api/muc-luc`), route đó mới gọi Claude bằng key trong `.env.local` —
key không bao giờ lộ ra trình duyệt.

## Đổi model

Mặc định dùng `claude-sonnet-5` (cân bằng giá/độ chính xác). Có thể đổi trong
`.env.local`:

| Model | Khi nào dùng |
|---|---|
| `claude-haiku-4-5-20251001` | Ảnh rõ, chữ in, khối lượng lớn, cần rẻ + nhanh |
| `claude-sonnet-5` | Mặc định — cân bằng độ chính xác và chi phí |
| `claude-opus-5` | Ảnh mờ, chữ viết tay, tài liệu phức tạp nhiều cột/bảng |

```
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

## Deploy bản online riêng (tùy chọn)

Không bắt buộc — chạy local là đủ dùng. Nếu muốn có bản online riêng (chỉ mình
bạn dùng, hoặc chia sẻ cho người khác dùng chung key của bạn), deploy lên Vercel
và thêm biến môi trường `ANTHROPIC_API_KEY` trong phần Settings → Environment
Variables của project.

> **Lưu ý:** ảnh gửi lên có thể khá lớn sau khi encode base64. Nếu deploy lên một
> nền tảng serverless có giới hạn kích thước request (ví dụ Vercel), cân nhắc
> giảm `MAX_SIZE_MB` trong `lib/scanner.js` nếu gặp lỗi request quá lớn.

## Đóng gói thành app desktop (Windows, có icon riêng)

Dành cho người dùng không quen dòng lệnh: build ra một file cài đặt `.exe`,
cài xong có icon trên Desktop, bấm vào mở thẳng app trong cửa sổ riêng (không
qua trình duyệt, không cần mở Terminal). Lần đầu mở app sẽ hiện màn hình nhập
API key ngay trong app — không cần sửa file `.env` bằng Notepad.

**Bắt buộc build trên máy Windows thật** — không cross-build từ Mac/Linux
được (electron-builder cần Wine để nhúng icon vào .exe khi build từ hệ điều
hành khác Windows). Trên Windows thì không cần Wine, tự chạy được luôn.

```bash
npm install
npm run dist:win
```

Đợi vài phút (lần đầu sẽ tải Electron ~115MB), file cài đặt nằm ở
`dist/Document Scanner Setup <version>.exe`. Chạy file đó để cài — trình cài
đặt có tùy chọn tạo icon Desktop + Start Menu. Cài xong, mở app lần đầu sẽ
hiện màn hình nhập API key.

Muốn đổi key sau này: mở app → menu **Cài đặt → Đổi API key...**

Nếu lúc dùng app báo lỗi `anthropic-workspace-id is required`, điền thêm ô
**Workspace ID** ở màn hình cài đặt trong app (lấy tại Console → Settings →
Workspaces) — không cần sửa file gì cả, app tự lưu.

## Lưu ý bảo mật

- **Không commit `.env.local` lên Git** — file này đã nằm trong `.gitignore`.
- Ảnh tài liệu có thể chứa dữ liệu nhạy cảm (CMND, hợp đồng...). Công cụ này
  không lưu ảnh lên server nào khác ngoài việc gửi trực tiếp tới Claude API để
  xử lý; ảnh không được ghi ra đĩa.
- Đây là công cụ single-user, tự chạy — không có đăng nhập/phân quyền. Nếu bạn
  tự deploy một bản public cho nhiều người dùng chung, tự thêm xác thực trước
  khi làm vậy.
- Bản app desktop (Electron): API key nhập trong app được lưu vào một file
  `config.json` riêng trong thư mục dữ liệu ứng dụng của Windows (thường ở
  `%APPDATA%\document-scanner\`), không phải trong thư mục cài đặt — không bị
  ai khác đọc được trừ khi có quyền truy cập máy đó.

## Giấy phép

MIT — dùng, sửa, chia sẻ thoải mái.
