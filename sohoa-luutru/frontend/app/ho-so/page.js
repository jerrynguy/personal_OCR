'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AlertTriangle, ArrowRight, Bot, CheckCircle2, Download, FileUp, Loader2, Play, RotateCcw, Save, Scissors,
  Trash2, X,
} from 'lucide-react';
import { api, fileUrl, fmtSeconds, upload } from '@/lib/api';
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
    setId(new URLSearchParams(window.location.search).get('id'));
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
  const busy = ['cho', 'dang_xu_ly'].includes(info?.trang_thai) || (prog && !prog.done);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!busy) return undefined;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [busy, load]);

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
        await api(`/ho-so/${id}/xu-ly`, { method: 'POST', body: {} }); // tải xong là xử lý luôn
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
          <p className="text-xs text-gray-400">
            {info.co_pdf
              ? `${hs.tep_tin_ho_so || info.ten_pdf} · ${info.so_trang} trang · ${info.tai_lieu.length} tài liệu`
              : 'Chưa có file PDF'}
          </p>
        </div>
        <input ref={fileInput} type="file" accept="application/pdf" hidden onChange={(e) => onPickPdf(e.target.files[0])} />
        <button className="btn btn-light" disabled={busy || uploadPct !== null} onClick={() => fileInput.current.click()}>
          <FileUp size={15} /> {info.co_pdf ? 'Đổi PDF' : 'Tải PDF lên'}
        </button>
        {info.co_pdf && (
          <button className="btn btn-primary" disabled={busy} onClick={() => startProcess()}>
            <Play size={15} /> {info.tai_lieu.length ? 'Xử lý lại' : 'Xử lý'}
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
      {info.loi && !busy && <Alert kind="warn">{info.loi}</Alert>}
      {uploadPct !== null && <Bar label="Đang tải PDF lên" value={uploadPct} />}
      {prog && (busy || prog.stage === 'loi') && (
        <Progress prog={prog} onCancel={() => run(() => api(`/xu-ly/${prog.id}/huy`, { method: 'POST' }))} />
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
          {tab === 'tach' && <SplitTab id={id} info={info} busy={busy} onProcess={startProcess} />}
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
        {busy ? 'Đang xử lý — kết quả sẽ hiện ở đây ngay khi đọc xong từng văn bản.' : 'Chưa có tài liệu. Bấm “Xử lý” để bắt đầu.'}
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
function SplitTab({ id, info, busy, onProcess }) {
  const current = useMemo(() => new Set(info.tai_lieu.map((d) => pageRange(d.trang_pdf)[0])), [info.tai_lieu]);
  const [starts, setStarts] = useState(current);
  useEffect(() => setStarts(current), [current]);

  const toggle = (n) =>
    n !== 1 &&
    setStarts((s) => {
      const next = new Set(s);
      next.has(n) ? next.delete(n) : next.add(n);
      return next;
    });
  const changed = [...starts].sort().join() !== [...current].sort().join();
  const pages = Array.from({ length: info.so_trang }, (_, i) => i + 1);

  let docNo = 0;
  return (
    <div className="space-y-3">
      <div className="card flex flex-wrap items-center gap-3 p-3 text-sm">
        <Scissors size={16} className="text-gray-500" />
        <span className="text-gray-600">
          Bấm vào trang để đánh dấu <b>trang đầu của một văn bản</b>. Các trang sau nó (đến trang đầu kế tiếp) thuộc cùng văn
          bản. Hiện có <b>{starts.size}</b> văn bản.
        </span>
        <button className="btn btn-primary ml-auto" disabled={busy || !changed} onClick={() => onProcess({ ranh_gioi: [...starts] })}>
          <Play size={14} /> Áp dụng và xử lý lại
        </button>
        <button
          className="btn btn-light"
          disabled={busy}
          onClick={() => confirm('OCR lại toàn bộ hồ sơ từ đầu?') && onProcess({ ocr_lai: true })}
        >
          <RotateCcw size={14} /> OCR lại từ đầu
        </button>
      </div>
      <p className="text-xs text-gray-500">
        Xử lý lại vẫn giữ các ô đã sửa tay và dấu “đã soát” của văn bản nào vẫn đúng các trang như cũ.
      </p>
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-8">
        {pages.map((n) => {
          const isStart = starts.has(n);
          if (isStart) docNo += 1;
          return (
            <button
              key={n}
              onClick={() => toggle(n)}
              disabled={busy}
              className={`card overflow-hidden text-left ${isStart ? 'ring-2 ring-blue-600' : ''}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={fileUrl(`/ho-so/${id}/trang/${n}/anh?nho=1`)} alt={`Trang ${n}`} loading="lazy" className="aspect-[1/1.414] w-full bg-gray-100 object-contain" />
              <div className={`flex items-center justify-between px-2 py-1 text-xs ${isStart ? 'bg-blue-600 text-white' : 'text-gray-600'}`}>
                <span>Trang {n}</span>
                {isStart && <span>Văn bản {docNo}</span>}
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
