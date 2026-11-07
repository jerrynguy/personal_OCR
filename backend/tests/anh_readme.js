// Ảnh chụp màn hình có đánh số ①②… cho README (cùng kiểu ảnh cũ: viền hồng + số trong vòng tròn đỏ).
// Cần server_gia.py đang chạy ở cổng 8765 với data TRỐNG (vd. giây OCR 0.25, giây AI 1.0):
//     node tests/anh_readme.js <thư mục dữ liệu thử>      -> ghi đè docs/images/12..16-*.png
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE = 'http://127.0.0.1:8765';
const OUT = path.resolve(__dirname, '../../docs/images');
const SRC = path.resolve(process.argv[2]);
// PDF dài được tải lên với tên H01.15.20.pdf -> OCR giả cần đáp án cùng tên
fs.copyFileSync(path.join(SRC, 'ho_so_dai.truth.json'), path.join(SRC, 'H01.15.20.truth.json'));
const LINUX_ROOT = SRC; // đổi thành đường dẫn kiểu Windows khi chụp
const WIN_ROOT = 'D:\\Số hóa';

async function annotate(page, marks) {
  await page.evaluate(
    ({ marks, linuxRoot, winRoot }) => {
      // đường dẫn trên máy thử -> đường dẫn kiểu Windows cho dễ hiểu
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const fix = (s) => s.split(linuxRoot).join(winRoot).replace(/(D:\\Số hóa[^·\n"]*)/g, (m) => m.replace(/\//g, '\\'));
      while (walker.nextNode()) if (walker.currentNode.nodeValue.includes(linuxRoot)) walker.currentNode.nodeValue = fix(walker.currentNode.nodeValue);
      document.querySelectorAll('input').forEach((i) => i.value.includes(linuxRoot) && (i.value = fix(i.value)));
      document.querySelectorAll('[title]').forEach((e) => e.title.includes(linuxRoot) && (e.title = fix(e.title)));
      document.querySelectorAll('.anno').forEach((e) => e.remove());
      marks.forEach(([sel, n, nth]) => {
        const els = [...document.querySelectorAll(sel.css || '*')].filter((e) =>
          sel.text ? e.textContent.trim().startsWith(sel.text) && ![...e.querySelectorAll(sel.css)].some((c) => c.textContent.trim().startsWith(sel.text)) : true,
        );
        let el = els[nth || 0];
        if (!el) throw new Error('không thấy ' + JSON.stringify(sel));
        if (sel.up) for (let k = 0; k < sel.up; k++) el = el.parentElement;
        el.style.outline = '3px solid #e11d48';
        el.style.outlineOffset = '2px';
        const r = el.getBoundingClientRect();
        const b = document.createElement('div');
        b.className = 'anno';
        b.textContent = n;
        Object.assign(b.style, {
          position: 'absolute', left: `${r.left + window.scrollX - 13}px`, top: `${r.top + window.scrollY - 13}px`,
          width: '26px', height: '26px', borderRadius: '50%', background: '#e11d48', color: 'white', zIndex: 9999,
          font: 'bold 15px Segoe UI, Arial, sans-serif', display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 0 0 2px white',
        });
        document.body.appendChild(b);
      });
    },
    { marks, linuxRoot: LINUX_ROOT, winRoot: WIN_ROOT },
  );
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const shot = async (name, clipH) => {
    await page.waitForTimeout(600); // nút có hiệu ứng đổi màu viền: chờ xong mới chụp
    await page.screenshot({ path: path.join(OUT, name), clip: { x: 0, y: 0, width: 1440, height: clipH } });
  };

  // ---------------------------------------------------------------- nhập thư mục
  await page.goto(BASE + '/nhap/');
  await page.getByPlaceholder('D:\\Số hóa\\Đà Lạt 1L').fill(path.join(SRC, 'Đà Lạt 1L'));
  await page.getByRole('button', { name: 'Đọc thư mục' }).click();
  await page.getByText('có vẻ là bản gộp của các file khác').waitFor();
  const row1 = page.locator('tr', { has: page.locator('td', { hasText: /^1$/ }) }).first();
  await row1.locator('button').first().click();
  await page.getByText('có vẻ là bản gộp của: H01.15.01.100001.pdf').waitFor();
  await annotate(page, [
    [{ css: 'button', text: 'Chọn thư mục' }, '1'],
    [{ css: 'button', text: 'Bỏ tích 2 file' }, '2'],
    [{ css: 'tbody tr td input.input' }, '3'],
    [{ css: 'tbody tr td button' }, '4'],
    [{ css: 'span.badge', text: '⚠ có vẻ là bản gộp của:' }, '5'],
  ]);
  await shot('12-nhap-thu-muc.png', 860);

  await page.getByRole('button', { name: /Bỏ tích 2 file gợi ý gộp/ }).click();
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(300);
  const top = await page.evaluate(() => document.querySelector('label.label').closest('.card').getBoundingClientRect().top + window.scrollY - 16);
  await annotate(page, [
    [{ css: 'input.input', }, '1', 0],
    [{ css: 'summary', text: 'Thông tin chung cho mọi hồ sơ' }, '2'],
    [{ css: 'label', text: 'Bỏ qua AI cho nhanh' }, '3'],
    [{ css: 'button', text: 'Tạo 7 hồ sơ' }, '4'],
  ]);
  // ô số 1 là "Tên lô": đánh lại đúng ô
  await page.evaluate(() => {
    const lo = [...document.querySelectorAll('label.label')].find((l) => l.textContent.startsWith('Tên lô')).nextElementSibling;
    const first = document.querySelector('.anno');
    document.querySelectorAll('input.input')[0].style.outline = '';
    lo.style.outline = '3px solid #e11d48';
    lo.style.outlineOffset = '2px';
    const r = lo.getBoundingClientRect();
    first.style.left = `${r.left + window.scrollX - 13}px`;
    first.style.top = `${r.top + window.scrollY - 13}px`;
  });
  await page.waitForTimeout(600);
  const h = await page.evaluate(() => document.body.scrollHeight);
  await page.screenshot({ path: path.join(OUT, '13-nhap-tao.png'), fullPage: true, clip: { x: 0, y: top, width: 1440, height: Math.min(330, h - top) } });

  await page.getByRole('button', { name: /Tạo 7 hồ sơ/ }).click();
  await page.getByText('Đã tạo 7 hồ sơ').waitFor();
  await page.getByRole('link', { name: /Xem các hồ sơ của lô/ }).click();
  await page.getByText('Đang xử lý H01').waitFor();
  await page.waitForTimeout(2500);
  await annotate(page, [
    [{ css: 'button', text: 'Tạm dừng' }, '1'],
    [{ css: 'select' }, '2', 0],
    [{ css: 'button', text: 'Excel gộp (1 file)' }, '3'],
    [{ css: 'button', text: 'Mỗi hồ sơ 1 file' }, '4'],
    [{ css: 'button', text: 'Chạy AI phần còn thiếu' }, '5'],
  ]);
  await shot('14-hang-doi.png', 720);

  // ---------------------------------------------------------------- PDF dài
  const created = await (await page.request.post(BASE + '/api/ho-so', { data: { ho_so: { ma_ho_so: 'H01.15.20', tieu_de_ho_so: 'Hồ sơ nhiều tài liệu trong 1 file' } } })).json();
  await page.request.post(BASE + `/api/ho-so/${created.id}/pdf`, {
    multipart: { file: { name: 'H01.15.20.pdf', mimeType: 'application/pdf', buffer: fs.readFileSync(path.join(SRC, 'ho_so_dai.pdf')) } },
  });
  // chờ lô xong để hồ sơ này được đọc ngay
  for (let i = 0; i < 200; i++) {
    const q = await (await page.request.get(BASE + '/api/hang-doi')).json();
    if (!q.dang_chay && !q.so_cho) break;
    await page.waitForTimeout(1000);
  }
  await page.goto(BASE + `/ho-so/?id=${created.id}&tab=tach`);
  await page.getByRole('button', { name: 'Đọc chữ để gợi ý' }).waitFor();
  await page.waitForTimeout(800);
  await annotate(page, [[{ css: 'button', text: 'Đọc chữ để gợi ý' }, '1']]);
  await shot('15-file-dai-doc-chu.png', 560);
  await page.getByRole('button', { name: 'Đọc chữ để gợi ý' }).click();
  await page.getByText(/App gợi ý \d+ trang nữa/).waitFor({ timeout: 60000 });
  await page.waitForTimeout(1500);
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(200);
  await annotate(page, [
    [{ css: 'button', text: 'Đánh dấu cả' }, '1'],
    [{ css: 'span.badge', text: 'Gợi ý' }, '2', 0],
    [{ css: 'button', text: 'Nhỏ' }, '3', 0],
    [{ css: 'span', text: 'Phím tắt' }, '4'],
  ]);
  // số 3: cả cụm chọn cỡ ảnh
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Nhỏ');
    btn.style.outline = '';
    const grp = btn.parentElement;
    grp.style.outline = '3px solid #e11d48';
    grp.style.outlineOffset = '2px';
    const a = [...document.querySelectorAll('.anno')].find((x) => x.textContent === '3');
    const r = grp.getBoundingClientRect();
    a.style.left = `${r.left + window.scrollX - 13}px`;
    a.style.top = `${r.top + window.scrollY - 13}px`;
    // số 2: viền cả trang được gợi ý
    const s = [...document.querySelectorAll('span.badge')].find((x) => x.textContent === 'Gợi ý');
    s.style.outline = '';
  });
  await shot('16-file-dai-goi-y.png', 760);

  await browser.close();
  console.log('xong');
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
