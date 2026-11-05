'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react';
import { api, fileUrl, plain } from '@/lib/api';

/**
 * Xem ảnh các trang của một văn bản, vẽ khung các dòng chữ OCR.
 * `highlight` = giá trị trường đang chọn -> tô sáng các dòng chữ chứa giá trị đó trên ảnh.
 */
export default function PageViewer({ hoSoId, pages, highlight, version = 0 }) {
  const [idx, setIdx] = useState(0);
  const [ocr, setOcr] = useState(null);
  const [zoom, setZoom] = useState(1);
  const page = pages[Math.min(idx, pages.length - 1)];

  useEffect(() => setIdx(0), [pages.join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let stop = false;
    setOcr(null);
    if (!page) return undefined;
    api(`/ho-so/${hoSoId}/trang/${page}/ocr`)
      .then((d) => !stop && setOcr(d))
      .catch(() => !stop && setOcr(null));
    return () => {
      stop = true;
    };
  }, [hoSoId, page, version]);

  const hits = useMemo(() => {
    const target = plain(highlight);
    if (!ocr || target.length < 2) return new Set();
    const words = new Set(target.split(' ').filter((w) => w.length > 1));
    const out = new Set();
    ocr.lines.forEach((l, i) => {
      const t = plain(l.text);
      if (t.length < 2) return;
      if (target.includes(t) || t.includes(target)) return out.add(i);
      const lw = t.split(' ').filter((w) => w.length > 1);
      const common = lw.filter((w) => words.has(w)).length;
      if (lw.length && common / lw.length >= 0.6 && common >= 2) out.add(i);
    });
    return out;
  }, [ocr, highlight]);

  if (!page) return <div className="p-6 text-sm text-gray-500">Không có trang</div>;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b px-3 py-2 text-sm">
        <button className="btn btn-light px-2" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>
          <ChevronLeft size={16} />
        </button>
        <span>
          Trang PDF <b>{page}</b> ({idx + 1}/{pages.length})
        </span>
        <button className="btn btn-light px-2" disabled={idx >= pages.length - 1} onClick={() => setIdx(idx + 1)}>
          <ChevronRight size={16} />
        </button>
        <div className="ml-auto flex items-center gap-1">
          <button className="btn btn-light px-2" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}>
            <ZoomOut size={16} />
          </button>
          <span className="w-12 text-center text-xs">{Math.round(zoom * 100)}%</span>
          <button className="btn btn-light px-2" onClick={() => setZoom((z) => Math.min(3, z + 0.25))}>
            <ZoomIn size={16} />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto bg-gray-100 p-3">
        <div className="relative mx-auto bg-white shadow" style={{ width: `${zoom * 100}%` }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={fileUrl(`/ho-so/${hoSoId}/trang/${page}/anh?v=${version}`)} alt={`Trang ${page}`} className="block w-full" />
          {ocr && (
            <svg
              className="pointer-events-none absolute inset-0 h-full w-full"
              viewBox={`0 0 ${ocr.width} ${ocr.height}`}
              preserveAspectRatio="none"
            >
              {ocr.lines.map((l, i) => {
                const [x0, y0, x1, y1] = l.box;
                const hit = hits.has(i);
                const low = l.score < 0.8;
                if (!hit && !low) return null;
                return (
                  <rect
                    key={i}
                    x={x0 - 6}
                    y={y0 - 6}
                    width={x1 - x0 + 12}
                    height={y1 - y0 + 12}
                    rx={6}
                    fill={hit ? 'rgba(250, 204, 21, 0.35)' : 'none'}
                    stroke={hit ? 'rgb(202, 138, 4)' : 'rgba(239, 68, 68, 0.6)'}
                    strokeWidth={hit ? 5 : 3}
                    strokeDasharray={hit ? '' : '12 8'}
                  />
                );
              })}
            </svg>
          )}
        </div>
        <p className="mt-2 text-center text-[11px] text-gray-500">
          Khung vàng: chữ của ô đang chọn · Khung đỏ nét đứt: OCR kém tin cậy, nên đối chiếu
        </p>
      </div>
    </div>
  );
}
