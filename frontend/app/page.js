'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, Bot, CheckCircle2, Download, FolderInput, Loader2, Plus, Search, Trash2, X,
} from 'lucide-react';
import { api, download, qs } from '@/lib/api';
import DropZone from '@/components/DropZone';
import NewHoSoDialog from '@/components/NewHoSoDialog';
import QueuePanel from '@/components/QueuePanel';
import { STATUS, STATUS_FILTERS } from '@/lib/constants';

const PER_PAGE = 50;

export default function HomePage() {
  const router = useRouter();
  const [data, setData] = useState(null); // {tong, ho_so}
  const [lots, setLots] = useState([]);
  const [queue, setQueue] = useState(null);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [newFile, setNewFile] = useState(null); // PDF vừa chọn -> mở hộp thoại tạo hồ sơ
  const [filter, setFilter] = useState({ q: '', lo: '', trang_thai: '' });
  const [qInput, setQInput] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(new Set());
  const [ready, setReady] = useState(false);
  const [exporting, setExporting] = useState('');
  const picker = useRef(null);

  // bộ lọc lấy từ địa chỉ (vd. /?lo=Đà Lạt 1L sau khi nhập thư mục)
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setFilter({ q: p.get('q') || '', lo: p.get('lo') || '', trang_thai: p.get('trang_thai') || '' });
    setQInput(p.get('q') || '');
    setReady(true);
  }, []);

  const load = useCallback(async () => {
    if (!ready) return;
    try {
      const [d, l, q] = await Promise.all([
        api('/ho-so' + qs({ ...filter, trang: page, moi_trang: PER_PAGE })),
        api('/lo'),
        api('/hang-doi'),
      ]);
      setData(d);
      setLots(l);
      setQueue(q);
      setError('');
    } catch (e) {
      setError(e.message);
    }
  }, [filter, page, ready]);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  const setF = (patch) => {
    const next = { ...filter, ...patch };
    setFilter(next);
    setPage(1);
    setSelected(new Set());
    history.replaceState(null, '', '/' + qs(next));
  };

  // tìm kiếm: chờ người dùng gõ xong
  useEffect(() => {
    const t = setTimeout(() => qInput !== filter.q && setF({ q: qInput }), 400);
    return () => clearTimeout(t);
  }, [qInput]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = data?.ho_so;
  const total = data?.tong ?? 0;
  const pages = Math.max(1, Math.ceil(total / PER_PAGE));
  const hasFilter = filter.q || filter.lo || filter.trang_thai;
  const sel = [...selected];
  // thao tác hàng loạt: hồ sơ đang tích, hoặc mọi hồ sơ khớp bộ lọc
  const target = sel.length ? { ids: sel } : { loc: filter };
  const targetQs = sel.length ? qs({ ids: sel.join(',') }) : qs({ lo: filter.lo, q: filter.q, trang_thai: filter.trang_thai });
  const targetLabel = sel.length ? `${sel.length} hồ sơ đang tích` : hasFilter ? `${total} hồ sơ đang lọc` : `tất cả ${total} hồ sơ`;

  const bulk = async (path, body, confirmText) => {
    if (confirmText && !confirm(confirmText)) return;
    setMsg('');
    try {
      const r = await api(path, { method: 'POST', body });
      setMsg(
        r.da_xep !== undefined
          ? `Đã xếp ${r.da_xep} hồ sơ vào hàng đợi.`
          : r.da_bo !== undefined
            ? `Đã bỏ ${r.da_bo} hồ sơ khỏi hàng đợi.`
            : `Đã xóa ${r.da_xoa} hồ sơ${r.bo_qua_dang_chay ? ` (bỏ qua ${r.bo_qua_dang_chay} hồ sơ đang chạy)` : ''}.`,
      );
      setSelected(new Set());
    } catch (e) {
      setError(e.message);
    }
    load();
  };

  const exportFile = async (kind) => {
    setExporting(kind);
    setError('');
    setMsg('');
    try {
      const name = await download(`/xuat/${kind}` + targetQs);
      setMsg(`Đã xuất ${name} (trong thư mục Downloads). Hồ sơ chưa xử lý xong không có trong file.`);
    } catch (e) {
      setError(e.message);
    }
    setExporting('');
  };

  const toggle = (id) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const allOnPage = rows?.length > 0 && rows.every((r) => selected.has(r.id));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Hồ sơ</h1>
        <Link href="/nhap/" className="btn btn-light">
          <FolderInput size={16} /> Nhập cả thư mục
        </Link>
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

      {data && (total > 0 || hasFilter) ? (
        <DropZone onFile={setNewFile} compact title="Kéo thả 1 file PDF vào đây để tạo hồ sơ mới" />
      ) : (
        data && (
          <div className="grid gap-3 md:grid-cols-2">
            <DropZone onFile={setNewFile} title="Kéo thả 1 file PDF scan của hồ sơ vào đây" />
            <Link
              href="/nhap/"
              className="card flex flex-col items-center justify-center gap-2 border-2 border-dashed border-gray-300 p-14 text-center hover:border-blue-400 hover:bg-blue-50/40"
            >
              <FolderInput size={34} className="text-blue-700" />
              <div className="font-medium">Nhập cả một thư mục hàng trăm file đã số hóa</div>
              <div className="text-sm text-gray-500">mỗi thư mục con = 1 hồ sơ, mỗi file PDF = 1 tài liệu</div>
            </Link>
          </div>
        )
      )}

      <QueuePanel q={queue} onChanged={load} />

      {error && <div className="card border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {msg && (
        <div className="card flex items-center gap-2 border-green-200 bg-green-50 p-3 text-sm text-green-800">
          <CheckCircle2 size={15} /> <span className="flex-1">{msg}</span>
          <button onClick={() => setMsg('')} className="opacity-60 hover:opacity-100">
            <X size={14} />
          </button>
        </div>
      )}

      {/* ---------------------------------------------------------------- lọc */}
      <div className="card flex flex-wrap items-center gap-2 p-2.5">
        <div className="relative min-w-[220px] flex-1">
          <Search size={15} className="absolute left-2.5 top-2.5 text-gray-400" />
          <input
            className="input pl-8"
            placeholder="Tìm theo mã hồ sơ, tiêu đề, thư mục…"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
          />
        </div>
        <select className="input w-auto" value={filter.lo} onChange={(e) => setF({ lo: e.target.value })}>
          <option value="">Mọi lô</option>
          {lots.map((l) => (
            <option key={l.lo || '-'} value={l.lo || '-'}>
              {l.lo || 'Hồ sơ tạo lẻ (từng file PDF)'} — {l.so_ho_so} hồ sơ
              {l.dang_cho ? `, ${l.dang_cho} đang chờ` : ''}
            </option>
          ))}
        </select>
        <select className="input w-auto" value={filter.trang_thai} onChange={(e) => setF({ trang_thai: e.target.value })}>
          {STATUS_FILTERS.map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        {hasFilter && (
          <button className="btn btn-light" onClick={() => (setQInput(''), setF({ q: '', lo: '', trang_thai: '' }))}>
            <X size={14} /> Bỏ lọc
          </button>
        )}
      </div>

      {/* ---------------------------------------------------------------- thao tác hàng loạt */}
      {total > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          <span className="mr-1 text-gray-600">
            Áp dụng cho <b>{targetLabel}</b>:
          </span>
          <button
            className="btn btn-light"
            disabled={!!exporting}
            onClick={() => exportFile('xlsx')}
            title="Mọi tài liệu của các hồ sơ trong 1 file Excel (23 cột)"
          >
            {exporting === 'xlsx' ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Excel gộp (1 file)
          </button>
          <button
            className="btn btn-light"
            disabled={!!exporting}
            onClick={() => exportFile('xlsx-zip')}
            title="File .zip, trong đó mỗi hồ sơ 1 file Excel (23 cột)"
          >
            {exporting === 'xlsx-zip' ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Mỗi hồ sơ 1 file
            Excel (.zip)
          </button>
          <button
            className="btn btn-light"
            title="Chạy AI cho các văn bản chưa có (vd. lô đã 'bỏ qua AI'); văn bản AI đã đọc thì giữ nguyên"
            onClick={() => bulk('/hang-doi/them', { ...target, chi_chua_ai: true })}
          >
            <Bot size={14} /> Chạy AI phần còn thiếu
          </button>
          <button className="btn btn-light" onClick={() => bulk('/hang-doi/bo', target)}>
            <X size={14} /> Bỏ khỏi hàng đợi
          </button>
          <button
            className="btn btn-danger"
            onClick={() =>
              bulk(
                '/ho-so/xoa',
                target,
                `Xóa ${targetLabel} khỏi app (kết quả đọc, phần đã soát)? File PDF gốc trong thư mục của bạn KHÔNG bị xóa.`,
              )
            }
          >
            <Trash2 size={14} /> Xóa
          </button>
          {sel.length > 0 && (
            <button className="text-xs text-blue-700 hover:underline" onClick={() => setSelected(new Set())}>
              bỏ tích
            </button>
          )}
        </div>
      )}

      {/* ---------------------------------------------------------------- bảng */}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="w-8 px-3 py-2.5">
                <input
                  type="checkbox"
                  checked={allOnPage}
                  onChange={() =>
                    setSelected((s) => {
                      const n = new Set(s);
                      rows.forEach((r) => (allOnPage ? n.delete(r.id) : n.add(r.id)));
                      return n;
                    })
                  }
                  title="Tích cả trang này"
                />
              </th>
              <th className="px-3 py-2.5">Mã hồ sơ</th>
              <th className="px-3 py-2.5">Tiêu đề</th>
              {!filter.lo && <th className="px-3 py-2.5">Lô</th>}
              <th className="px-3 py-2.5">Trạng thái</th>
              <th className="px-3 py-2.5 text-right">Trang</th>
              <th className="px-3 py-2.5 text-right">Tài liệu</th>
              <th className="px-3 py-2.5 text-right">Cần kiểm tra</th>
              <th className="px-3 py-2.5 text-right">Đã soát</th>
              <th className="px-3 py-2.5">Cập nhật</th>
            </tr>
          </thead>
          <tbody>
            {rows?.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-10 text-center text-gray-500">
                  {hasFilter ? 'Không có hồ sơ nào khớp bộ lọc.' : 'Chưa có hồ sơ nào. Kéo thả file PDF hoặc nhập cả thư mục để bắt đầu.'}
                </td>
              </tr>
            )}
            {rows?.map((r) => {
              const [label, cls] = STATUS[r.trang_thai] || [r.trang_thai, 'bg-gray-100'];
              return (
                <tr
                  key={r.id}
                  className={`cursor-pointer border-t border-gray-100 hover:bg-blue-50/40 ${selected.has(r.id) ? 'bg-blue-50/60' : ''}`}
                  onClick={() => router.push(`/ho-so/?id=${r.id}`)}
                >
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
                  </td>
                  <td className="px-3 py-2 font-medium text-blue-800">{r.ma_ho_so}</td>
                  <td className="max-w-xs truncate px-3 py-2">{r.tieu_de || <span className="text-gray-400">—</span>}</td>
                  {!filter.lo && <td className="px-3 py-2 text-gray-600">{r.lo || <span className="text-gray-400">—</span>}</td>}
                  <td className="px-3 py-2">
                    <span className={`badge ${cls}`} title={r.loi || ''}>
                      {(r.trang_thai === 'dang_xu_ly' || r.trang_thai === 'cho') && (
                        <Loader2 size={12} className={`mr-1 ${r.trang_thai === 'dang_xu_ly' ? 'animate-spin' : ''}`} />
                      )}
                      {label}
                    </span>
                    {r.chua_ai > 0 && r.trang_thai === 'xong' && (
                      <span className="badge ml-1 bg-gray-100 text-gray-600" title="Văn bản chưa chạy AI (cơ quan, trích yếu, từ khóa trống)">
                        {r.chua_ai} chưa AI
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">{r.so_trang || '—'}</td>
                  <td className="px-3 py-2 text-right">{r.so_tai_lieu}</td>
                  <td className="px-3 py-2 text-right">
                    {r.can_kiem_tra ? (
                      <span className="inline-flex items-center gap-1 text-amber-700">
                        <AlertTriangle size={13} /> {r.can_kiem_tra}
                      </span>
                    ) : (
                      '0'
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {r.so_tai_lieu > 0 && r.da_soat === r.so_tai_lieu ? (
                      <span className="inline-flex items-center gap-1 text-green-700">
                        <CheckCircle2 size={13} /> {r.da_soat}
                      </span>
                    ) : (
                      `${r.da_soat}/${r.so_tai_lieu}`
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-gray-500">{r.cap_nhat?.replace('T', ' ')}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {total > PER_PAGE && (
          <div className="flex items-center justify-end gap-2 border-t px-3 py-2 text-sm">
            <span className="mr-auto text-gray-500">
              {(page - 1) * PER_PAGE + 1}–{Math.min(page * PER_PAGE, total)} / {total} hồ sơ
            </span>
            <button className="btn btn-light py-1" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Trước
            </button>
            <span>
              Trang {page}/{pages}
            </span>
            <button className="btn btn-light py-1" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Sau
            </button>
          </div>
        )}
      </div>

      {newFile && <NewHoSoDialog file={newFile} onClose={() => setNewFile(null)} />}
    </div>
  );
}
