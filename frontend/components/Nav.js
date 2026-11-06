'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Archive, Bot, Cpu, FolderOpen } from 'lucide-react';
import { api } from '@/lib/api';

const LINKS = [
  { href: '/', label: 'Hồ sơ', icon: FolderOpen },
  { href: '/model-ai/', label: 'Model AI', icon: Bot },
  { href: '/may/', label: 'Kiểm tra máy', icon: Cpu },
];

/** Thanh trên cùng + trạng thái OCR / AI (đã nạp sẵn chưa). */
export default function Nav() {
  const path = usePathname();
  const [sys, setSys] = useState(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const s = await api('/he-thong');
        if (!stop) {
          setSys(s);
          setOffline(false);
        }
      } catch {
        if (!stop) setOffline(true);
      }
    };
    tick();
    const t = setInterval(tick, 4000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, []);

  const active = (href) => (href === '/' ? path === '/' || path.startsWith('/ho-so') : path.startsWith(href));

  return (
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-[1600px] items-center gap-6 px-4 py-2.5">
        <Link href="/" className="flex items-center gap-2 font-semibold text-blue-800">
          <Archive size={20} /> Số hóa Lưu trữ
        </Link>
        <nav className="flex gap-1">
          {LINKS.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm ${
                active(href) ? 'bg-blue-50 font-medium text-blue-800' : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              <Icon size={16} /> {label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-xs">
          {offline ? (
            <span className="badge bg-red-50 text-red-700">Mất kết nối backend</span>
          ) : sys ? (
            <>
              {sys.nguon_dien && <span className="badge bg-amber-50 text-amber-800">⚠ {sys.nguon_dien}</span>}
              <Status ok={sys.ocr_da_nap} label="OCR" />
              <Status ok={sys.llm_dang_chay} loading={sys.llm_dang_nap} error={sys.llm_loi} label="AI" />
            </>
          ) : null}
        </div>
      </div>
    </header>
  );
}

function Status({ ok, loading, error, label }) {
  const cls = error
    ? 'bg-red-50 text-red-700'
    : ok
      ? 'bg-green-50 text-green-700'
      : loading
        ? 'bg-blue-50 text-blue-700'
        : 'bg-gray-100 text-gray-500';
  const text = error ? 'lỗi' : ok ? 'sẵn sàng' : loading ? 'đang nạp…' : 'chưa nạp';
  return (
    <span className={`badge ${cls}`} title={error || ''}>
      {label}: {text}
    </span>
  );
}
