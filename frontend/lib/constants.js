export const STATUS = {
  moi: ['Mới tạo', 'bg-gray-100 text-gray-600'],
  cho: ['Đang chờ', 'bg-blue-50 text-blue-700'],
  dang_xu_ly: ['Đang xử lý', 'bg-blue-50 text-blue-700'],
  xong: ['Xong', 'bg-green-50 text-green-700'],
  loi: ['Lỗi', 'bg-red-50 text-red-700'],
};

/** Bộ lọc trạng thái ở danh sách hồ sơ (giá trị gửi backend: trang_thai). */
export const STATUS_FILTERS = [
  ['', 'Mọi trạng thái'],
  ['cho', 'Đang chờ'],
  ['dang_xu_ly', 'Đang xử lý'],
  ['xong', 'Xong'],
  ['loi', 'Lỗi'],
  ['moi', 'Mới tạo'],
  ['can_kiem_tra', 'Có tài liệu cần kiểm tra'],
  ['chua_soat', 'Chưa soát xong'],
];
