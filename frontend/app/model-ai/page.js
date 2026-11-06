'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Bot, CheckCircle2, FolderSearch, Loader2, RotateCcw, Trash2, Upload } from 'lucide-react';
import { api, upload } from '@/lib/api';

export default function ModelAiPage() {
  const [st, setSt] = useState(null);
  const [error, setError] = useState('');
  const [path, setPath] = useState('');
  const [pct, setPct] = useState(null);
  const fileInput = useRef(null);

  const load = useCallback(async () => {
    try {
      setSt(await api('/llm'));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!st?.dang_nap) return undefined;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [st?.dang_nap, load]);

  const run = async (fn) => {
    setError('');
    try {
      const res = await fn();
      if (res?.danh_sach) setSt(res);
    } catch (e) {
      setError(e.message);
    }
    load();
  };

  const chooseModel = (duong_dan) => run(() => api('/llm/chon', { method: 'POST', body: { duong_dan } }));

  const onUpload = (file) =>
    run(async () => {
      if (!file) return null;
      if (!file.name.toLowerCase().endsWith('.gguf')) throw new Error('Chỉ nhận file .gguf');
      setPct(0);
      try {
        const res = await upload(`/llm/tai-len?ten=${encodeURIComponent(file.name)}`, file, {
          method: 'PUT',
          raw: true,
          onProgress: setPct,
        });
        return api('/llm/chon', { method: 'POST', body: { duong_dan: res.duong_dan } });
      } finally {
        setPct(null);
      }
    });

  if (!st) return <div className="p-6 text-sm text-gray-500">{error || 'Đang tải…'}</div>;

  const tooBig = (gb) => gb > st.ram_gb * 0.7;

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-xl font-semibold">Model AI</h1>

      {/* đang dùng */}
      <div className="card flex items-center gap-4 p-4">
        <Bot size={28} className="text-violet-700" />
        <div className="min-w-0 flex-1">
          <div className="text-xs text-gray-500">Đang dùng</div>
          <div className="truncate font-medium">{st.dang_dung || 'Chưa có model'}</div>
          <div className="truncate text-xs text-gray-400">{st.duong_dan}</div>
        </div>
        {st.dang_nap ? (
          <span className="badge bg-blue-50 text-blue-700">
            <Loader2 size={12} className="mr-1 animate-spin" /> Đang nạp thử…
          </span>
        ) : st.dang_chay ? (
          <span className="badge bg-green-50 text-green-700">
            <CheckCircle2 size={12} className="mr-1" /> Đang chạy
          </span>
        ) : (
          <span className="badge bg-gray-100 text-gray-600">Chưa nạp (sẽ nạp khi xử lý)</span>
        )}
        <button
          className="btn btn-light"
          disabled={st.dang_nap || st.dang_dung === st.mac_dinh}
          onClick={() => run(() => api('/llm/mac-dinh', { method: 'POST' }))}
          title={`Dùng lại model mặc định ${st.mac_dinh}`}
        >
          <RotateCcw size={14} /> Về mặc định
        </button>
      </div>

      {(error || st.loi) && (
        <div className="card flex gap-2 border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" /> {error || st.loi}
        </div>
      )}

      {/* danh sách */}
      <div className="card overflow-hidden">
        <div className="border-b px-4 py-2.5 text-sm font-semibold">Các model trên máy</div>
        <table className="w-full text-sm">
          <tbody>
            {st.danh_sach.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-center text-gray-500">Chưa có model nào. Tải lên hoặc chọn file có sẵn ở dưới.</td>
              </tr>
            )}
            {st.danh_sach.map((m) => (
              <tr key={m.duong_dan} className="border-t border-gray-100">
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2 font-medium">
                    {m.ten}
                    {m.mac_dinh && <span className="badge bg-blue-50 text-blue-700">Mặc định</span>}
                    {m.dang_dung && <span className="badge bg-green-50 text-green-700">Đang dùng</span>}
                  </div>
                  <div className="truncate text-xs text-gray-400">{m.duong_dan}</div>
                </td>
                <td className="whitespace-nowrap px-4 py-2.5 text-right">
                  {m.dung_luong_gb} GB
                  {tooBig(m.dung_luong_gb) && (
                    <div className="text-xs text-amber-700">Có thể thiếu RAM (máy {st.ram_gb} GB)</div>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-2.5 text-right">
                  {!m.dang_dung && (
                    <button className="btn btn-light" disabled={st.dang_nap} onClick={() => chooseModel(m.duong_dan)}>
                      Dùng model này
                    </button>
                  )}
                  {m.trong_thu_muc_app && !m.dang_dung && (
                    <button
                      className="btn btn-danger ml-1"
                      disabled={st.dang_nap}
                      onClick={() =>
                        confirm(`Xóa file ${m.ten} khỏi máy?`) &&
                        run(() => api(`/llm?duong_dan=${encodeURIComponent(m.duong_dan)}`, { method: 'DELETE' }))
                      }
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* thêm model */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="card space-y-2 p-4">
          <div className="flex items-center gap-2 font-semibold">
            <FolderSearch size={16} /> Dùng file có sẵn trên máy
          </div>
          <p className="text-xs text-gray-500">
            Không sao chép, không tốn thêm ổ cứng. Dán đường dẫn đầy đủ tới file <code>.gguf</code> (vd. model đã tải bằng LM
            Studio).
          </p>
          <input
            className="input"
            placeholder="C:\Users\...\model.gguf"
            value={path}
            onChange={(e) => setPath(e.target.value)}
          />
          <button className="btn btn-primary" disabled={!path.trim() || st.dang_nap} onClick={() => chooseModel(path.trim())}>
            Dùng file này
          </button>
        </div>
        <div className="card space-y-2 p-4">
          <div className="flex items-center gap-2 font-semibold">
            <Upload size={16} /> Tải file model lên
          </div>
          <p className="text-xs text-gray-500">
            Sao chép file <code>.gguf</code> (vd. từ USB) vào thư mục của app: <span className="break-all">{st.thu_muc}</span>.
            File lớn (10–20 GB) có thể mất vài phút.
          </p>
          <input ref={fileInput} type="file" accept=".gguf" hidden onChange={(e) => onUpload(e.target.files[0])} />
          {pct !== null ? (
            <div>
              <div className="mb-1 text-sm">Đang tải lên… {Math.round(pct * 100)}%</div>
              <div className="h-2 overflow-hidden rounded bg-gray-100">
                <div className="h-full bg-blue-600" style={{ width: `${pct * 100}%` }} />
              </div>
            </div>
          ) : (
            <button className="btn btn-light" disabled={st.dang_nap} onClick={() => fileInput.current.click()}>
              <Upload size={14} /> Chọn file .gguf
            </button>
          )}
        </div>
      </div>

      <p className="text-xs text-gray-500">
        Khi đổi model, app nạp thử ngay. Nếu model không chạy được (file hỏng, thiếu RAM…), app tự quay về model cũ và báo
        lỗi ở trên. Model nên là bản Q4 (GGUF), hỗ trợ tiếng Việt, dung lượng không quá ~70% RAM của máy.
      </p>
    </div>
  );
}
