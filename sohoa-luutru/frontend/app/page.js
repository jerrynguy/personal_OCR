'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, CheckCircle2, Loader2, Plus, X } from 'lucide-react';
import { api } from '@/lib/api';
import FieldForm from '@/components/FieldForm';
import { STATUS } from '@/lib/constants';

export default function HomePage() {
  const router = useRouter();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await api('/ho-so'));
      setError('');
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Hồ sơ</h1>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          <Plus size={16} /> Tạo hồ sơ
        </button>
      </div>

      {error && <div className="card border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-2.5">Mã hồ sơ</th>
              <th className="px-4 py-2.5">Tiêu đề</th>
              <th className="px-4 py-2.5">Trạng thái</th>
              <th className="px-4 py-2.5 text-right">Trang</th>
              <th className="px-4 py-2.5 text-right">Tài liệu</th>
              <th className="px-4 py-2.5 text-right">Cần kiểm tra</th>
              <th className="px-4 py-2.5 text-right">Đã soát</th>
              <th className="px-4 py-2.5">Cập nhật</th>
            </tr>
          </thead>
          <tbody>
            {rows?.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-gray-500">
                  Chưa có hồ sơ nào. Bấm <b>Tạo hồ sơ</b> để bắt đầu.
                </td>
              </tr>
            )}
            {rows?.map((r) => {
              const [label, cls] = STATUS[r.trang_thai] || [r.trang_thai, 'bg-gray-100'];
              return (
                <tr
                  key={r.id}
                  className="cursor-pointer border-t border-gray-100 hover:bg-blue-50/40"
                  onClick={() => router.push(`/ho-so/?id=${r.id}`)}
                >
                  <td className="px-4 py-2.5 font-medium text-blue-800">{r.ma_ho_so}</td>
                  <td className="px-4 py-2.5">{r.tieu_de || <span className="text-gray-400">—</span>}</td>
                  <td className="px-4 py-2.5">
                    <span className={`badge ${cls}`}>
                      {(r.trang_thai === 'dang_xu_ly' || r.trang_thai === 'cho') && (
                        <Loader2 size={12} className="mr-1 animate-spin" />
                      )}
                      {label}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">{r.so_trang || '—'}</td>
                  <td className="px-4 py-2.5 text-right">{r.so_tai_lieu}</td>
                  <td className="px-4 py-2.5 text-right">
                    {r.can_kiem_tra ? (
                      <span className="inline-flex items-center gap-1 text-amber-700">
                        <AlertTriangle size={13} /> {r.can_kiem_tra}
                      </span>
                    ) : (
                      '0'
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {r.so_tai_lieu > 0 && r.da_soat === r.so_tai_lieu ? (
                      <span className="inline-flex items-center gap-1 text-green-700">
                        <CheckCircle2 size={13} /> {r.da_soat}
                      </span>
                    ) : (
                      `${r.da_soat}/${r.so_tai_lieu}`
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-gray-500">{r.cap_nhat?.replace('T', ' ')}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {creating && <CreateDialog onClose={() => setCreating(false)} onCreated={(id) => router.push(`/ho-so/?id=${id}`)} />}
    </div>
  );
}

function CreateDialog({ onClose, onCreated }) {
  const [schema, setSchema] = useState(null);
  const [phong, setPhong] = useState({});
  const [hoSo, setHoSo] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api('/schema').then((s) => {
      setSchema(s);
      const init = (fs) => Object.fromEntries(fs.map((f) => [f.key, f.mac_dinh || '']));
      setPhong(init(s.phong));
      setHoSo(init(s.ho_so));
    });
  }, []);

  const submit = async () => {
    if (!hoSo.ma_ho_so?.trim()) return setError('Cần nhập Mã hồ sơ');
    setSaving(true);
    try {
      const res = await api('/ho-so', { method: 'POST', body: { phong, ho_so: hoSo } });
      onCreated(res.id);
    } catch (e) {
      setError(e.message);
      setSaving(false);
    }
  };

  const manual = (fs) => fs.filter((f) => f.nguon === 'nhap_tay');

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-6">
      <div className="card w-full max-w-3xl">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h2 className="font-semibold">Tạo hồ sơ mới</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>
        {!schema ? (
          <div className="p-6 text-sm text-gray-500">Đang tải…</div>
        ) : (
          <div className="space-y-5 p-5">
            <section>
              <h3 className="mb-2 text-sm font-semibold text-gray-700">Hồ sơ</h3>
              <p className="mb-3 text-xs text-gray-500">
                Các giá trị như thời hạn lưu trữ, mức độ tiếp cận… sẽ tự áp xuống mọi tài liệu trong hồ sơ.
                Thời gian bắt đầu/kết thúc, số tờ, số trang, từ khóa sẽ tự tính sau khi xử lý.
              </p>
              <FieldForm
                fields={manual(schema.ho_so)}
                values={hoSo}
                onChange={(k, v) => setHoSo((s) => ({ ...s, [k]: v }))}
              />
            </section>
            <section>
              <h3 className="mb-2 text-sm font-semibold text-gray-700">Phông lưu trữ</h3>
              <FieldForm
                fields={manual(schema.phong)}
                values={phong}
                onChange={(k, v) => setPhong((s) => ({ ...s, [k]: v }))}
              />
            </section>
            {error && <div className="rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</div>}
          </div>
        )}
        <div className="flex justify-end gap-2 border-t px-5 py-3">
          <button className="btn btn-light" onClick={onClose}>
            Hủy
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={saving || !schema}>
            {saving && <Loader2 size={14} className="animate-spin" />} Tạo hồ sơ
          </button>
        </div>
      </div>
    </div>
  );
}
