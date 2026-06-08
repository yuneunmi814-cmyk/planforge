/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export → produces ./out, which Tauri serves as frontendDist.
  output: "export",
  // Tauri serves files directly; relative asset paths avoid absolute-root issues.
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
