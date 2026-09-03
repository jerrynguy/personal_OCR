// Định nghĩa chung: loại tài liệu, tool schema để ép Claude trả JSON có cấu trúc,
// và system prompt. Dùng chung cho cả API route (server) lẫn UI (client).

export const DOCUMENT_TYPE_LABELS = {
  hoa_don: 'Hóa đơn',
  bien_lai: 'Biên lai',
  hop_dong: 'Hợp đồng',
  cmnd_cccd: 'CMND / CCCD',
  ho_chieu: 'Hộ chiếu',
  danh_thiep: 'Danh thiếp',
  khac: 'Khác',
};

export const EXTRACT_TOOL = {
  name: 'extract_document_info',
  description:
    'Trích xuất thông tin có cấu trúc từ ảnh tài liệu (hóa đơn, biên lai, hợp đồng, giấy tờ tùy thân, danh thiếp...).',
  input_schema: {
    type: 'object',
    properties: {
      document_type: {
        type: 'string',
        enum: Object.keys(DOCUMENT_TYPE_LABELS),
        description: 'Loại tài liệu được phát hiện trong ảnh',
      },
      language: { type: 'string', description: 'Ngôn ngữ chính trong ảnh, ví dụ: vi, en, zh' },
      date: {
        type: 'string',
        description: 'Ngày tháng chính trên tài liệu, định dạng YYYY-MM-DD. Để trống nếu không có.',
      },
      issuer: { type: 'string', description: 'Bên phát hành / cửa hàng / công ty' },
      recipient: { type: 'string', description: 'Người nhận / khách hàng, nếu có' },
      total_amount: { type: 'number', description: 'Tổng số tiền, nếu có' },
      currency: { type: 'string', description: 'Đơn vị tiền tệ: VND, USD, CNY...' },
      id_number: { type: 'string', description: 'Số CMND/CCCD/hộ chiếu nếu là giấy tờ tùy thân' },
      line_items: {
        type: 'array',
        description: 'Danh sách hạng mục nếu là hóa đơn/biên lai',
        items: {
          type: 'object',
          properties: {
            name: { type: 'string' },
            quantity: { type: 'number' },
            unit_price: { type: 'number' },
          },
        },
      },
      raw_text: { type: 'string', description: 'Toàn bộ văn bản đọc được trong ảnh, dùng làm fallback' },
      confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    },
    required: ['document_type', 'language', 'raw_text', 'confidence'],
  },
};

export const SYSTEM_PROMPT =
  'Bạn là hệ thống trích xuất dữ liệu từ ảnh tài liệu (hóa đơn, biên lai, hợp đồng, giấy tờ tùy thân, danh thiếp...). ' +
  'Tài liệu có thể ở tiếng Việt, tiếng Trung, tiếng Anh hoặc ngôn ngữ khác. Đọc kỹ nội dung ảnh và gọi tool ' +
  'extract_document_info với dữ liệu chính xác nhất có thể. Nếu không chắc một trường nào đó, để trống thay vì đoán bừa.';

export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
export const MAX_SIZE_MB = 5;
