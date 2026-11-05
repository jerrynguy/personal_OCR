'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Cpu, XCircle } from 'lucide-react';
import { api } from '@/lib/api';

export default function MayPage() {
  const [s, setS] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/he-thong').then(setS).catch((e) => setError(e.message));
  }, []);

  if (!s) return <div className="p-6 text-sm text-gray-500">{error || 'Đang kiểm tra máy…'}</div>;

  const hw = s.phan_cung;
  const rec = s.khuyen_nghi;
  const cfg = s.llm_cau_hinh;
  const ok = (v) =>
    v ? <CheckCircle2 size={15} className="text-green-600" /> : <XCircle size={15} className="text-red-600" />;

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="flex items-center gap-2 text-xl font-semibold">
        <Cpu size={20} /> Kiểm tra máy
      </h1>

      {s.nguon_dien && (
        <div className="card flex gap-2 border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle size={15} className="mt-0.5" />
          Máy {s.nguon_dien} — CPU bị hạ xung, xử lý sẽ chậm hơn nhiều lần. Hãy cắm sạc và đặt Power mode = Best performance.
        </div>
      )}

      <div className="card p-4">
        <h2 className="mb-3 font-semibold">Phần cứng</h2>
        <dl className="grid grid-cols-[160px_1fr] gap-y-1.5 text-sm">
          <dt className="text-gray-500">Hệ điều hành</dt>
          <dd>{hw.he_dieu_hanh}</dd>
          <dt className="text-gray-500">CPU</dt>
          <dd>
            {hw.cpu} — {hw.nhan} nhân / {hw.luong} luồng — AVX2 {hw.avx2 ? 'có' : 'KHÔNG'}, AVX-512 {hw.avx512 ? 'có' : 'không'}
          </dd>
          <dt className="text-gray-500">RAM</dt>
          <dd>{hw.ram_gb} GB</dd>
          <dt className="text-gray-500">Card đồ họa</dt>
          <dd>
            {hw.gpu.length
              ? hw.gpu.map((g) => (
                  <div key={g.ten}>
                    {g.ten} ({g.tich_hop ? 'tích hợp' : 'rời'}
                    {g.vram_gb ? `, ${g.vram_gb} GB VRAM` : ''})
                  </div>
                ))
              : 'Không nhận diện được'}
          </dd>
        </dl>
      </div>

      <div className="card p-4">
        <h2 className="mb-3 font-semibold">Cách app chạy AI trên máy này</h2>
        <ul className="mb-3 list-disc space-y-1 pl-5 text-sm">
          {rec.ly_do.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
        <dl className="grid grid-cols-[160px_1fr] gap-y-1.5 text-sm">
          <dt className="text-gray-500">Đề nghị</dt>
          <dd>
            llama.cpp bản <b>{rec.llama_variant}</b>, {rec.gpu_layers} lớp lên GPU {rec.extra_args.join(' ')} · {rec.llm_tier_ten}
          </dd>
          <dt className="text-gray-500">Đang dùng</dt>
          <dd>
            {cfg ? (
              <>
                bản <b>{cfg.variant}</b>, {cfg.gpu_layers} lớp lên GPU {cfg.extra_args.join(' ')}
                {cfg.ghi_chu && <div className="text-amber-700">{cfg.ghi_chu}</div>}
              </>
            ) : (
              <span className="text-red-600">Chưa cài llama.cpp</span>
            )}
          </dd>
          <dt className="text-gray-500">Đã cài llama.cpp</dt>
          <dd>{s.llama_cpp_da_cai.join(', ') || '—'}</dd>
          <dt className="text-gray-500">Model AI</dt>
          <dd className="flex items-center gap-1.5">
            {ok(s.model_llm_co_file)} {s.model_llm || 'chưa chọn'}
          </dd>
          {s.llm_loi && (
            <>
              <dt className="text-gray-500">Lỗi AI</dt>
              <dd className="text-red-600">{s.llm_loi}</dd>
            </>
          )}
        </dl>
      </div>

      <div className="card p-4">
        <h2 className="mb-3 font-semibold">Model OCR</h2>
        <ul className="space-y-1 text-sm">
          {Object.entries(s.model_ocr).map(([k, v]) => (
            <li key={k} className="flex items-center gap-1.5">
              {ok(v)} {k}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
