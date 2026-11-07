'use client';

import Link from 'next/link';
import { Loader2, Pause, Play } from 'lucide-react';
import { api, fmtDuration, fmtFinish } from '@/lib/api';

/**
 * Hàng đợi xử lý: hồ sơ đang chạy, số hồ sơ đang chờ, giờ xong dự kiến, nút Tạm dừng / Chạy tiếp.
 * `q` = kết quả GET /api/hang-doi (trang cha tự hỏi định kỳ rồi truyền vào).
 */
export default function QueuePanel({ q, onChanged }) {
  if (!q || (!q.dang_chay && !q.so_cho)) return null;
  const run = q.dang_chay;
  const toggle = async () => {
    await api(q.tam_dung ? '/hang-doi/tiep-tuc' : '/hang-doi/tam-dung', { method: 'POST' });
    onChanged?.();
  };
  return (
    <div className={`card flex flex-wrap items-center gap-x-4 gap-y-2 p-3 text-sm ${q.tam_dung ? 'border-amber-300 bg-amber-50' : ''}`}>
      {q.tam_dung ? (
        <Pause size={16} className="text-amber-700" />
      ) : (
        <Loader2 size={16} className="animate-spin text-blue-700" />
      )}
      <div className="min-w-0 flex-1">
        {q.tam_dung ? (
          <b className="text-amber-900">Hàng đợi đang tạm dừng</b>
        ) : run ? (
          <span>
            Đang xử lý{' '}
            <Link href={`/ho-so/?id=${run.ho_so_id}`} className="font-medium text-blue-800 hover:underline">
              {run.ma_ho_so}
            </Link>{' '}
            — {run.stage_label}
            {run.total > 0 && ` ${run.current}/${run.total}`}
          </span>
        ) : (
          <span>Chuẩn bị xử lý…</span>
        )}
        <span className="text-gray-600">
          {q.so_cho > 0 && (
            <>
              {' '}
              · <b>{q.so_cho}</b> hồ sơ đang chờ
            </>
          )}
          {q.uoc_tinh_giay > 0 && !q.tam_dung && (
            <>
              {' '}
              · xong khoảng <b>{fmtFinish(q.uoc_tinh_giay)}</b> (còn ~{fmtDuration(q.uoc_tinh_giay)})
            </>
          )}
          {q.uoc_tinh_giay > 0 && q.tam_dung && <> · còn ~{fmtDuration(q.uoc_tinh_giay)} khi chạy tiếp</>}
        </span>
        {!q.tam_dung && q.so_cho > 0 && (
          <div className="text-xs text-gray-500">
            Có thể để máy chạy qua đêm: nhớ cắm sạc; app tự giữ máy không ngủ khi còn việc. Tắt app giữa chừng thì lần mở sau tự làm tiếp.
          </div>
        )}
      </div>
      <button className={`btn ${q.tam_dung ? 'btn-primary' : 'btn-light'}`} onClick={toggle}>
        {q.tam_dung ? <Play size={14} /> : <Pause size={14} />} {q.tam_dung ? 'Chạy tiếp' : 'Tạm dừng'}
      </button>
    </div>
  );
}
