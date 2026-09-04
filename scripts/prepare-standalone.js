// Next.js "standalone" output không tự copy .next/static và public/ (theo thiết kế
// của Next.js, để tránh trùng lặp khi deploy sau CDN). Với Electron thì cần có đủ
// 2 thư mục này bên trong .next/standalone để server tự phục vụ được, nên copy thủ công.
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const standaloneDir = path.join(root, '.next', 'standalone');

function copyDir(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

if (!fs.existsSync(standaloneDir)) {
  console.error('Không thấy .next/standalone — kiểm tra next.config.mjs có output: "standalone" chưa.');
  process.exit(1);
}

copyDir(path.join(root, '.next', 'static'), path.join(standaloneDir, '.next', 'static'));
copyDir(path.join(root, 'public'), path.join(standaloneDir, 'public'));

console.log('Đã copy .next/static và public/ vào .next/standalone/');
