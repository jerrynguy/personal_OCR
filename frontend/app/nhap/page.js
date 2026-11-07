'use client';

import { Fragment, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, FolderOpen, FolderSearch, Loader2, Play, Search,
} from 'lucide-react';
import { api, fmtDuration } from '@/lib/api';
import FieldForm from '@/components/FieldForm';
import { HO_SO_MAIN, PHONG_MAIN, loadLast, saveLast, splitFields } from '@/lib/fields';

const PAGE = 100; // số thư mục hiện mỗi trang của bảng xem trước
const NOT_SHARED = ['ma_ho_so', 'tieu_de_ho_so'];

/**
 * Nhập cả một thư mục: mỗi thư mục có file PDF = 1 hồ sơ, mỗi file PDF = 1 tài liệu.
 * App chỉ GỢI Ý (mã hồ sơ, file có vẻ là bản gộp); người dùng xem bảng, sửa, bỏ tích rồi mới tạo.
 */
export default function ImportPage() {
  const [path, setPath] = useState('');
  const [scan, setScan] = useState(null); // {id, xong, da_doc, tong, loi, ket_qua}
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [picking, setPicking] = useState(false);
  const [onlyWarn, setOnlyWarn] = useState(false);
  const [page, setPage] = useState(0);
  const [schema, setSchema] = useState(null);
  const [hoSo, setHoSo] = useState({});
  const [phong, setPhong] = useState({});
  const [lo, setLo] = useState('');
  const [noAi, setNoAi] = useState(false);
  const [rates, setRates] = useState(null);
  const [creating, setCreating] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    try {
      setPath(localStorage.getItem('sohoa_thu_muc') || '');
    } catch {}
    api('/schema')
      .then((s) => {
        setSchema(s);
        const last = loadLast();
        const init = (fs, prev) => Object.fromEntries(fs.map((f) => [f.key, prev?.[f.key] || f.mac_dinh || '']));
        setPhong(init(s.phong, last.phong));
        setHoSo(init(s.ho_so, last.ho_so));
      })
      .catch((e) => setError(e.message));
    api('/hang-doi')
      .then((q) => setRates(q.toc_do))
      .catch(() => {});
  }, []);

  // hỏi tiến độ quét
  useEffect(() => {
    if (!scan || scan.xong) return undefined;
    const t = setInterval(async () => {
      try {
        const s = await api(`/nhap/quet/${scan.id}`);
        setScan(s);
        if (s.xong && s.ket_qua) {
          const kq = s.ket_qua;
          setLo(kq.ten_lo);
          setPage(0);
          setRows(
            kq.ho_so.map((f, i) => ({
              i,
              on: !f.da_nhap && !f.ma_da_co && f.files.some((x) => !x.loi),
              ma: f.ma_goi_y,
              tieu_de: '',
              files: f.files.map((x) => !x.loi),
              open: false,
            })),
          );
        }
      } catch (e) {
        setError(e.message);
        setScan(null);
      }
    }, 400);
    return () => clearInterval(t);
  }, [scan]);

  const pick = async () => {
    setPicking(true);
    setError('');
    try {
      const r = await api('/nhap/chon-thu-muc', { method: 'POST', body: { ban_dau: path } });
      if (r.duong_dan) {
        setPath(r.duong_dan);
        start(r.duong_dan);
      }
    } catch (e) {
      setError(e.message);
    }
    setPicking(false);
  };

  const start = async (p = path) => {
    setError('');
    setDone(null);
    setRows([]);
    try {
      localStorage.setItem('sohoa_thu_muc', p);
    } catch {}
    try {
      const { id } = await api('/nhap/quet', { method: 'POST', body: { duong_dan: p } });
      setScan({ id, xong: false, da_doc: 0, tong: 0 });
    } catch (e) {
      setError(e.message);
    }
  };

  const kq = scan?.xong ? scan.ket_qua : null;
  const folders = kq?.ho_so || [];
  const setRow = (i, patch) => setRows((rs) => rs.map((r) => (r.i === i ? { ...r, ...patch } : r)));

  // mã trùng giữa các thư mục đang chọn
  const dupCodes = useMemo(() => {
    const seen = {};
    rows.filter((r) => r.on).forEach((r) => {
      const k = r.ma.trim();
      seen[k] = (seen[k] || 0) + 1;
    });
    return new Set(Object.keys(seen).filter((k) => seen[k] > 1));
  }, [rows]);

  const rowInfo = (r) => {
    const f = folders[r.i];
    const files = f.files.filter((_, k) => r.files[k]);
    const issues = [];
    if (f.da_nhap) issues.push(`Đã nhập trước đây (mã ${f.da_nhap.ma_ho_so})`);
    if (f.ma_da_co && r.ma === f.ma_goi_y) issues.push('Mã hồ sơ đã có trong app');
    if (r.on && dupCodes.has(r.ma.trim())) issues.push('Trùng mã với thư mục khác');
    if (r.on && !r.ma.trim()) issues.push('Chưa có mã hồ sơ');
    if (r.on && !files.length) issues.push('Chưa chọn file nào');
    const bad = f.files.filter((x) => x.loi).length;
    const gop = f.files.filter((x, k) => x.goi_y_gop && r.files[k]).length;
    return { f, files, issues, bad, gop, pages: files.reduce((a, x) => a + x.so_trang, 0) };
  };

  const chosen = rows.filter((r) => r.on);
  const infos = chosen.map(rowInfo);
  const blocking = infos.filter((x) => x.issues.some((m) => !m.startsWith('Đã nhập')));
  const totalPages = infos.reduce((a, x) => a + x.pages, 0);
  const totalFiles = infos.reduce((a, x) => a + x.files.length, 0);
  const eta = rates ? totalPages * rates.giay_moi_trang_ocr + (noAi ? 0 : totalFiles * rates.giay_moi_van_ban_ai) : null;
  const gopTicked = rows.reduce((a, r) => a + folders[r.i].files.filter((x, k) => x.goi_y_gop && r.files[k]).length, 0);
  const gopTotal = kq?.so_file_goi_y_gop || 0;

  const untickMerged = () =>
    setRows((rs) => rs.map((r) => ({ ...r, files: r.files.map((on, k) => on && !folders[r.i].files[k].goi_y_gop) })));

  const shown = rows.filter((r) => !onlyWarn || rowInfo(r).issues.length || rowInfo(r).gop || rowInfo(r).bad);
  const pages = Math.max(1, Math.ceil(shown.length / PAGE));
  const visible = shown.slice(page * PAGE, page * PAGE + PAGE);

  const create = async () => {
    setCreating(true);
    setError('');
    try {
      const shared = Object.fromEntries(Object.entries(hoSo).filter(([k]) => !NOT_SHARED.includes(k)));
      saveLast({ phong, ho_so: shared });
      const res = await api('/nhap/tao', {
        method: 'POST',
        body: {
          quet_id: scan.id,
          lo,
          khong_llm: noAi,
          phong,
          ho_so: shared,
          chon: chosen.map((r) => ({
            i: r.i,
            ma_ho_so: r.ma.trim(),
            tieu_de_ho_so: r.tieu_de.trim(),
            files: r.files.map((on, k) => (on ? k : -1)).filter((k) => k >= 0),
          })),
        },
      });
      setDone(res);
    } catch (e) {
      setError(e.message);
    }
    setCreating(false);
  };

  const manual = (fs) => fs.filter((f) => f.nguon === 'nhap_tay');
  const [hoSoMain, hoSoRest] = schema ? splitFields(manual(schema.ho_so), HO_SO_MAIN) : [[], []];
  const [phongMain, phongRest] = schema ? splitFields(manual(schema.phong), PHONG_MAIN) : [[], []];

  if (done) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="card space-y-3 p-6">
          <div className="flex items-center gap-2 text-lg font-semibold text-green-800">
            <CheckCircle2 size={22} /> Đã tạo {done.da_tao} hồ sơ và xếp hàng xử lý
          </div>
          <p className="text-sm text-gray-600">
            App xử lý lần lượt từng hồ sơ ở nền. Bạn có thể đóng trang này, làm việc khác, hoặc để máy chạy qua đêm
            (nhớ cắm sạc). Tắt app giữa chừng thì lần mở sau app tự làm tiếp.
          </p>
          {done.loi?.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <b>{done.loi.length} thư mục chưa tạo được:</b>
              <ul className="mt-1 list-disc pl-5">
                {done.loi.map((e) => (
                  <li key={e.thu_muc}>
                    {e.thu_muc}: {e.loi}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex gap-2">
            <Link href={`/?lo=${encodeURIComponent(lo)}`} className="btn btn-primary">
              <FolderOpen size={15} /> Xem các hồ sơ của lô “{lo}”
            </Link>
            <button className="btn btn-light" onClick={() => setDone(null)}>
              Quay lại bảng
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <h1 className="text-xl font-semibold">Nhập cả thư mục</h1>
        <p className="text-sm text-gray-600">
          Chọn thư mục lớn (vd. <b>Đà Lạt 1L</b>). <b>Mỗi thư mục con có file PDF = 1 hồ sơ</b>,{' '}
          <b>mỗi file PDF = 1 tài liệu</b>. App đọc thẳng file trong thư mục, không sao chép — đừng di chuyển hay đổi tên
          thư mục cho đến khi xử lý và xuất xong.
        </p>
      </div>

      {/* ---------------------------------------------------------------- chọn thư mục */}
      <div className="card flex flex-wrap items-center gap-2 p-3">
        <button className="btn btn-primary" onClick={pick} disabled={picking || (scan && !scan.xong)}>
          {picking ? <Loader2 size={15} className="animate-spin" /> : <FolderSearch size={15} />} Chọn thư mục…
        </button>
        <span className="text-sm text-gray-500">hoặc dán đường dẫn:</span>
        <input
          className="input min-w-[280px] flex-1 font-mono text-[13px]"
          placeholder="D:\Số hóa\Đà Lạt 1L"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && path.trim() && start()}
        />
        <button className="btn btn-light" onClick={() => start()} disabled={!path.trim() || (scan && !scan.xong)}>
          <Search size={15} /> Đọc thư mục
        </button>
      </div>
      {picking && (
        <p className="text-xs text-gray-500">
          Hộp chọn thư mục của Windows đang mở (có thể nằm sau cửa sổ trình duyệt — xem thanh tác vụ).
        </p>
      )}

      {error && <div className="card border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {scan && !scan.xong && (
        <div className="card p-3 text-sm">
          <div className="mb-1 flex items-center gap-2">
            <Loader2 size={15} className="animate-spin text-blue-700" /> Đang đọc thư mục… {scan.da_doc}/{scan.tong || '?'}{' '}
            file
          </div>
          <div className="h-2 overflow-hidden rounded bg-gray-100">
            <div className="h-full bg-blue-600" style={{ width: `${scan.tong ? (scan.da_doc / scan.tong) * 100 : 5}%` }} />
          </div>
        </div>
      )}
      {scan?.xong && scan.loi && <div className="card border-red-200 bg-red-50 p-3 text-sm text-red-700">{scan.loi}</div>}

      {kq && (
        <>
          {/* ---------------------------------------------------------------- tóm tắt */}
          <div className="card flex flex-wrap items-center gap-x-5 gap-y-1 p-3 text-sm">
            <span>
              Tìm thấy <b>{kq.so_ho_so}</b> thư mục (hồ sơ) · <b>{kq.so_file}</b> file PDF · <b>{kq.so_trang}</b> trang
            </span>
            <span className="text-gray-600">
              Đang chọn: <b>{chosen.length}</b> hồ sơ · {totalFiles} tài liệu · {totalPages} trang
              {eta != null && chosen.length > 0 && <> · ước tính <b>~{fmtDuration(eta)}</b> trên máy này</>}
            </span>
            <div className="ml-auto flex gap-1">
              <button className="btn btn-light py-1 text-xs" onClick={() => setRows((rs) => rs.map((r) => ({ ...r, on: true })))}>
                Chọn hết
              </button>
              <button className="btn btn-light py-1 text-xs" onClick={() => setRows((rs) => rs.map((r) => ({ ...r, on: false })))}>
                Bỏ chọn hết
              </button>
            </div>
          </div>

          {gopTotal > 0 && (
            <div className="card flex flex-wrap items-center gap-2 border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <AlertTriangle size={16} />
              <span className="flex-1">
                <b>{gopTotal} file</b> có vẻ là <b>bản gộp</b> của các file khác trong cùng thư mục (nội dung từng trang
                trùng nhau) — nhãn <span className="badge bg-amber-200 text-amber-900">⚠ có vẻ là bản gộp</span>. App vẫn để
                tích; bạn quyết định.
              </span>
              <button className="btn btn-light" onClick={untickMerged} disabled={!gopTicked}>
                Bỏ tích {gopTicked} file gợi ý gộp
              </button>
            </div>
          )}

          {/* ---------------------------------------------------------------- bảng xem trước */}
          <div className="card overflow-hidden">
            <div className="flex items-center gap-3 border-b px-3 py-2 text-xs text-gray-600">
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={onlyWarn} onChange={(e) => (setOnlyWarn(e.target.checked), setPage(0))} />
                Chỉ hiện thư mục cần xem (có cảnh báo / file gộp / file lỗi)
              </label>
              <span className="ml-auto">Bấm ▸ để xem và bỏ tích từng file</span>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
                <tr>
                  <th className="w-8 px-3 py-2" />
                  <th className="w-8 px-1 py-2" />
                  <th className="px-2 py-2">Thư mục</th>
                  <th className="px-2 py-2">Mã hồ sơ</th>
                  <th className="px-2 py-2">Tiêu đề (không bắt buộc)</th>
                  <th className="px-2 py-2 text-right">File</th>
                  <th className="px-2 py-2 text-right">Trang</th>
                  <th className="px-3 py-2">Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => {
                  const x = rowInfo(r);
                  return (
                    <Fragment key={r.i}>
                      <tr className={`border-t border-gray-100 ${r.on ? '' : 'bg-gray-50 text-gray-400'}`}>
                        <td className="px-3 py-1.5">
                          <input type="checkbox" checked={r.on} onChange={(e) => setRow(r.i, { on: e.target.checked })} />
                        </td>
                        <td className="px-1">
                          <button className="text-gray-500 hover:text-gray-800" onClick={() => setRow(r.i, { open: !r.open })}>
                            {r.open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                          </button>
                        </td>
                        <td className="px-2 py-1.5 font-medium">{x.f.ten}</td>
                        <td className="px-2 py-1.5">
                          <input
                            className={`input py-1 ${x.issues.some((m) => m.includes('mã') || m.includes('Mã')) ? 'border-red-400' : ''}`}
                            value={r.ma}
                            disabled={!r.on}
                            onChange={(e) => setRow(r.i, { ma: e.target.value })}
                            title={x.f.ma_tu === 'ten_file' ? 'Lấy từ phần chung của tên các file' : 'Lấy theo tên thư mục'}
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <input
                            className="input py-1"
                            value={r.tieu_de}
                            disabled={!r.on}
                            onChange={(e) => setRow(r.i, { tieu_de: e.target.value })}
                          />
                        </td>
                        <td className="px-2 py-1.5 text-right">
                          {x.files.length}/{x.f.files.length}
                        </td>
                        <td className="px-2 py-1.5 text-right">{x.pages}</td>
                        <td className="px-3 py-1.5 text-xs">
                          <div className="flex flex-wrap gap-1">
                            {x.issues.map((m) => (
                              <span key={m} className={`badge ${m.startsWith('Đã nhập') ? 'bg-gray-100 text-gray-600' : 'bg-red-50 text-red-700'}`}>
                                {m}
                              </span>
                            ))}
                            {x.gop > 0 && <span className="badge bg-amber-100 text-amber-900">⚠ {x.gop} file có vẻ là bản gộp</span>}
                            {x.bad > 0 && <span className="badge bg-red-50 text-red-700">{x.bad} file lỗi</span>}
                            {x.f.ma_tu === 'thu_muc_vi_trung' && (
                              <span className="badge bg-gray-100 text-gray-600" title="Phần chung tên file trùng với thư mục khác">
                                mã theo tên thư mục
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                      {r.open && (
                        <tr className="border-t border-gray-100 bg-gray-50/60">
                          <td colSpan={8} className="px-10 py-2">
                            <div className="mb-1 truncate font-mono text-[11px] text-gray-500">{x.f.thu_muc}</div>
                            <table className="w-full text-xs">
                              <tbody>
                                {x.f.files.map((file, k) => (
                                  <tr key={file.ten} className={r.files[k] ? '' : 'text-gray-400'}>
                                    <td className="w-6 py-0.5">
                                      <input
                                        type="checkbox"
                                        disabled={!!file.loi}
                                        checked={r.files[k]}
                                        onChange={(e) =>
                                          setRow(r.i, { files: r.files.map((v, j) => (j === k ? e.target.checked : v)) })
                                        }
                                      />
                                    </td>
                                    <td className="py-0.5 pr-3 font-medium">{file.ten}</td>
                                    <td className="w-20 py-0.5 text-right">{file.so_trang ? `${file.so_trang} trang` : ''}</td>
                                    <td className="w-20 py-0.5 text-right">{(file.dung_luong / 1048576).toFixed(1)} MB</td>
                                    <td className="py-0.5 pl-3">
                                      {file.loi && <span className="text-red-700">{file.loi}</span>}
                                      {file.goi_y_gop && (
                                        <span className="badge bg-amber-100 text-amber-900">
                                          ⚠ có vẻ là bản gộp của: {file.goi_y_gop.join(' + ')}
                                        </span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            {pages > 1 && (
              <div className="flex items-center justify-end gap-2 border-t px-3 py-2 text-sm">
                <button className="btn btn-light py-1" disabled={page === 0} onClick={() => setPage(page - 1)}>
                  Trước
                </button>
                <span>
                  Trang {page + 1}/{pages}
                </span>
                <button className="btn btn-light py-1" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>
                  Sau
                </button>
              </div>
            )}
          </div>

          {/* ---------------------------------------------------------------- thông tin chung + tạo */}
          <div className="card space-y-3 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label">Tên lô (để lọc và xuất Excel cả lô về sau)</label>
                <input className="input" value={lo} onChange={(e) => setLo(e.target.value)} />
              </div>
            </div>
            <details className="rounded-md border border-gray-200 p-3">
              <summary className="cursor-pointer text-sm text-blue-700">
                Thông tin chung cho mọi hồ sơ trong lô (thời hạn lưu trữ, mức độ tiếp cận, phông…) — nhớ theo lần trước
              </summary>
              {schema && (
                <div className="mt-3 space-y-4">
                  <FieldForm
                    fields={[...hoSoMain.filter((f) => !NOT_SHARED.includes(f.key)), ...phongMain]}
                    values={{ ...hoSo, ...phong }}
                    onChange={(k, v) =>
                      PHONG_MAIN.includes(k) ? setPhong((s) => ({ ...s, [k]: v })) : setHoSo((s) => ({ ...s, [k]: v }))
                    }
                  />
                  <details className="text-sm">
                    <summary className="cursor-pointer text-gray-600">Các trường còn lại của hồ sơ và phông</summary>
                    <div className="mt-3 space-y-4">
                      <FieldForm fields={hoSoRest} values={hoSo} onChange={(k, v) => setHoSo((s) => ({ ...s, [k]: v }))} />
                      <FieldForm fields={phongRest} values={phong} onChange={(k, v) => setPhong((s) => ({ ...s, [k]: v }))} />
                    </div>
                  </details>
                </div>
              )}
            </details>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={noAi} onChange={(e) => setNoAi(e.target.checked)} />
              <span>
                <b>Bỏ qua AI cho nhanh</b> — chỉ đọc tên loại, số, ký hiệu, ngày ban hành (vài giây mỗi trang). Cơ quan ban
                hành, trích yếu, từ khóa để trống; chạy AI bổ sung sau được ở danh sách hồ sơ (nút <i>Chạy AI phần còn thiếu</i>).
              </span>
            </label>
            {blocking.length > 0 && (
              <div className="rounded-md bg-red-50 p-2 text-sm text-red-700">
                {blocking.length} hồ sơ đang chọn cần sửa trước (xem cột Ghi chú màu đỏ): mã trùng, thiếu mã, hoặc chưa chọn file.
              </div>
            )}
            <div className="flex items-center gap-3">
              <button className="btn btn-primary" disabled={creating || !chosen.length || blocking.length > 0} onClick={create}>
                {creating ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />} Tạo {chosen.length} hồ sơ và
                xếp hàng xử lý
              </button>
              <span className="text-xs text-gray-500">Mỗi file PDF = 1 tài liệu. Tách lại từng hồ sơ sau được nếu cần.</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
