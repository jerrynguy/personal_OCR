// Nhóm trường để màn hình gọn: chỉ hiện trước những trường người dùng thực sự cần xem / sửa.

/** Trường đọc từ nội dung văn bản (soát kỹ) + vài trường người soát hay điền. */
export const DOC_MAIN = [
  'ten_loai_tai_lieu', 'so_cua_tai_lieu', 'ky_hieu_cua_tai_lieu', 'ngay_ban_hanh', 'co_quan_ban_hanh',
  'trich_yeu_noi_dung', 'tu_khoa', 'nguoi_ky', 'chuc_vu_nguoi_ky', 'do_mat', 'do_khan', 'but_tich', 'ghi_chu',
];
/** Trường của hồ sơ cần khi tạo / hay sửa; còn lại tự tính hoặc ít khi đổi. */
export const HO_SO_MAIN = ['ma_ho_so', 'tieu_de_ho_so', 'thoi_han_luu_tru', 'muc_do_tiep_can'];
export const PHONG_MAIN = ['ma_phong', 'ten_phong'];

/** Tách danh sách trường thành [nhóm chính (đúng thứ tự keys), phần còn lại]. */
export function splitFields(fields, keys) {
  const byKey = Object.fromEntries(fields.map((f) => [f.key, f]));
  const main = keys.map((k) => byKey[k]).filter(Boolean);
  const set = new Set(keys);
  return [main, fields.filter((f) => !set.has(f.key))];
}

/** Nhớ thông tin phông / hồ sơ của lần tạo trước (chỉ trên máy này). */
const KEY = 'sohoa_lan_truoc';
export function loadLast() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}');
  } catch {
    return {};
  }
}
export function saveLast(data) {
  try {
    localStorage.setItem(KEY, JSON.stringify(data));
  } catch {}
}

/** Gợi ý mã hồ sơ từ tên file PDF: "HS 15-2025 (scan).pdf" -> "HS_15-2025_scan". */
export function maFromFileName(name) {
  return (name || '')
    .replace(/\.pdf$/i, '')
    .replace(/[\\/:*?"<>|()[\]]+/g, ' ')
    .trim()
    .replace(/\s+/g, '_')
    .slice(0, 60);
}
