// Gọi backend (FastAPI, chỉ nghe 127.0.0.1).
// - Chạy thử bằng `npm run dev` (cổng 3000): gọi http://127.0.0.1:8765, backend chạy --dev (không token).
// - Bản đóng gói: backend phục vụ luôn giao diện (cùng địa chỉ); token được Electron truyền qua
//   phần "#token=..." của địa chỉ, lưu vào sessionStorage rồi xóa khỏi thanh địa chỉ.

const DEV_API = 'http://127.0.0.1:8765';

export function apiBase() {
  if (typeof window === 'undefined') return '';
  return window.location.port === '3000' ? DEV_API : '';
}

export function getToken() {
  if (typeof window === 'undefined') return '';
  try {
    const m = window.location.hash.match(/token=([^&]+)/);
    if (m) {
      sessionStorage.setItem('sohoa_token', decodeURIComponent(m[1]));
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
    return sessionStorage.getItem('sohoa_token') || '';
  } catch {
    return '';
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'X-Token': getToken() };
  let payload = body;
  if (body !== undefined && !(body instanceof FormData) && !(body instanceof Blob)) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(apiBase() + '/api' + path, { method, headers, body: payload });
  } catch {
    throw new Error('Không kết nối được backend. Backend đã chạy chưa?');
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

/** Đường dẫn dùng trực tiếp trong <img src> / tải file (token đi theo ?token=). */
export function fileUrl(path) {
  const t = getToken();
  return apiBase() + '/api' + path + (t ? (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(t) : '');
}

/** Tải file lên có báo tiến độ (fetch không báo được tiến độ tải lên nên dùng XHR). */
export function upload(path, file, { method = 'POST', raw = false, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, apiBase() + '/api' + path);
    xhr.setRequestHeader('X-Token', getToken());
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error(data?.detail || `Lỗi ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error('Mất kết nối khi tải file lên'));
    if (raw) {
      xhr.send(file);
    } else {
      const fd = new FormData();
      fd.append('file', file);
      xhr.send(fd);
    }
  });
}

export function fmtSeconds(s) {
  if (s == null) return '';
  if (s < 60) return `${Math.round(s)} giây`;
  return `${Math.floor(s / 60)} phút ${Math.round(s % 60)} giây`;
}

/** Bỏ dấu, viết thường — để so khớp chữ trên ảnh với giá trị trường. */
export function plain(s) {
  return (s || '')
    .toString()
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9/ ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Thời lượng dài (hàng đợi chạy qua đêm): "2 giờ 15 phút", "45 phút", "30 giây". */
export function fmtDuration(s) {
  if (s == null) return '';
  if (s < 60) return `${Math.round(s)} giây`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  if (h >= 24) return `${Math.floor(h / 24)} ngày ${h % 24} giờ`;
  return h ? `${h} giờ ${m} phút` : `${m} phút`;
}

/** Giờ xong dự kiến: "14:30" (hôm nay) / "07:10 ngày 08/11". */
export function fmtFinish(s) {
  if (!s) return '';
  const t = new Date(Date.now() + s * 1000);
  const hm = t.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
  return t.toDateString() === new Date().toDateString()
    ? hm
    : `${hm} ngày ${String(t.getDate()).padStart(2, '0')}/${String(t.getMonth() + 1).padStart(2, '0')}`;
}

/** Tham số truy vấn: bỏ giá trị rỗng. */
export function qs(params) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && p.set(k, v));
  const s = p.toString();
  return s ? `?${s}` : '';
}

/** Tải file về bằng fetch (báo lỗi ngay trên trang thay vì mở trang lỗi), giữ tên file backend đặt. */
export async function download(path) {
  let res;
  try {
    res = await fetch(apiBase() + '/api' + path, { headers: { 'X-Token': getToken() } });
  } catch {
    throw new Error('Không kết nối được backend. Backend đã chạy chưa?');
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail || msg;
    } catch {}
    throw new Error(msg);
  }
  const cd = res.headers.get('content-disposition') || '';
  const m = cd.match(/filename\*=utf-8''([^;]+)/i) || cd.match(/filename="([^"]+)"/i);
  const name = m ? decodeURIComponent(m[1]) : 'tai_ve';
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  return name;
}
