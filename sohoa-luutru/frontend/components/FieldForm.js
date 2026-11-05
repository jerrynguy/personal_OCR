'use client';

// Form sinh từ danh sách trường trong tt05.json (backend /api/schema).
// Mỗi ô có nhãn nguồn: Luật / AI / Sửa tay / Từ hồ sơ / Tự tính.

const SOURCE = {
  luật: ['Luật', 'bg-emerald-50 text-emerald-700'],
  'luật (chưa chuẩn hóa)': ['Luật (thô)', 'bg-amber-50 text-amber-800'],
  LLM: ['AI', 'bg-violet-50 text-violet-700'],
  'sửa tay': ['Sửa tay', 'bg-blue-50 text-blue-700'],
  ke_thua_ho_so: ['Từ hồ sơ', 'bg-gray-100 text-gray-600'],
  tu_tinh: ['Tự tính', 'bg-gray-100 text-gray-600'],
};

const LONG = new Set(['trich_yeu_noi_dung', 'co_quan_ban_hanh', 'tu_khoa', 'ghi_chu', 'can_kiem_tra',
  'tieu_de_ho_so', 'lich_su_don_vi', 'phuong_an_phan_loai']);

export default function FieldForm({
  fields,
  values,
  onChange,
  sources = {},
  readOnly = false,
  readOnlyKeys = new Set(),
  onFocusField,
  cols = 2,
}) {
  return (
    <div className={`grid gap-x-4 gap-y-3 ${cols === 2 ? 'sm:grid-cols-2' : ''}`}>
      {fields.map((f) => {
        const src = sources[f.key] || (f.nguon === 'ke_thua_ho_so' || f.nguon === 'tu_tinh' ? f.nguon : '');
        const [srcLabel, srcCls] = SOURCE[src] || [];
        const disabled = readOnly || readOnlyKeys.has(f.key);
        const value = values?.[f.key] ?? '';
        const long = LONG.has(f.key);
        const common = {
          id: `f-${f.key}`,
          className: `input ${src === 'sửa tay' ? 'border-blue-300' : ''}`,
          value,
          disabled,
          onFocus: () => onFocusField?.(f.key),
          onChange: (e) => onChange?.(f.key, e.target.value),
        };
        return (
          <div key={f.key} className={long && cols === 2 ? 'sm:col-span-2' : ''}>
            <label htmlFor={`f-${f.key}`} className="label flex items-center gap-1.5">
              <span>{f.label}</span>
              {srcLabel && <span className={`badge ${srcCls}`}>{srcLabel}</span>}
            </label>
            {f.lua_chon ? (
              <select {...common}>
                <option value="" />
                {f.lua_chon.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : long ? (
              <textarea {...common} rows={f.key === 'trich_yeu_noi_dung' ? 3 : 2} />
            ) : (
              <input {...common} />
            )}
            {f.ghi_chu && <p className="mt-0.5 text-[11px] text-gray-400">{f.ghi_chu}</p>}
          </div>
        );
      })}
    </div>
  );
}
