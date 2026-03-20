/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export', // Static export for Cloudflare Pages
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
