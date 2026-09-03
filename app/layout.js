import './globals.css';
import Link from 'next/link';

export const metadata = {
  title: 'Document Scanner',
  description: 'Quét và trích xuất thông tin từ ảnh tài liệu đa ngôn ngữ bằng Claude API',
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <nav
          className="flex items-center gap-4 px-6 py-2 text-xs border-b"
          style={{
            borderColor: 'var(--border)',
            background: 'var(--surface)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          <Link href="/" className="hover:underline" style={{ color: 'inherit' }}>
            Quét tài liệu
          </Link>
          <span>·</span>
          <Link href="/muc-luc" className="hover:underline" style={{ color: 'inherit' }}>
            Mục lục lưu trữ
          </Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
