'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, CheckCircle2, Loader2, Plus } from 'lucide-react';
import { api } from '@/lib/api';
import DropZone from '@/components/DropZone';
import NewHoSoDialog from '@/components/NewHoSoDialog';
import { STATUS } from '@/lib/constants';

export default function HomePage() {
  const router = useRouter();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [newFile, setNewFile] = useState(null); // PDF vừa chọn -> mở hộp thoại tạo hồ sơ
  const picker = useRef(null);

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
        <button className="btn btn-primary" onClick={() => picker.current.click()}>
          <Plus size={16} /> Tạo hồ sơ từ PDF
        </button>
        <input
          ref={picker}
          type="file"
          accept="application/pdf"
          hidden
          onChange={(e) => {
            if (e.target.files[0]) setNewFile(e.target.files[0]);
            e.target.value = '';
          }}
        />
      </div>

      <DropZone onFile={setNewFile} compact={rows?.length > 0} title="Kéo thả file PDF scan của hồ sơ vào đây để tạo hồ sơ mới" />

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
                  Chưa có hồ sơ nào. Kéo thả file PDF vào ô ở trên để bắt đầu.
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

      {newFile && <NewHoSoDialog file={newFile} onClose={() => setNewFile(null)} />}
    </div>
  );
}
