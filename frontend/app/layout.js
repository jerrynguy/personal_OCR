import './globals.css';
import Nav from '@/components/Nav';

export const metadata = {
  title: 'Số hóa Lưu trữ',
  description: 'Số hóa hồ sơ lưu trữ theo Thông tư 05/2025/TT-BNV — chạy offline',
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body className="min-h-screen">
        <Nav />
        <main className="mx-auto max-w-[1600px] px-4 py-4">{children}</main>
      </body>
    </html>
  );
}
