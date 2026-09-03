'use client';

import { useState, useCallback, useRef } from 'react';
import { Upload, Loader2, AlertTriangle, X, ChevronDown, ChevronUp, FileWarning, Download } from 'lucide-react';
import { DOCUMENT_TYPE_LABELS, ACCEPTED_TYPES, MAX_SIZE_MB } from '@/lib/scanner';

const CONFIDENCE_META = {
  high: { label: 'Độ tin cậy cao', color: 'var(--success)' },
  medium: { label: 'Độ tin cậy trung bình', color: 'var(--warning)' },
  low: { label: 'Độ tin cậy thấp', color: 'var(--danger)' },
};

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Không đọc được file'));
    reader.readAsDataURL(file);
  });
}

function formatAmount(amount, currency) {
  if (amount === undefined || amount === null || amount === '') return null;
  const num = Number(amount);
  if (Number.isNaN(num)) return String(amount);
  return `${num.toLocaleString('vi-VN')}${currency ? ' ' + currency : ''}`;
}

function csvEscape(cell) {
  const s = String(cell ?? '');
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function documentsToCsv(docs) {
  const header = [
    'File',
    'Loại tài liệu',
    'Ngôn ngữ',
    'Ngày',
    'Bên phát hành',
    'Người nhận',
    'Tổng tiền',
    'Đơn vị tiền tệ',
    'Số giấy tờ',
    'Hạng mục',
    'Độ tin cậy',
    'Văn bản gốc',
  ];
  const rows = docs.map((d) => {
    const r = d.result || {};
    const lineItems = Array.isArray(r.line_items)
      ? r.line_items.map((it) => `${it.name ?? ''} x${it.quantity ?? ''} @${it.unit_price ?? ''}`).join('; ')
      : '';
    return [
      d.fileName,
      DOCUMENT_TYPE_LABELS[r.document_type] || r.document_type || '',
      r.language || '',
      r.date || '',
      r.issuer || '',
      r.recipient || '',
      r.total_amount ?? '',
      r.currency || '',
      r.id_number || '',
      lineItems,
      r.confidence || '',
      r.raw_text || '',
    ];
  });
  return [header, ...rows].map((row) => row.map(csvEscape).join(',')).join('\r\n');
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

let idCounter = 0;
function nextId() {
  idCounter += 1;
  return `doc-${Date.now()}-${idCounter}`;
}

function Field({ label, value }) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
        {label}
      </div>
      <div className="text-sm mt-0.5 break-words" style={{ fontFamily: 'var(--font-mono)' }}>
        {value}
      </div>
    </div>
  );
}

function DocCard({ doc, onRemove, onToggle, onRetry }) {
  const result = doc.result;
  const confidence = result ? CONFIDENCE_META[result.confidence] : null;

  return (
    <div className="rounded-md border p-4" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
      <div className="flex gap-4">
        <div
          className="relative overflow-hidden rounded flex-shrink-0 border"
          style={{ width: 88, height: 116, borderColor: 'var(--border)', background: 'var(--background)' }}
        >
          {doc.previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={doc.previewUrl}
              alt={doc.fileName}
              className="w-full h-full object-cover"
              style={{ opacity: doc.status === 'error' ? 0.4 : 1 }}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <FileWarning size={18} style={{ color: 'var(--text-secondary)' }} />
            </div>
          )}
          {doc.status === 'processing' && <div className="scan-line" />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div
              className="text-xs truncate"
              style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
              title={doc.fileName}
            >
              {doc.fileName}
            </div>
            <button
              onClick={() => onRemove(doc.id)}
              aria-label="Xóa"
              className="flex-shrink-0 rounded p-1 transition-colors"
              style={{ color: 'var(--text-secondary)' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <X size={14} />
            </button>
          </div>

          {doc.status === 'processing' && (
            <div className="flex items-center gap-2 mt-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <Loader2 size={14} className="spin" />
              Đang đọc ảnh…
            </div>
          )}

          {doc.status === 'error' && (
            <div className="mt-3">
              <div className="flex items-start gap-2 text-sm" style={{ color: 'var(--danger)' }}>
                <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                <span>{doc.error}</span>
              </div>
              {doc.base64 && (
                <button
                  onClick={() => onRetry(doc)}
                  className="mt-2 text-xs rounded px-2 py-1 border"
                  style={{ borderColor: 'var(--border)', color: 'var(--foreground)' }}
                >
                  Thử lại
                </button>
              )}
            </div>
          )}

          {doc.status === 'done' && result && (
            <div className="mt-2">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className="text-xs px-2 py-0.5 rounded border"
                  style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}
                >
                  {DOCUMENT_TYPE_LABELS[result.document_type] || result.document_type || 'Không rõ'}
                </span>
                {confidence && (
                  <span className="text-xs flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
                    <span
                      className="inline-block rounded-full"
                      style={{ width: 6, height: 6, background: confidence.color }}
                    />
                    {confidence.label}
                  </span>
                )}
                {result.language && (
                  <span
                    className="text-xs uppercase"
                    style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                  >
                    {result.language}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
                <Field label="Ngày" value={result.date} />
                <Field label="Bên phát hành" value={result.issuer} />
                <Field label="Người nhận" value={result.recipient} />
                <Field label="Tổng tiền" value={formatAmount(result.total_amount, result.currency)} />
                <Field label="Số giấy tờ" value={result.id_number} />
              </div>

              {Array.isArray(result.line_items) && result.line_items.length > 0 && (
                <div className="mt-3 rounded border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
                  <table className="w-full text-xs" style={{ fontFamily: 'var(--font-mono)' }}>
                    <thead>
                      <tr style={{ background: 'var(--surface-hover)' }}>
                        <th className="text-left font-medium px-2 py-1.5" style={{ color: 'var(--text-secondary)' }}>
                          Tên
                        </th>
                        <th className="text-right font-medium px-2 py-1.5" style={{ color: 'var(--text-secondary)' }}>
                          SL
                        </th>
                        <th className="text-right font-medium px-2 py-1.5" style={{ color: 'var(--text-secondary)' }}>
                          Đơn giá
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.line_items.map((item, i) => (
                        <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                          <td className="px-2 py-1.5">{item.name}</td>
                          <td className="px-2 py-1.5 text-right">{item.quantity ?? ''}</td>
                          <td className="px-2 py-1.5 text-right">
                            {item.unit_price !== undefined ? Number(item.unit_price).toLocaleString('vi-VN') : ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <button
                onClick={() => onToggle(doc.id)}
                className="mt-3 flex items-center gap-1 text-xs"
                style={{ color: 'var(--text-secondary)' }}
              >
                {doc.expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                {doc.expanded ? 'Ẩn văn bản gốc' : 'Xem văn bản gốc'}
              </button>
              {doc.expanded && (
                <pre
                  className="mt-2 text-xs rounded p-2 max-h-40 overflow-auto whitespace-pre-wrap"
                  style={{
                    background: 'var(--background)',
                    color: 'var(--text-secondary)',
                    fontFamily: 'var(--font-mono)',
                    border: '1px solid var(--border)',
                  }}
                >
                  {result.raw_text || '(không có)'}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [documents, setDocuments] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  const scanDocument = useCallback(async (id, base64, mediaType) => {
    try {
      const response = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base64, mediaType }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.error || `API trả lỗi (mã ${response.status}).`);
      }
      if (!data?.result) {
        throw new Error('Không nhận được kết quả trích xuất.');
      }

      setDocuments((prev) => prev.map((d) => (d.id === id ? { ...d, status: 'done', result: data.result } : d)));
    } catch (err) {
      setDocuments((prev) =>
        prev.map((d) => (d.id === id ? { ...d, status: 'error', error: err.message || 'Có lỗi xảy ra' } : d))
      );
    }
  }, []);

  // Mọi file được thêm vào danh sách ngay lập tức (không chờ nhau), rồi mỗi file
  // tự đọc base64 + gọi API độc lập — cả loạt ảnh được quét song song, không tuần tự.
  const addFiles = useCallback(
    (fileList) => {
      const files = Array.from(fileList);
      files.forEach((file) => {
        if (!ACCEPTED_TYPES.includes(file.type)) {
          setDocuments((prev) => [
            ...prev,
            {
              id: nextId(),
              fileName: file.name,
              previewUrl: null,
              base64: null,
              mediaType: null,
              status: 'error',
              error: `Định dạng không hỗ trợ (${file.type || 'không xác định'}). Chỉ nhận JPEG, PNG, GIF, WebP.`,
              result: null,
              expanded: false,
            },
          ]);
          return;
        }
        if (file.size > MAX_SIZE_MB * 1024 * 1024) {
          setDocuments((prev) => [
            ...prev,
            {
              id: nextId(),
              fileName: file.name,
              previewUrl: URL.createObjectURL(file),
              base64: null,
              mediaType: null,
              status: 'error',
              error: `File vượt quá ${MAX_SIZE_MB}MB. Nén hoặc chụp lại ở độ phân giải thấp hơn.`,
              result: null,
              expanded: false,
            },
          ]);
          return;
        }

        const id = nextId();
        const previewUrl = URL.createObjectURL(file);
        setDocuments((prev) => [
          ...prev,
          {
            id,
            fileName: file.name,
            previewUrl,
            base64: null,
            mediaType: file.type,
            status: 'processing',
            result: null,
            error: null,
            expanded: false,
          },
        ]);

        fileToBase64(file)
          .then((base64) => {
            setDocuments((prev) => prev.map((d) => (d.id === id ? { ...d, base64 } : d)));
            scanDocument(id, base64, file.type);
          })
          .catch(() => {
            setDocuments((prev) =>
              prev.map((d) => (d.id === id ? { ...d, status: 'error', error: 'Không đọc được file ảnh' } : d))
            );
          });
      });
    },
    [scanDocument]
  );

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      setIsDragging(false);
      if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
    },
    [addFiles]
  );

  const removeDocument = (id) => setDocuments((prev) => prev.filter((d) => d.id !== id));
  const toggleExpand = (id) =>
    setDocuments((prev) => prev.map((d) => (d.id === id ? { ...d, expanded: !d.expanded } : d)));
  const retryDocument = (doc) => {
    setDocuments((prev) => prev.map((d) => (d.id === doc.id ? { ...d, status: 'processing', error: null } : d)));
    scanDocument(doc.id, doc.base64, doc.mediaType);
  };

  const activeCount = documents.filter((d) => d.status === 'processing').length;
  const doneCount = documents.filter((d) => d.status === 'done' && d.result).length;
  const handleDownloadCsv = () => {
    const done = documents.filter((d) => d.status === 'done' && d.result);
    if (done.length === 0) return;
    downloadBlob('\uFEFF' + documentsToCsv(done), 'ket-qua-quet.csv', 'text/csv;charset=utf-8');
  };

  return (
    <div className="flex-1">
      <div className="border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="max-w-3xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <div
              className="text-xs tracking-widest uppercase"
              style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}
            >
              Document Scanner
            </div>
            <h1 className="text-xl font-semibold mt-1">Quét &amp; trích xuất thông tin từ ảnh</h1>
          </div>
          <div
            className="flex items-center gap-2 text-xs flex-shrink-0"
            style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
          >
            <span
              className={`inline-block rounded-full ${activeCount > 0 ? 'pulse-dot' : ''}`}
              style={{ width: 7, height: 7, background: activeCount > 0 ? 'var(--accent)' : 'var(--text-secondary)' }}
            />
            {activeCount > 0 ? `ĐANG QUÉT ${activeCount}` : 'SẴN SÀNG'}
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-8">
        <div
          role="button"
          tabIndex={0}
          className="drop-zone cursor-pointer rounded-md border-2 border-dashed flex flex-col items-center justify-center py-12 px-6 transition-colors"
          style={{
            borderColor: isDragging ? 'var(--accent)' : 'var(--border)',
            background: isDragging ? 'rgba(56,223,216,0.06)' : 'var(--surface)',
          }}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={onDrop}
        >
          <Upload size={26} style={{ color: 'var(--accent)' }} />
          <p className="mt-3 text-sm font-medium">Thả ảnh vào đây, hoặc bấm để chọn file</p>
          <p className="mt-1 text-xs" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            JPEG · PNG · GIF · WEBP — tối đa {MAX_SIZE_MB}MB / ảnh, chọn được nhiều ảnh cùng lúc
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/gif,image/webp"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) addFiles(e.target.files);
              e.target.value = '';
            }}
          />
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 pb-16 space-y-3">
        {documents.length === 0 && (
          <div className="text-center py-10 text-sm" style={{ color: 'var(--text-secondary)' }}>
            Chưa có ảnh nào. Tải lên một hóa đơn, giấy tờ, hoặc danh thiếp để bắt đầu.
          </div>
        )}
        {doneCount > 0 && (
          <div className="flex justify-end">
            <button
              onClick={handleDownloadCsv}
              className="text-xs rounded px-2 py-1 border flex items-center gap-1"
              style={{ borderColor: 'var(--border)', color: 'var(--foreground)' }}
            >
              <Download size={12} /> Tải CSV ({doneCount})
            </button>
          </div>
        )}
        {documents
          .slice()
          .reverse()
          .map((doc) => (
            <DocCard key={doc.id} doc={doc} onRemove={removeDocument} onToggle={toggleExpand} onRetry={retryDocument} />
          ))}
      </div>
    </div>
  );
}
