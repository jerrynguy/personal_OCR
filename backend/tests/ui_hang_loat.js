// Kiểm thử giao diện: nhập thư mục -> hàng đợi -> danh sách -> soát; PDF dài -> gợi ý -> tách.
// Cần server_gia.py đang chạy ở cổng 8765 với data trống, và Playwright:
//     node tests/ui_hang_loat.js <thư mục dữ liệu thử> <thư mục lưu ảnh chụp>
const { chromium } = require('playwright');
const path = require('path');

const BASE = 'http://127.0.0.1:8765';
const TESTDATA = path.resolve(process.argv[2]);
const SHOTS = path.resolve(process.argv[3] || 'anh_kiem_thu');
const fs = require('fs');
fs.mkdirSync(SHOTS, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));
  const shot = (name) => page.screenshot({ path: path.join(SHOTS, name + '.png') });

  // trang đầu khi chưa có hồ sơ
  await page.goto(BASE + '/');
  await page.getByText('Nhập cả một thư mục hàng trăm file').waitFor();
  await shot('a-trang-dau');

  // nhập thư mục
  await page.getByRole('link', { name: 'Nhập thư mục' }).click();
  await page.getByPlaceholder('D:\\Số hóa\\Đà Lạt 1L').fill(path.join(TESTDATA, 'Đà Lạt 1L'));
  await page.getByRole('button', { name: 'Đọc thư mục' }).click();
  await page.getByText('Tìm thấy').waitFor();
  await page.getByText('có vẻ là bản gộp của các file khác').waitFor();
  await shot('b-xem-truoc');
  // mở thư mục 1 xem file
  const row1 = page.locator('tr', { has: page.locator('td', { hasText: /^1$/ }) }).first();
  await row1.locator('button').first().click();
  await page.getByText('có vẻ là bản gộp của: H01.15.01.100001.pdf + H01.15.01.100002.pdf').waitFor();
  await shot('c-file-gop');
  await page.getByRole('button', { name: /Bỏ tích 2 file gợi ý gộp/ }).click();
  const btn = page.getByRole('button', { name: /Tạo 7 hồ sơ và xếp hàng xử lý/ });
  await btn.waitFor();
  console.log('nút tạo bật:', await btn.isEnabled());
  // thông tin chung
  await page.getByText('Thông tin chung cho mọi hồ sơ trong lô').click();
  await shot('d-thong-tin-chung');
  await btn.click();
  await page.getByText('Đã tạo 7 hồ sơ').waitFor();
  await shot('e-da-tao');
  await page.getByRole('link', { name: /Xem các hồ sơ của lô/ }).click();
  await page.getByText('hồ sơ đang chờ').waitFor();
  await page.waitForTimeout(1500);
  await shot('f-hang-doi');

  // tạm dừng / chạy tiếp
  await page.getByRole('button', { name: 'Tạm dừng' }).first().click();
  await page.getByText('Hàng đợi đang tạm dừng').waitFor();
  await shot('g-tam-dung');
  await page.getByRole('button', { name: 'Chạy tiếp' }).first().click();
  await page.getByText('Đang xử lý', { exact: false }).first().waitFor();

  // chờ xong
  for (let i = 0; i < 120; i++) {
    const n = await page.locator('text=hồ sơ đang chờ').count();
    const running = await page.locator('tbody >> text=Đang xử lý').count();
    const waiting = await page.locator('tbody >> text=Đang chờ').count();
    if (!n && !running && !waiting) break;
    await page.waitForTimeout(1000);
  }
  await page.waitForTimeout(1000);
  await shot('h-danh-sach-xong');

  // mở hồ sơ thư mục 1
  await page.getByText('H01.15.01', { exact: true }).click();
  await page.getByText('Soát tài liệu (2)').waitFor();
  await page.waitForTimeout(800);
  await shot('i-soat');
  await page.getByRole('button', { name: 'Tách văn bản' }).click();
  await page.getByText('Mỗi file 1 tài liệu').waitFor();
  await page.waitForTimeout(800);
  await shot('j-tach-thu-muc');

  // PDF dài: tạo + tải lên bằng API
  const ctx = page.request;
  const created = await (await ctx.post(BASE + '/api/ho-so', { data: { ho_so: { ma_ho_so: 'HS-DAI-01' } } })).json();
  await ctx.post(BASE + `/api/ho-so/${created.id}/pdf`, {
    multipart: { file: { name: 'ho_so_dai.pdf', mimeType: 'application/pdf', buffer: fs.readFileSync(path.join(TESTDATA, 'ho_so_dai.pdf')) } },
  });
  await page.goto(BASE + `/ho-so/?id=${created.id}&tab=tach`);
  await page.getByRole('button', { name: 'Đọc chữ để gợi ý' }).waitFor();
  await page.waitForTimeout(1000);
  await shot('k-dai-chua-doc');
  await page.getByRole('button', { name: 'Đọc chữ để gợi ý' }).click();
  await page.getByText(/App gợi ý \d+ trang/).waitFor({ timeout: 60000 });
  await page.waitForTimeout(1500);
  await shot('l-dai-goi-y');
  // phím tắt: N tới gợi ý kế tiếp, Space đánh dấu
  await page.keyboard.press('n');
  await page.keyboard.press(' ');
  await page.waitForTimeout(300);
  const docs1 = await page.locator('text=/^\\d+ tài liệu/').first().innerText().catch(() => '');
  console.log('sau N + Space:', await page.locator('.card b').first().innerText());
  await page.getByRole('button', { name: /Đánh dấu cả \d+ trang gợi ý/ }).click();
  await page.getByRole('button', { name: 'Lớn' }).click();
  await page.waitForTimeout(800);
  await shot('m-dai-da-danh-dau-lon');
  await page.getByRole('button', { name: 'Nhỏ' }).click();
  await page.waitForTimeout(800);
  await shot('n-dai-nho');
  console.log('số tài liệu:', await page.locator('.card b').first().innerText());
  await page.getByRole('button', { name: 'Xử lý', exact: true }).click();
  await page.getByText(/Soát tài liệu \(14\)/).waitFor({ timeout: 60000 });
  console.log('đã xử lý 14 tài liệu');

  // xuất Excel gộp từ danh sách
  await page.goto(BASE + '/?lo=' + encodeURIComponent('Đà Lạt 1L'));
  await page.getByText('Excel gộp (1 file)').waitFor();
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByText('Excel gộp (1 file)').click()]);
  console.log('tải về:', dl.suggestedFilename());
  const [dl2] = await Promise.all([page.waitForEvent('download'), page.getByText('Mỗi hồ sơ 1 file Excel (.zip)').click()]);
  console.log('tải về:', dl2.suggestedFilename());
  await shot('o-danh-sach-lo');

  console.log('lỗi console:', errors.length ? errors : 'không có');
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
