'use client';

import { useRef, useState } from 'react';
import { FileUp } from 'lucide-react';

/** Ô kéo thả / bấm để chọn file PDF. */
export default function DropZone({ onFile, title = 'Kéo thả file PDF scan của hồ sơ vào đây', compact = false }) {
  const [over, setOver] = useState(false);
  const input = useRef(null);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files[0];
        if (f) onFile(f);
      }}
      onClick={() => input.current.click()}
      className={`card flex cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed text-center ${
        compact ? 'p-6' : 'p-14'
      } ${over ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-blue-50/40'}`}
    >
      <FileUp size={compact ? 26 : 34} className="text-blue-700" />
      <div className="font-medium">{title}</div>
      <div className="text-sm text-gray-500">hoặc bấm để chọn file · scan nên từ 300 DPI</div>
      <input
        ref={input}
        type="file"
        accept="application/pdf"
        hidden
        onChange={(e) => {
          if (e.target.files[0]) onFile(e.target.files[0]);
          e.target.value = '';
        }}
      />
    </div>
  );
}
