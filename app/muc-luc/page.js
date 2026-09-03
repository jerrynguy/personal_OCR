'use client';

import { useState, useCallback, useRef } from 'react';
import { Upload, Loader2, AlertTriangle, X, Download, FileSpreadsheet, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ACCEPTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const ACCEPTED_TYPES = [...ACCEPTED_IMAGE_TYPES, 'application/pdf'];
const MAX_IMAGE_SIZE_MB = 5;
const MAX_PDF_SIZE_MB = 30;
const MAX_IMAGES = 20;

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Không đọc được file'));
    reader.readAsDataURL(file);
  });
}

let idCounter = 0;
function nextId() {
  idCounter += 1;
  return `f-${Date.now()}-${idCounter}`;
}

function mdTableToRows(markdown) {
  const lines = markdown.split('\n').filter((l) => l.trim().startsWith('|'));
  const rows = [];
  for (const line of lines) {
    const cells = line
      .trim()
      .replace(/^\||\|$/g, '')
      .split('|')
      .map((c) => c.trim());
    if (cells.every((c) => /^:?-+:?$/.test(c))) continue; // dòng phân cách header
    rows.push(cells);
  }
  return rows;
}

function rowsToCsv(rows) {
  const escape = (cell) => {
    const s = String(cell ?? '');
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return rows.map((r) => r.map(escape).join(',')).join('\r\n');
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

export default function MucLucPage() {
  const [files, setFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState('idle'); // idle | processing | done | error
  const [resultMarkdown, setResultMarkdown] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const fileInputRef = useRef(null);

  const addFiles = useCallback((fileList) => {
    const incoming = Array.from(fileList);
    setErrorMsg('');
    setFiles((prev) => {
      const room = MAX_IMAGES - prev.length;
      const toAdd = incoming.slice(0, Math.max(room, 0));
      const rejectedForLimit = incoming.length - toAdd.length;

      const next = toAdd
        .filter((file) => {
          if (!ACCEPTED_TYPES.includes(file.type)) return false;
          const isPdf = file.type === 'application/pdf';
          const limitBytes = (isPdf ? MAX_PDF_SIZE_MB : MAX_IMAGE_SIZE_MB) * 1024 * 1024;
          if (file.size > limitBytes) return false;
          return true;
        })
        .map((file) => {
          const id = nextId();
          const isPdf = file.type === 'application/pdf';
          const entry = {
            id,
            file,
            fileName: file.name,
            previewUrl: isPdf ? null : URL.createObjectURL(file),
            isPdf,
            mediaType: file.type,
            base64: null,
          };
          fileToBase64(file).then((base64) => {
            setFiles((cur) => cur.map((f) => (f.id === id ? { ...f, base64 } : f)));
          });
          return entry;
        });

      if (rejectedForLimit > 0) {
        setErrorMsg(`Chỉ nhận tối đa ${MAX_IMAGES} ảnh/lần — đã bỏ qua ${rejectedForLimit} ảnh cuối.`);
      }
      return [...prev, ...next];
    });
  }, []);

  const removeFile = (id) => setFiles((prev) => prev.filter((f) => f.id !== id));
  const clearAll = () => {
    setFiles([]);
    setResultMarkdown('');
    setStatus('idle');
    setErrorMsg('');
  };

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      setIsDragging(false);
      if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
    },
    [addFiles]
  );

  const submit = async () => {
    if (files.length === 0) return;
    setStatus('processing');
    setErrorMsg('');
    setResultMarkdown('');

    try {
      const images = files.map((f) => ({ fileName: f.fileName, mediaType: f.mediaType, base64: f.base64 }));
      const response = await fetch('/api/muc-luc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ images }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error || `API trả lỗi (mã ${response.status}).`);
      if (!data?.markdown) throw new Error('Không nhận được kết quả.');

      setResultMarkdown(data.markdown);
      setStatus('done');
    } catch (err) {
      setErrorMsg(err.message || 'Có lỗi xảy ra');
      setStatus('error');
    }
  };

  const handleDownloadMd = () => downloadBlob(resultMarkdown, 'muc-luc.md', 'text/markdown');
  const handleDownloadCsv = () => {
    const rows = mdTableToRows(resultMarkdown);
    if (rows.length === 0) return;
    downloadBlob('\uFEFF' + rowsToCsv(rows), 'muc-luc.csv', 'text/csv;charset=utf-8');
  };

  const isProcessing = status === 'processing';

  return (
    <div className="flex-1">
      <div className="border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="max-w-3xl mx-auto px-6 py-5">
          <div
            className="text-xs tracking-widest uppercase"
            style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}
          >
            Mục lục hồ sơ lưu trữ
          </div>
          <h1 className="text-xl font-semibold mt-1">Lập mục lục văn bản trong hồ sơ</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            Thả toàn bộ ảnh scan các văn bản trong một hồ sơ, xử lý cùng lúc để sắp xếp và gộp trùng đúng cách.
          </p>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-8">
        <div
          role="button"
          tabIndex={0}
          className="drop-zone cursor-pointer rounded-md border-2 border-dashed flex flex-col items-center justify-center py-10 px-6 transition-colors"
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
          <Upload size={24} style={{ color: 'var(--accent)' }} />
          <p className="mt-2 text-sm font-medium">Thả ảnh hoặc PDF vào đây, hoặc bấm để chọn nhiều file</p>
          <p className="mt-1 text-xs" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            JPEG · PNG · GIF · WEBP (tối đa {MAX_IMAGE_SIZE_MB}MB/ảnh) · PDF (tối đa {MAX_PDF_SIZE_MB}MB, 100
            trang/file) — tối đa {MAX_IMAGES} file/lần
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/gif,image/webp,application/pdf"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) addFiles(e.target.files);
              e.target.value = '';
            }}
          />
        </div>

        {files.length > 0 && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {files.length} file đã chọn
              </div>
              <button onClick={clearAll} className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Xóa hết
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {files.map((f) => (
                <div
                  key={f.id}
                  className="relative rounded border overflow-hidden"
                  style={{ width: 64, height: 64, borderColor: 'var(--border)' }}
                >
                  {f.isPdf ? (
                    <div
                      className="w-full h-full flex flex-col items-center justify-center gap-0.5 px-1"
                      style={{ background: 'var(--surface-hover)' }}
                    >
                      <FileText size={18} style={{ color: 'var(--text-secondary)' }} />
                      <span
                        className="text-[8px] leading-tight text-center break-all line-clamp-2"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {f.fileName}
                      </span>
                    </div>
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={f.previewUrl} alt={f.fileName} className="w-full h-full object-cover" />
                  )}
                  <button
                    onClick={() => removeFile(f.id)}
                    aria-label="Xóa ảnh"
                    className="absolute top-0.5 right-0.5 rounded-full p-0.5"
                    style={{ background: 'rgba(18,20,26,0.75)', color: 'var(--foreground)' }}
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>

            <button
              onClick={submit}
              disabled={isProcessing}
              className="mt-4 w-full sm:w-auto px-5 py-2 rounded-md text-sm font-medium flex items-center justify-center gap-2 transition-opacity"
              style={{
                background: 'var(--accent)',
                color: 'var(--background)',
                opacity: isProcessing ? 0.6 : 1,
                cursor: isProcessing ? 'not-allowed' : 'pointer',
              }}
            >
              {isProcessing ? (
                <>
                  <Loader2 size={16} className="spin" />
                  Đang lập mục lục…
                </>
              ) : (
                'Lập mục lục'
              )}
            </button>
          </div>
        )}

        {errorMsg && (
          <div className="mt-4 flex items-start gap-2 text-sm" style={{ color: 'var(--danger)' }}>
            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {status === 'done' && resultMarkdown && (
          <div className="mt-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold">Kết quả</h2>
              <div className="flex gap-2">
                <button
                  onClick={handleDownloadMd}
                  className="text-xs rounded px-2 py-1 border flex items-center gap-1"
                  style={{ borderColor: 'var(--border)', color: 'var(--foreground)' }}
                >
                  <Download size={12} /> .md
                </button>
                <button
                  onClick={handleDownloadCsv}
                  className="text-xs rounded px-2 py-1 border flex items-center gap-1"
                  style={{ borderColor: 'var(--border)', color: 'var(--foreground)' }}
                >
                  <FileSpreadsheet size={12} /> .csv
                </button>
              </div>
            </div>
            <div
              className="markdown-table-wrap rounded border overflow-auto"
              style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{resultMarkdown}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
