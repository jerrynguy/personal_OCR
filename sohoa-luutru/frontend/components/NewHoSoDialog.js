'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown, FileText, Loader2, X } from 'lucide-react';
import { api, upload } from '@/lib/api';
import { HO_SO_MAIN, PHONG_MAIN, loadLast, maFromFileName, saveLast, splitFields } from '@/lib/fields';
import FieldForm from '@/components/FieldForm';

/**
 * Tạo hồ sơ từ một file PDF: chỉ hỏi Mã hồ sơ (+ tiêu đề nếu muốn). Thông tin khác thu gọn,
 * nhớ giá trị lần trước. Bấm "Tạo và xử lý" -> tạo hồ sơ, tải PDF lên, bắt đầu xử lý.
 */
export default function NewHoSoDialog({ file, onClose }) {
  const router = useRouter();
  const [schema, setSchema] = useState(null);
  const [hoSo, setHoSo] = useState({});
  const [phong, setPhong] = useState({});
  const [more, setMore] = useState(false);
  const [error, setError] = useState('');
  const [pct, setPct] = useState(null);

  useEffect(() => {
    api('/schema')
      .then((s) => {
        setSchema(s);
        const last = loadLast();
        const init = (fs, prev) => Object.fromEntries(fs.map((f) => [f.key, prev?.[f.key] || f.mac_dinh || '']));
        setPhong(init(s.phong, last.phong));
        setHoSo({ ...init(s.ho_so, last.ho_so), ma_ho_so: maFromFileName(file.name), tieu_de_ho_so: '' });
      })
      .catch((e) => setError(e.message));
  }, [file]);

  const submit = async () => {
    if (!hoSo.ma_ho_so?.trim()) return setError('Cần nhập Mã hồ sơ');
    setError('');
    setPct(0);
    let id = null;
    try {
      const created = await api('/ho-so', { method: 'POST', body: { phong, ho_so: hoSo } });
      id = created.id;
      const { ma_ho_so, tieu_de_ho_so, ...keep } = hoSo; // nhớ cho lần sau (trừ mã + tiêu đề)
      saveLast({ phong, ho_so: keep });
      await upload(`/ho-so/${id}/pdf`, file, { onProgress: setPct });
      await api(`/ho-so/${id}/xu-ly`, { method: 'POST', body: {} });
      router.push(`/ho-so/?id=${id}`);
    } catch (e) {
      setError(e.message + (id ? ' — hồ sơ đã được tạo, mở hồ sơ để tải PDF lại.' : ''));
      setPct(null);
    }
  };

  const manual = (fs) => fs.filter((f) => f.nguon === 'nhap_tay');
  const [hoSoMain, hoSoRest] = schema ? splitFields(manual(schema.ho_so), HO_SO_MAIN) : [[], []];
  const [phongMain, phongRest] = schema ? splitFields(manual(schema.phong), PHONG_MAIN) : [[], []];
  const busy = pct !== null;

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-6">
      <div className="card w-full max-w-xl">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h2 className="font-semibold">Tạo hồ sơ</h2>
          <button onClick={onClose} disabled={busy} className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>
        <div className="space-y-4 p-5">
          <div className="flex items-center gap-2 rounded-md bg-gray-50 p-2.5 text-sm">
            <FileText size={16} className="text-blue-700" />
            <span className="truncate font-medium">{file.name}</span>
            <span className="ml-auto shrink-0 text-gray-500">{(file.size / 1048576).toFixed(1)} MB</span>
          </div>
          {!schema ? (
            <div className="text-sm text-gray-500">Đang tải…</div>
          ) : (
            <>
              <FieldForm
                cols={1}
                fields={hoSoMain.filter((f) => ['ma_ho_so', 'tieu_de_ho_so'].includes(f.key))}
                values={hoSo}
                readOnly={busy}
                onChange={(k, v) => setHoSo((s) => ({ ...s, [k]: v }))}
              />
              <p className="-mt-2 text-xs text-gray-500">
                Tiêu đề có thể để trống và điền sau. Các thông tin khác (thời gian, số tờ, từ khóa...) app tự tính.
              </p>
              <button className="flex items-center gap-1 text-sm text-blue-700" onClick={() => setMore(!more)}>
                <ChevronDown size={15} className={more ? 'rotate-180' : ''} /> Thông tin khác (không bắt buộc, nhớ theo lần
                trước)
              </button>
              {more && (
                <div className="space-y-4 rounded-md border border-gray-200 p-3">
                  <FieldForm
                    fields={[...hoSoMain.filter((f) => !['ma_ho_so', 'tieu_de_ho_so'].includes(f.key)), ...phongMain]}
                    values={{ ...hoSo, ...phong }}
                    readOnly={busy}
                    onChange={(k, v) =>
                      PHONG_MAIN.includes(k) ? setPhong((s) => ({ ...s, [k]: v })) : setHoSo((s) => ({ ...s, [k]: v }))
                    }
                  />
                  <details className="text-sm">
                    <summary className="cursor-pointer text-gray-600">Các trường còn lại của hồ sơ và phông</summary>
                    <div className="mt-3 space-y-4">
                      <FieldForm fields={hoSoRest} values={hoSo} readOnly={busy} onChange={(k, v) => setHoSo((s) => ({ ...s, [k]: v }))} />
                      <FieldForm fields={phongRest} values={phong} readOnly={busy} onChange={(k, v) => setPhong((s) => ({ ...s, [k]: v }))} />
                    </div>
                  </details>
                </div>
              )}
            </>
          )}
          {busy && (
            <div className="text-sm">
              <div className="mb-1">Đang tải PDF lên… {Math.round(pct * 100)}%</div>
              <div className="h-2 overflow-hidden rounded bg-gray-100">
                <div className="h-full bg-blue-600" style={{ width: `${pct * 100}%` }} />
              </div>
            </div>
          )}
          {error && <div className="rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</div>}
        </div>
        <div className="flex justify-end gap-2 border-t px-5 py-3">
          <button className="btn btn-light" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy || !schema}>
            {busy && <Loader2 size={14} className="animate-spin" />} Tạo và xử lý
          </button>
        </div>
      </div>
    </div>
  );
}
