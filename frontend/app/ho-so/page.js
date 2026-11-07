'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AlertTriangle, ArrowRight, Bot, CheckCircle2, Clock, Download, FileUp, FolderOpen, Keyboard, Loader2, Pause, Play,
  RotateCcw, Save, Scissors, Sparkles, Trash2, X,
} from 'lucide-react';
import { api, fileUrl, fmtDuration, fmtSeconds, upload } from '@/lib/api';
import { STATUS } from '@/lib/constants';
import DropZone from '@/components/DropZone';
import FieldForm from '@/components/FieldForm';
import PageViewer from '@/components/PageViewer';
import { DOC_MAIN, HO_SO_MAIN, PHONG_MAIN, splitFields } from '@/lib/fields';

const READONLY_DOC = new Set(['stt', 'trang_pdf', 'diem_ocr', 'can_kiem_tra']);

function pageRange(trang) {
  const [a, b] = String(trang).split('-').map(Number);
  return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i);
}

export default function HoSoPage() {
  const router = useRouter();
  const [id, setId] = useState(null);
  const [info, setInfo] = useState(null);
  const [schema, setSchema] = useState(null);
  const [tab, setTab] = useState('soat');
  const [error, setError] = useState('');
  const [uploadPct, setUploadPct] = useState(null);
  const [warning, setWarning] = useState('');
  const fileInput = useRef(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setId(q.get('id'));
    if (q.get('tab')) setTab(q.get('tab'));
    api('/schema').then(setSchema).catch((e) => setError(e.message));
  }, []);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setInfo(await api(`/ho-so/${id}`));
    } catch (e) {
      setError(e.message);
    }
  }, [id]);

  const prog = info?.tien_do;
  // Đang CHẠY thì khóa sửa; đang CHỜ trong hàng đợi thì vẫn sửa được (lúc chạy app đọc thông tin mới nhất).
  const waiting = prog?.stage === 'cho';
  const busy = info?.trang_thai === 'dang_xu_ly' || (prog && !prog.done && !waiting);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!busy && !waiting) return undefined;
    const t = setInterval(load, busy ? 1500 : 3000);
    return () => clearInterval(t);
  }, [busy, waiting, load]);

  const run = async (fn) => {
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    }
    load();
  };

  const onPickPdf = (file) =>
    run(async () => {
      if (!file) return;
      setUploadPct(0);
      try {
        const res = await upload(`/ho-so/${id}/pdf`, file, { onProgress: setUploadPct });
        setWarning(res?.canh_bao || '');
        setTab('tach'); // tải xong -> người dùng tự đánh dấu từng tài liệu rồi mới xử lý
      } finally {
        setUploadPct(null);
      }
    });

  const startProcess = (params = {}) => run(() => api(`/ho-so/${id}/xu-ly`, { method: 'POST', body: params }));

  if (!id || !info || !schema) {
    return <div className="p-6 text-sm text-gray-500">{error || 'Đang tải…'}</div>;
  }

  const [stLabel, stCls] = STATUS[info.trang_thai] || [info.trang_thai, ''];
  const hs = info.ho_so;

  return (
    <div className="space-y-3">
      {/* ------------------------------------------------ đầu trang */}
      <div className="card flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-lg font-semibold text-blue-900">{hs.ma_ho_so}</h1>
            <span className={`badge ${stCls}`}>{stLabel}</span>
          </div>
          <p className="truncate text-sm text-gray-600">{hs.tieu_de_ho_so || 'Chưa có tiêu đề hồ sơ'}</p>
          <p className="truncate text-xs text-gray-400">
            {info.tu_thu_muc ? (
              <span title={info.thu_muc}>
                <FolderOpen size={12} className="mr-1 inline" />
                {info.thu_muc} · {info.nguon_pdf.length} file PDF · {info.so_trang} trang · {info.tai_lieu.length} tài liệu
                {info.lo && ` · lô ${info.lo}`}
              </span>
            ) : info.co_pdf ? (
              `${hs.tep_tin_ho_so || info.ten_pdf} · ${info.so_trang} trang · ${info.tai_lieu.length} tài liệu`
            ) : (
              'Chưa có file PDF'
            )}
          </p>
        </div>
        <input ref={fileInput} type="file" accept="application/pdf" hidden onChange={(e) => onPickPdf(e.target.files[0])} />
        {!info.tu_thu_muc && (
          <button className="btn btn-light" disabled={busy || uploadPct !== null} onClick={() => fileInput.current.click()}>
            <FileUp size={15} /> {info.co_pdf ? 'Đổi PDF' : 'Tải PDF lên'}
          </button>
        )}
        {info.co_pdf && (info.tai_lieu.length > 0 || info.trang_thai === 'loi') && (
          <button className="btn btn-primary" disabled={busy || waiting} onClick={() => startProcess()} title="Xử lý lại, giữ cách tách tài liệu hiện tại">
            <Play size={15} /> Xử lý lại
          </button>
        )}
        {info.tai_lieu.length > 0 && (
          <div className="flex gap-1">
            {[
              ['xlsx', 'Excel'],
              ['csv', 'CSV'],
              ['pdf', 'PDF từng tài liệu'],
            ].map(([k, label]) => (
              <a key={k} className={`btn btn-light ${busy ? 'pointer-events-none opacity-50' : ''}`} href={fileUrl(`/ho-so/${id}/xuat/${k}`)}>
                <Download size={15} /> {label}
              </a>
            ))}
          </div>
        )}
        <button
          className="btn btn-danger"
          disabled={busy}
          onClick={() =>
            confirm(`Xóa hồ sơ ${hs.ma_ho_so} và toàn bộ dữ liệu của nó?`) &&
            run(async () => {
              await api(`/ho-so/${id}`, { method: 'DELETE' });
              router.push('/');
            })
          }
        >
          <Trash2 size={15} />
        </button>
      </div>

      {error && <Alert kind="error" onClose={() => setError('')}>{error}</Alert>}
      {warning && <Alert kind="warn" onClose={() => setWarning('')}>{warning}</Alert>}
      {info.file_thieu?.length > 0 && (
        <Alert kind="error">
          Không thấy {info.file_thieu.length} file gốc trong thư mục: {info.file_thieu.slice(0, 5).join(', ')}
          {info.file_thieu.length > 5 && '…'}. File đã bị di chuyển, đổi tên hoặc xóa? Trang chưa đọc chữ của các file này sẽ
          không xử lý được — hãy để file về đúng chỗ.
        </Alert>
      )}
      {info.loi && !busy && !waiting && <Alert kind="warn">{info.loi}</Alert>}
      {uploadPct !== null && <Bar label="Đang tải PDF lên" value={uploadPct} />}
      {waiting && (
        <div className="card flex flex-wrap items-center gap-2 p-3 text-sm">
          {info.hang_doi_tam_dung ? <Pause size={15} className="text-amber-700" /> : <Clock size={15} className="text-blue-700" />}
          <span className="flex-1">
            <b>Đang chờ trong hàng đợi</b> — {prog.message}. Vẫn xem và sửa được trong lúc chờ.
          </span>
          {info.hang_doi_tam_dung && (
            <button className="btn btn-primary" onClick={() => run(() => api('/hang-doi/tiep-tuc', { method: 'POST' }))}>
              <Play size={14} /> Chạy tiếp hàng đợi
            </button>
          )}
          <button className="btn btn-light" onClick={() => run(() => api(`/ho-so/${id}/huy`, { method: 'POST' }))}>
            <X size={14} /> Bỏ khỏi hàng đợi
          </button>
        </div>
      )}
      {prog && !waiting && (busy || prog.stage === 'loi') && (
        <Progress prog={prog} onCancel={() => run(() => api(`/ho-so/${id}/huy`, { method: 'POST' }))} />
      )}

      {!info.co_pdf ? (
        <DropZone onFile={onPickPdf} />
      ) : (
        <>
          <div className="flex gap-1 border-b">
            {[
              ['soat', `Soát tài liệu (${info.tai_lieu.length})`],
              ['thong-tin', 'Thông tin hồ sơ'],
              ['tach', 'Tách văn bản'],
            ].map(([k, label]) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                className={`-mb-px border-b-2 px-4 py-2 text-sm ${
                  tab === k ? 'border-blue-700 font-medium text-blue-800' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === 'soat' && <ReviewTab id={id} info={info} schema={schema} busy={busy} onChanged={load} />}
          {tab === 'thong-tin' && <InfoTab id={id} info={info} schema={schema} busy={busy} onChanged={load} />}
          {tab === 'tach' && (
            <SplitTab
              id={id}
              info={info}
              busy={busy}
              waiting={waiting}
              prog={prog}
              onReadText={() => run(() => api(`/ho-so/${id}/doc-chu`, { method: 'POST' }))}
              onProcess={(p) => {
                setTab('soat');
                startProcess(p);
              }}
            />
          )}
        </>
      )}
    </div>
  );
}

/* ================================================================== soát tài liệu */
function ReviewTab({ id, info, schema, busy, onChanged }) {
  const docs = info.tai_lieu;
  const [stt, setStt] = useState(docs[0]?.stt ?? null);
  const [draft, setDraft] = useState(null);
  const [focusKey, setFocusKey] = useState('');
  const [onlyWarn, setOnlyWarn] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const doc = docs.find((d) => d.stt === stt) || docs[0];
  useEffect(() => {
    if (doc && stt == null) setStt(doc.stt);
  }, [doc, stt]);
  // Đổi văn bản, hoặc dữ liệu văn bản thay đổi từ backend (AI vừa điền xong) -> nạp lại bản nháp
  const docKey = doc ? JSON.stringify(doc) : '';
  useEffect(() => {
    setDraft(doc ? { ...doc } : null);
    setError('');
  }, [docKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const fields = useMemo(() => [...schema.tai_lieu, ...schema.bo_sung], [schema]);
  const [mainFields, restFields] = useMemo(
    () => splitFields(fields.filter((f) => f.key !== 'can_kiem_tra'), DOC_MAIN),
    [fields],
  );
  const changed = draft && doc ? fields.map((f) => f.key).filter((k) => (draft[k] ?? '') !== (doc[k] ?? '')) : [];
  const shown = onlyWarn ? docs.filter((d) => d.can_kiem_tra && !d.da_soat) : docs;

  if (!docs.length) {
    return (
      <div className="card p-10 text-center text-sm text-gray-500">
        {busy
          ? 'Đang xử lý — kết quả sẽ hiện ở đây ngay khi đọc xong từng văn bản.'
          : info.trang_thai === 'cho'
            ? 'Đang chờ trong hàng đợi — kết quả sẽ hiện ở đây khi tới lượt hồ sơ này.'
            : 'Chưa xử lý. Sang tab “Tách văn bản” để đánh dấu từng tài liệu rồi bấm “Xử lý”.'}
      </div>
    );
  }

  const save = async (markReviewed, goNext) => {
    setSaving(true);
    setError('');
    try {
      const body = { thay_doi: Object.fromEntries(changed.map((k) => [k, draft[k]])) };
      if (markReviewed !== undefined) body.da_soat = markReviewed;
      await api(`/ho-so/${id}/tai-lieu/${doc.stt}`, { method: 'PUT', body });
      await onChanged();
      if (goNext) {
        const i = shown.findIndex((d) => d.stt === doc.stt);
        const next = shown[i + 1] || shown.find((d) => !d.da_soat && d.stt !== doc.stt);
        if (next) setStt(next.stt);
      }
    } catch (e) {
      setError(e.message);
    }
    setSaving(false);
  };

  const aiPending = doc?.ai_trang_thai === 'cho';
  // AI chưa đọc xong -> chưa cảnh báo thiếu các trường do AI điền
  const warnings = (doc?.can_kiem_tra || '')
    .split(' | ')
    .filter((w) => w && !(aiPending && w.startsWith('Không có trích yếu')));

  return (
    <div className="grid gap-3 lg:grid-cols-[270px_minmax(0,1fr)_minmax(0,520px)]" style={{ height: 'calc(100vh - 250px)', minHeight: 560 }}>
      {/* danh sách văn bản */}
      <div className="card flex min-h-0 flex-col">
        <label className="flex items-center gap-2 border-b px-3 py-2 text-xs text-gray-600">
          <input type="checkbox" checked={onlyWarn} onChange={(e) => setOnlyWarn(e.target.checked)} />
          Chỉ hiện văn bản cần kiểm tra
        </label>
        <div className="flex-1 overflow-y-auto">
          {shown.map((d) => (
            <button
              key={d.stt}
              onClick={() => setStt(d.stt)}
              className={`block w-full border-b border-gray-100 px-3 py-2 text-left text-sm ${
                d.stt === doc?.stt ? 'bg-blue-50' : 'hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center gap-1.5">
                <span className="text-gray-400">{d.stt}.</span>
                <span className="truncate font-medium">{d.ten_loai_tai_lieu || 'Chưa rõ tên loại'}</span>
                <span className="ml-auto flex shrink-0 gap-1">
                  {d.ai_trang_thai === 'cho' && <Loader2 size={13} className="animate-spin text-violet-600" />}
                  {d.can_kiem_tra && !d.da_soat && d.ai_trang_thai !== 'cho' && <AlertTriangle size={13} className="text-amber-600" />}
                  {d.da_soat && <CheckCircle2 size={13} className="text-green-600" />}
                </span>
              </div>
              <div className="truncate text-xs text-gray-500">
                {[d.so_cua_tai_lieu && `${d.so_cua_tai_lieu}/${d.ky_hieu_cua_tai_lieu}`, d.ngay_ban_hanh, `tr. ${d.trang_pdf}`]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
              {info.tu_thu_muc && <div className="truncate text-[11px] text-gray-400">{d.tep_tin_tai_lieu}</div>}
            </button>
          ))}
        </div>
      </div>

      {/* ảnh trang */}
      <div className="card min-h-0 overflow-hidden">
        {doc && <PageViewer hoSoId={id} pages={pageRange(doc.trang_pdf)} highlight={draft?.[focusKey]} version={info.so_trang} />}
      </div>

      {/* các trường */}
      <div className="card flex min-h-0 flex-col">
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {aiPending && (
            <div className="flex items-center gap-2 rounded-md bg-violet-50 p-2 text-xs text-violet-800">
              <Bot size={14} /> AI đang đọc văn bản này (cơ quan, trích yếu, từ khóa, người ký) — các trường khác đã có.
            </div>
          )}
          {warnings.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
              <div className="mb-1 flex items-center gap-1 font-medium">
                <AlertTriangle size={13} /> Cần kiểm tra
              </div>
              <ul className="list-disc pl-4">
                {warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          {draft && (
            <>
              <FieldForm
                fields={mainFields}
                values={draft}
                sources={doc._nguon}
                readOnly={busy}
                readOnlyKeys={READONLY_DOC}
                onFocusField={setFocusKey}
                onChange={(k, v) => setDraft((d) => ({ ...d, [k]: v }))}
              />
              <details className="rounded-md border border-gray-200 p-3">
                <summary className="cursor-pointer text-sm text-gray-600">
                  Thông tin quản lý ({restFields.length} trường — đa số tự điền từ hồ sơ hoặc tự tính)
                </summary>
                <div className="mt-3">
                  <FieldForm
                    fields={restFields}
                    values={draft}
                    sources={doc._nguon}
                    readOnly={busy}
                    readOnlyKeys={READONLY_DOC}
                    onFocusField={setFocusKey}
                    onChange={(k, v) => setDraft((d) => ({ ...d, [k]: v }))}
                  />
                </div>
              </details>
            </>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t px-4 py-2.5">
          {error && <span className="w-full text-xs text-red-600">{error}</span>}
          {busy && <span className="w-full text-xs text-gray-500">Đang xử lý hồ sơ — chờ xong mới sửa được.</span>}
          <button className="btn btn-light" disabled={busy || saving || !changed.length} onClick={() => save()}>
            <Save size={14} /> Lưu {changed.length ? `(${changed.length})` : ''}
          </button>
          {doc?.da_soat ? (
            <button className="btn btn-light" disabled={busy || saving} onClick={() => save(false)}>
              <RotateCcw size={14} /> Bỏ đánh dấu đã soát
            </button>
          ) : (
            <button className="btn btn-primary ml-auto" disabled={busy || saving} onClick={() => save(true, true)}>
              {saving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} Đã soát, sang văn bản
              tiếp <ArrowRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ================================================================== thông tin hồ sơ */
function InfoTab({ id, info, schema, busy, onChanged }) {
  const [phong, setPhong] = useState(info.phong);
  const [hoSo, setHoSo] = useState(info.ho_so);
  const [msg, setMsg] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setPhong(info.phong);
    setHoSo(info.ho_so);
  }, [info.phong, info.ho_so]);

  const autoKeys = new Set(schema.ho_so.filter((f) => f.nguon !== 'nhap_tay').map((f) => f.key));
  const [hsMain, hsRest] = splitFields(schema.ho_so, HO_SO_MAIN);
  const hsAuto = hsRest.filter((f) => autoKeys.has(f.key));
  const hsOther = hsRest.filter((f) => !autoKeys.has(f.key));
  const [phMain, phOther] = splitFields(schema.phong, PHONG_MAIN);
  const save = async () => {
    setSaving(true);
    setMsg('');
    try {
      const manual = Object.fromEntries(Object.entries(hoSo).filter(([k]) => !autoKeys.has(k)));
      await api(`/ho-so/${id}`, { method: 'PUT', body: { phong, ho_so: manual } });
      setMsg('Đã lưu. Các trường kế thừa đã được cập nhật xuống tài liệu (trừ ô đã sửa tay).');
      onChanged();
    } catch (e) {
      setMsg(e.message);
    }
    setSaving(false);
  };

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div className="card space-y-4 p-4">
        <h3 className="font-semibold">Hồ sơ</h3>
        <FieldForm fields={hsMain} values={hoSo} readOnly={busy} onChange={(k, v) => setHoSo((s) => ({ ...s, [k]: v }))} />
        <div className="rounded-md bg-gray-50 p-3">
          <div className="mb-2 text-xs font-medium uppercase text-gray-500">App tự tính</div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            {hsAuto.map((f) => (
              <div key={f.key} className="contents">
                <dt className="text-gray-500">{f.label}</dt>
                <dd className="break-words">{String(hoSo[f.key] ?? '') || '—'}</dd>
              </div>
            ))}
          </dl>
        </div>
        <details className="rounded-md border border-gray-200 p-3">
          <summary className="cursor-pointer text-sm text-gray-600">Các trường khác của hồ sơ ({hsOther.length})</summary>
          <div className="mt-3">
            <FieldForm fields={hsOther} values={hoSo} readOnly={busy} onChange={(k, v) => setHoSo((s) => ({ ...s, [k]: v }))} />
          </div>
        </details>
      </div>
      <div className="space-y-3">
        <div className="card space-y-4 p-4">
          <h3 className="font-semibold">Phông lưu trữ</h3>
          <FieldForm fields={phMain} values={phong} readOnly={busy} onChange={(k, v) => setPhong((s) => ({ ...s, [k]: v }))} />
          <details className="rounded-md border border-gray-200 p-3">
            <summary className="cursor-pointer text-sm text-gray-600">Các trường khác của phông ({phOther.length})</summary>
            <div className="mt-3">
              <FieldForm fields={phOther} values={phong} readOnly={busy} onChange={(k, v) => setPhong((s) => ({ ...s, [k]: v }))} />
            </div>
          </details>
        </div>
        <div className="flex items-center gap-3">
          <button className="btn btn-primary" disabled={busy || saving} onClick={save}>
            <Save size={14} /> Lưu thông tin
          </button>
          {msg && <span className="text-sm text-gray-600">{msg}</span>}
        </div>
      </div>
    </div>
  );
}

/* ================================================================== tách văn bản */
const SIZES = {
  nho: ['Nhỏ', 'grid-cols-6 sm:grid-cols-8 lg:grid-cols-12'],
  vua: ['Vừa', 'grid-cols-3 sm:grid-cols-5 lg:grid-cols-8'],
  lon: ['Lớn', 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4'],
};

/**
 * Người dùng tự tách tài liệu: bấm trang đầu của từng tài liệu. App KHÔNG tự tách; chỉ GỢI Ý (viền cam nét đứt)
 * trang có quốc hiệu / dòng "Số:" để bấm xác nhận nhanh — cần đọc chữ trước (hoặc PDF có sẵn lớp chữ).
 * Phím tắt cho file dài: ← → ↑ ↓ di chuyển, Space / Enter đánh dấu, N tới gợi ý kế tiếp chưa đánh dấu.
 */
function SplitTab({ id, info, busy, waiting, prog, onReadText, onProcess }) {
  const firstTime = info.tai_lieu.length === 0;
  const fileStarts = useMemo(() => info.nguon_pdf.map((f) => f.trang_dau), [info.nguon_pdf]);
  const fileAt = useMemo(() => Object.fromEntries(info.nguon_pdf.map((f) => [f.trang_dau, f.ten])), [info.nguon_pdf]);
  // Chưa xử lý: mỗi file 1 tài liệu (PDF tải lên: cả file là 1 tài liệu)
  const current = useMemo(
    () => new Set(info.tai_lieu.length ? info.tai_lieu.map((d) => pageRange(d.trang_pdf)[0]) : fileStarts.length ? fileStarts : [1]),
    [info.tai_lieu, fileStarts],
  );
  const [starts, setStarts] = useState(current);
  useEffect(() => setStarts(current), [current]);
  const [size, setSize] = useState('vua');
  const [cursor, setCursor] = useState(1);
  const [hint, setHint] = useState(null); // {goi_y, da_doc, tong}
  const grid = useRef(null);

  useEffect(() => {
    try {
      const v = localStorage.getItem('sohoa_co_anh');
      if (v && SIZES[v]) setSize(v);
    } catch {}
  }, []);
  const pickSize = (k) => {
    setSize(k);
    try {
      localStorage.setItem('sohoa_co_anh', k);
    } catch {}
  };

  // gợi ý: hỏi lại khi đọc chữ xong / đang đọc
  const reading = prog && !prog.done && prog.kind === 'ocr';
  const ocrTick = reading ? Math.floor(prog.current / 10) : 0;
  useEffect(() => {
    let stop = false;
    api(`/ho-so/${id}/goi-y`)
      .then((g) => !stop && setHint(g))
      .catch(() => {});
    return () => {
      stop = true;
    };
  }, [id, info.trang_thai, ocrTick]);
  const suggested = useMemo(() => new Set(hint?.goi_y || []), [hint]);
  const pending = (hint?.goi_y || []).filter((n) => !starts.has(n));

  const toggle = useCallback(
    (n) =>
      n !== 1 &&
      setStarts((s) => {
        const next = new Set(s);
        next.has(n) ? next.delete(n) : next.add(n);
        return next;
      }),
    [],
  );
  const changed = [...starts].sort().join() !== [...current].sort().join();
  const total = info.so_trang;
  const pages = useMemo(() => Array.from({ length: total }, (_, i) => i + 1), [total]);

  // phím tắt
  useEffect(() => {
    const onKey = (e) => {
      if (busy || e.target.closest?.('input, textarea, select') || e.ctrlKey || e.metaKey || e.altKey) return;
      const cols = grid.current ? getComputedStyle(grid.current).gridTemplateColumns.split(' ').length : 1;
      const move = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -cols, ArrowDown: cols }[e.key];
      let next = null;
      if (move) next = Math.min(total, Math.max(1, cursor + move));
      else if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        toggle(cursor);
        return;
      } else if (e.key === 'n' || e.key === 'N') {
        next = pending.find((n) => n > cursor) ?? pending[0] ?? null;
      } else return;
      e.preventDefault();
      if (next) {
        setCursor(next);
        document.getElementById(`trang-${next}`)?.scrollIntoView({ block: 'nearest' });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, cursor, total, pending, toggle]);

  const readMinutes = Math.max(1, Math.round(((total - (hint?.da_doc || 0)) * 5) / 60));
  // Chỉ mời "đọc chữ để gợi ý" khi có file dài (file ngắn: tự bấm còn nhanh hơn chờ)
  const longFile = info.nguon_pdf.some((f) => f.so_trang >= 6);
  const offerRead = longFile && hint && hint.da_doc < total && !reading && !busy && !waiting;
  const showHint = hint && (offerRead || reading || hint.goi_y.length > 0);
  let docNo = 0;
  return (
    <div className="space-y-3">
      {firstTime && !busy && (
        <div className="card border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
          <b>Tách tài liệu:</b> bấm vào <b>trang đầu của từng tài liệu</b> (viền xanh). Các trang sau nó, đến trang đầu kế
          tiếp, thuộc cùng tài liệu.
          {info.nguon_pdf.length > 1 && <> Mặc định: <b>mỗi file PDF là 1 tài liệu</b>.</>} Xong bấm <b>Xử lý</b>.
        </div>
      )}
      <div className="card flex flex-wrap items-center gap-2 p-3 text-sm">
        <Scissors size={16} className="text-gray-500" />
        <span className="text-gray-600">
          <b>{starts.size}</b> tài liệu · {total} trang
        </span>
        <button className="btn btn-light" disabled={busy} onClick={() => setStarts(new Set([1]))}>
          Cả file là 1 tài liệu
        </button>
        {info.nguon_pdf.length > 1 && (
          <button className="btn btn-light" disabled={busy} onClick={() => setStarts(new Set(fileStarts))}>
            Mỗi file 1 tài liệu
          </button>
        )}
        <button className="btn btn-light" disabled={busy} onClick={() => setStarts(new Set(pages))}>
          Mỗi trang 1 tài liệu
        </button>
        <div className="flex overflow-hidden rounded-md border border-gray-300">
          {Object.entries(SIZES).map(([k, [label]]) => (
            <button
              key={k}
              onClick={() => pickSize(k)}
              className={`px-2.5 py-1 text-xs ${size === k ? 'bg-blue-700 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}
              title="Cỡ ảnh trang"
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className="btn btn-primary ml-auto"
          disabled={busy || waiting || (!firstTime && !changed)}
          onClick={() => onProcess({ ranh_gioi: [...starts] })}
        >
          <Play size={14} /> {firstTime ? 'Xử lý' : 'Áp dụng và xử lý lại'}
        </button>
        {!firstTime && (
          <button
            className="btn btn-light"
            disabled={busy || waiting}
            onClick={() => confirm('OCR lại toàn bộ hồ sơ từ đầu?') && onProcess({ ocr_lai: true, ranh_gioi: [...starts] })}
          >
            <RotateCcw size={14} /> OCR lại từ đầu
          </button>
        )}
      </div>

      {/* gợi ý trang đầu (người dùng xác nhận) */}
      {showHint && (
        <div className="card flex flex-wrap items-center gap-2 border-orange-200 bg-orange-50/60 p-3 text-sm text-orange-950">
          <Sparkles size={16} className="text-orange-600" />
          {offerRead ? (
            <>
              <span className="flex-1">
                File dài? App có thể <b>gợi ý</b> trang nào có vẻ là trang đầu tài liệu (có quốc hiệu hoặc dòng “Số:”) để
                bạn bấm xác nhận — app không tự tách. Cần đọc chữ trước: khoảng <b>{fmtDuration(readMinutes * 60)}</b>
                {hint.da_doc > 0 && ` (đã đọc ${hint.da_doc}/${total} trang)`}; phần đã đọc được dùng lại khi xử lý.
              </span>
              <button className="btn btn-light" onClick={onReadText}>
                <Sparkles size={14} /> Đọc chữ để gợi ý
              </button>
            </>
          ) : reading || (waiting && prog?.kind === 'ocr') ? (
            <span className="flex-1">
              Đang đọc chữ để gợi ý… {hint.da_doc}/{total} trang. Gợi ý hiện dần; vẫn đánh dấu được trong lúc chờ.
            </span>
          ) : pending.length ? (
            <span className="flex-1">
              App gợi ý <b>{pending.length}</b> trang nữa có vẻ là trang đầu tài liệu (viền <b>cam nét đứt</b>)
              {hint.da_doc < total && ` — trong ${hint.da_doc}/${total} trang đã đọc chữ`}. Kiểm tra rồi bấm vào trang để
              xác nhận, hoặc đánh dấu hết một lần.
            </span>
          ) : (
            <span className="flex-1">
              Mọi trang app gợi ý ({hint.goi_y.length} trang có quốc hiệu / dòng “Số:”) đều đã là trang đầu tài liệu.
            </span>
          )}
          {pending.length > 0 && (
            <button
              className="btn btn-light"
              disabled={busy}
              onClick={() => setStarts((s) => new Set([...s, ...hint.goi_y]))}
              title="Đánh dấu mọi trang được gợi ý là trang đầu tài liệu (vẫn bỏ từng trang được)"
            >
              <CheckCircle2 size={14} /> Đánh dấu cả {pending.length} trang gợi ý
            </button>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 text-xs text-gray-500">
        <span className="inline-flex items-center gap-1">
          <Keyboard size={13} /> Phím tắt: ← → ↑ ↓ di chuyển · <b>Space</b>/<b>Enter</b> đánh dấu trang đầu · <b>N</b> tới gợi ý
          tiếp theo
        </span>
        {!firstTime && <span>· Xử lý lại vẫn giữ các ô đã sửa tay và dấu “đã soát” của tài liệu nào vẫn đúng các trang như cũ.</span>}
      </div>
      <div ref={grid} className={`grid gap-2 ${SIZES[size][1]}`}>
        {pages.map((n) => {
          const isStart = starts.has(n);
          if (isStart) docNo += 1;
          const sug = suggested.has(n) && !isStart;
          return (
            <button
              key={n}
              id={`trang-${n}`}
              onClick={() => {
                setCursor(n);
                toggle(n);
              }}
              disabled={busy}
              className={`card relative overflow-hidden text-left ${
                isStart ? 'ring-2 ring-blue-600' : sug ? 'outline-2 outline-dashed outline-orange-500' : ''
              } ${cursor === n ? 'shadow-[0_0_0_4px_rgba(17,24,39,0.35)]' : ''}`}
            >
              {fileAt[n] && info.nguon_pdf.length > 1 && (
                <div className="truncate bg-gray-700 px-1.5 py-0.5 text-[10px] text-white" title={fileAt[n]}>
                  {fileAt[n]}
                </div>
              )}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={fileUrl(`/ho-so/${id}/trang/${n}/anh?nho=1`)} alt={`Trang ${n}`} loading="lazy" className="aspect-[1/1.414] w-full bg-gray-100 object-contain" />
              {sug && <span className="badge absolute right-1 top-6 bg-orange-500 text-white">Gợi ý</span>}
              <div
                className={`flex items-center justify-between gap-1 px-1.5 py-1 text-xs ${
                  isStart ? 'bg-blue-600 text-white' : 'text-gray-600'
                }`}
              >
                <span>{size === 'nho' ? n : `Trang ${n}`}</span>
                {isStart && <span className="truncate">{size === 'nho' ? `TL ${docNo}` : `Tài liệu ${docNo}`}</span>}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ================================================================== thành phần nhỏ */
function Progress({ prog, onCancel }) {
  const pct = prog.total ? prog.current / prog.total : null;
  return (
    <div className="card p-3">
      <div className="mb-1.5 flex items-center gap-2 text-sm">
        {prog.stage === 'loi' ? (
          <AlertTriangle size={15} className="text-red-600" />
        ) : (
          <Loader2 size={15} className="animate-spin text-blue-700" />
        )}
        <b>{prog.stage_label}</b>
        {prog.total > 0 && (
          <span className="text-gray-600">
            {prog.current}/{prog.total}
          </span>
        )}
        {prog.message && <span className="truncate text-gray-500">— {prog.message}</span>}
        <span className="ml-auto text-xs text-gray-500">
          {fmtSeconds(prog.elapsed)}
          {prog.eta_stage ? ` · còn ~${fmtSeconds(prog.eta_stage)}` : ''}
        </span>
        {prog.stage !== 'loi' && (
          <button className="btn btn-light py-1" onClick={onCancel}>
            <X size={13} /> Hủy
          </button>
        )}
      </div>
      {prog.stage === 'loi' ? (
        <p className="text-sm text-red-700">{prog.error}</p>
      ) : (
        <div className="h-2 overflow-hidden rounded bg-gray-100">
          <div
            className={`h-full bg-blue-600 transition-all ${pct === null ? 'w-1/3 animate-pulse' : ''}`}
            style={pct !== null ? { width: `${Math.max(3, pct * 100)}%` } : undefined}
          />
        </div>
      )}
    </div>
  );
}

function Bar({ label, value }) {
  return (
    <div className="card p-3 text-sm">
      <div className="mb-1">
        {label}… {Math.round(value * 100)}%
      </div>
      <div className="h-2 overflow-hidden rounded bg-gray-100">
        <div className="h-full bg-blue-600" style={{ width: `${value * 100}%` }} />
      </div>
    </div>
  );
}

function Alert({ kind, children, onClose }) {
  const cls = kind === 'error' ? 'border-red-200 bg-red-50 text-red-700' : 'border-amber-200 bg-amber-50 text-amber-900';
  return (
    <div className={`card flex items-start gap-2 p-3 text-sm ${cls}`}>
      <AlertTriangle size={15} className="mt-0.5 shrink-0" />
      <div className="flex-1">{children}</div>
      {onClose && (
        <button onClick={onClose} className="opacity-60 hover:opacity-100">
          <X size={14} />
        </button>
      )}
    </div>
  );
}
