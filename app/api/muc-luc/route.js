import Anthropic from '@anthropic-ai/sdk';
import { LUUTRU_SYSTEM_PROMPT, LUUTRU_MAX_IMAGES, LUUTRU_MAX_REQUEST_BYTES } from '@/lib/luutru';

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

  const files = Array.isArray(body?.images) ? body.images : [];
  if (files.length === 0) {
    return Response.json({ error: 'Chưa có file nào được gửi lên.' }, { status: 400 });
  }
  if (files.length > LUUTRU_MAX_IMAGES) {
    return Response.json(
      { error: `Chỉ xử lý được tối đa ${LUUTRU_MAX_IMAGES} file/lần. Chia hồ sơ thành nhiều đợt nhỏ hơn.` },
      { status: 400 }
    );
  }

  const totalBytes = files.reduce((sum, f) => sum + (f.base64?.length || 0), 0);
  if (totalBytes > LUUTRU_MAX_REQUEST_BYTES) {
    return Response.json(
      {
        error:
          'Tổng dung lượng các file vượt quá giới hạn cho một lần gọi API (~30MB). ' +
          'Chia hồ sơ thành nhiều đợt nhỏ hơn, hoặc nén bớt PDF (mỗi PDF tối đa 100 trang theo giới hạn của Claude).',
      },
      { status: 400 }
    );
  }

  const anthropic = new Anthropic({
    apiKey: process.env.ANTHROPIC_API_KEY,
    ...(process.env.ANTHROPIC_WORKSPACE_ID
      ? { defaultHeaders: { 'anthropic-workspace-id': process.env.ANTHROPIC_WORKSPACE_ID } }
      : {}),
  });

  const contentBlocks = files.map((f) =>
    f.mediaType === 'application/pdf'
      ? { type: 'document', source: { type: 'base64', media_type: 'application/pdf', data: f.base64 } }
      : { type: 'image', source: { type: 'base64', media_type: f.mediaType, data: f.base64 } }
  );

  const fileList = files.map((f) => f.fileName).join(', ');

  try {
    const response = await anthropic.messages.create({
      model: process.env.ANTHROPIC_MODEL || 'claude-sonnet-5',
      max_tokens: 8192,
      system: LUUTRU_SYSTEM_PROMPT,
      messages: [
        {
          role: 'user',
          content: [
            ...contentBlocks,
            {
              type: 'text',
              text:
                `Hãy lập mục lục cho toàn bộ ${files.length} văn bản trong hồ sơ này theo đúng yêu cầu đã nêu. ` +
                `Tên file lần lượt theo đúng thứ tự đưa vào: ${fileList}.`,
            },
          ],
        },
      ],
    });

    const text = (response.content || [])
      .filter((b) => b.type === 'text')
      .map((b) => b.text)
      .join('');

    if (!text.trim()) {
      return Response.json({ error: 'Model không trả về kết quả. Thử lại.' }, { status: 502 });
    }

    return Response.json({ markdown: text, usage: response.usage });
  } catch (err) {
    console.error('Lỗi gọi Claude API:', err);
    const message = err?.status === 401 ? 'API key không hợp lệ.' : err.message || 'Lỗi gọi Claude API.';
    return Response.json({ error: message }, { status: err?.status || 500 });
  }
}
