# Kiểm thử không cần model thật

Môi trường cloud (và máy chưa tải model) không có PaddleOCR / VietOCR / LLM. Các script ở đây chạy **backend thật**
(API, CSDL, hàng đợi, xuất file, giao diện đã build) với **OCR giả** và **AI giả**:

- `tao_du_lieu_thu.py` — tạo PDF "scan" (ảnh, nội dung giả) kèm đáp án `<tên>.truth.json`: thư mục `Đà Lạt 1L`
  kiểu dữ liệu thật (file gộp ghép thẳng, file gộp đã nén lại, tên file trùng tiền tố, file hỏng, thư mục 10 sau 6)
  và `ho_so_dai.pdf` (27 trang, 14 tài liệu).
- `server_gia.py` — chạy backend: OCR giả trả các dòng chữ trong đáp án đúng toạ độ trên ảnh; AI giả trả JSON đúng schema.
- `test_nhap_thu_muc.py` — quét thư mục, gợi ý mã / file gộp, tạo hàng loạt, tạm dừng / chạy tiếp, xuất Excel gộp / zip,
  lọc + phân trang, nhập lại, chạy lại giữ ô sửa tay.
- `test_tiep_tuc.py` — PDF dài: đọc chữ trước -> gợi ý trang đầu; tắt app đột ngột giữa lúc AI chạy -> mở lại tự làm tiếp;
  hủy / bỏ khỏi hàng; file gốc bị đổi tên -> lỗi rõ ràng, không kẹt hàng đợi.
- `ui_hang_loat.js` — Playwright: đi trọn giao diện nhập thư mục, hàng đợi, soát, tách file dài bằng phím tắt, xuất.
- `anh_readme.js` — chụp lại ảnh có đánh số cho README (`docs/images/12..16-*.png`).

Chạy (thư mục `backend`, đã cài `requirements.txt` — không cần paddle/torch; giao diện đã `npm run build`):

```bash
python tests/tao_du_lieu_thu.py /tmp/kt/du_lieu
python tests/server_gia.py /tmp/kt/data /tmp/kt/du_lieu 8765 0.15 0.4 &
python tests/test_nhap_thu_muc.py /tmp/kt/du_lieu /tmp/kt/data
python tests/test_tiep_tuc.py /tmp/kt/du_lieu /tmp/kt
```

Kiểm thử giao diện / chụp ảnh README: chạy lại `server_gia.py` với thư mục data **trống** rồi
`node tests/ui_hang_loat.js /tmp/kt/du_lieu /tmp/kt/anh` hoặc `node tests/anh_readme.js /tmp/kt/du_lieu`.
