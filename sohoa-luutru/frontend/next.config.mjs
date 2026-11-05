/** Xuất ra file tĩnh (thư mục out/) để backend Python phục vụ trực tiếp — không cần server Node. */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
