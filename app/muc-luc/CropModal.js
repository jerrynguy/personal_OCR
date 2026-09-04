'use client';

import { useState, useRef, useCallback } from 'react';
import ReactCrop, { centerCrop, makeAspectCrop } from 'react-image-crop';
import 'react-image-crop/dist/ReactCrop.css';
import { X, Check, Loader2 } from 'lucide-react';

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Không đọc được ảnh đã cắt'));
    reader.readAsDataURL(blob);
  });
}

// Vẽ đúng vùng đã chọn (theo pixel thật của ảnh gốc) ra canvas rồi xuất thành Blob.
function getCroppedBlob(image, cropPixels, mediaType) {
  const canvas = document.createElement('canvas');
  const scaleX = image.naturalWidth / image.width;
  const scaleY = image.naturalHeight / image.height;
  canvas.width = Math.max(1, Math.round(cropPixels.width * scaleX));
  canvas.height = Math.max(1, Math.round(cropPixels.height * scaleY));
  const ctx = canvas.getContext('2d');
  ctx.drawImage(
    image,
    cropPixels.x * scaleX,
    cropPixels.y * scaleY,
    cropPixels.width * scaleX,
    cropPixels.height * scaleY,
    0,
    0,
    canvas.width,
    canvas.height
  );
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), mediaType === 'image/png' ? 'image/png' : 'image/jpeg', 0.92);
  });
}

export default function CropModal({ file, onCancel, onApply }) {
  const [crop, setCrop] = useState();
  const [pixelCrop, setPixelCrop] = useState(null);
  const [busy, setBusy] = useState(false);
  const imgRef = useRef(null);

  const onImageLoad = useCallback((e) => {
    const { width, height } = e.currentTarget;
    // Mặc định chọn sẵn gần hết ảnh, người dùng chỉnh lại theo ý muốn.
    const initial = centerCrop(
      makeAspectCrop({ unit: '%', width: 92 }, width / height, width, height),
      width,
      height
    );
    setCrop(initial);
  }, []);

  const handleApply = async () => {
    if (!pixelCrop || !imgRef.current) return;
    setBusy(true);
    try {
      const outputType = file.mediaType === 'image/png' ? 'image/png' : 'image/jpeg';
      const blob = await getCroppedBlob(imgRef.current, pixelCrop, outputType);
      const base64 = await blobToBase64(blob);
      const previewUrl = URL.createObjectURL(blob);
      onApply({ base64, previewUrl, mediaType: outputType });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={onCancel}
    >
      <div
        className="rounded-md border w-full max-w-2xl flex flex-col"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)', maxHeight: '90vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="px-4 py-3 border-b flex items-center justify-between flex-shrink-0"
          style={{ borderColor: 'var(--border)' }}
        >
          <span className="text-sm font-medium truncate pr-4">Cắt ảnh — {file.fileName}</span>
          <button
            onClick={onCancel}
            aria-label="Đóng"
            style={{ color: 'var(--text-secondary)' }}
            className="flex-shrink-0"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4 flex items-center justify-center" style={{ background: 'var(--background)' }}>
          <ReactCrop crop={crop} onChange={(c) => setCrop(c)} onComplete={(c) => setPixelCrop(c)}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              ref={imgRef}
              src={file.previewUrl}
              alt={file.fileName}
              onLoad={onImageLoad}
              style={{ maxHeight: '60vh', display: 'block' }}
            />
          </ReactCrop>
        </div>

        <div
          className="px-4 py-3 border-t flex items-center justify-between gap-2 flex-shrink-0"
          style={{ borderColor: 'var(--border)' }}
        >
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Kéo góc/cạnh khung để chỉnh vùng cắt tự do.
          </span>
          <div className="flex gap-2">
            <button
              onClick={onCancel}
              className="text-xs px-3 py-1.5 rounded border"
              style={{ borderColor: 'var(--border)', color: 'var(--foreground)' }}
            >
              Hủy
            </button>
            <button
              onClick={handleApply}
              disabled={busy || !pixelCrop}
              className="text-xs px-3 py-1.5 rounded flex items-center gap-1 font-medium"
              style={{
                background: 'var(--accent)',
                color: 'var(--background)',
                opacity: busy || !pixelCrop ? 0.6 : 1,
              }}
            >
              {busy ? <Loader2 size={12} className="spin" /> : <Check size={12} />}
              {busy ? 'Đang cắt...' : 'Áp dụng'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}