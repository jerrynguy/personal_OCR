import Anthropic from '@anthropic-ai/sdk';
import { EXTRACT_TOOL, SYSTEM_PROMPT } from '@/lib/scanner';

// Route này chạy trên server (Node.js), key không bao giờ tới trình duyệt người dùng.
export async function POST(request) {
  if (!process.env.ANTHROPIC_API_KEY) {
    return Response.json(
      { error: 'Chưa cấu hình ANTHROPIC_API_KEY. Xem file .env.example và README.' },
      { status: 500 }
    );
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: 'Request không hợp lệ.' }, { status: 400 });
  }

  const { base64, mediaType } = body || {};
  if (!base64 || !mediaType) {
    return Response.json({ error: 'Thiếu dữ liệu ảnh (base64/mediaType).' }, { status: 400 });
  }

  const anthropic = new Anthropic({
    apiKey: process.env.ANTHROPIC_API_KEY,
    ...(process.env.ANTHROPIC_WORKSPACE_ID
      ? { defaultHeaders: { 'anthropic-workspace-id': process.env.ANTHROPIC_WORKSPACE_ID } }
      : {}),
  });

  try {
    const response = await anthropic.messages.create({
      model: process.env.ANTHROPIC_MODEL || 'claude-sonnet-5',
      max_tokens: 1024,
      system: SYSTEM_PROMPT,
      messages: [
        {
          role: 'user',
          content: [
            { type: 'image', source: { type: 'base64', media_type: mediaType, data: base64 } },
            { type: 'text', text: 'Hãy trích xuất thông tin từ tài liệu trong ảnh này.' },
          ],
        },
      ],
      tools: [EXTRACT_TOOL],
      tool_choice: { type: 'tool', name: 'extract_document_info' },
    });

    const toolUse = response.content.find((b) => b.type === 'tool_use');
    if (!toolUse) {
      return Response.json(
        { error: 'Model không trả về kết quả trích xuất. Thử ảnh khác hoặc thử lại.' },
        { status: 502 }
      );
    }

    return Response.json({ result: toolUse.input });
  } catch (err) {
    console.error('Lỗi gọi Claude API:', err);
    const message = err?.status === 401 ? 'API key không hợp lệ.' : err.message || 'Lỗi gọi Claude API.';
    return Response.json({ error: message }, { status: err?.status || 500 });
  }
}
