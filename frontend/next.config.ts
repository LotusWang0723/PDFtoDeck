/** @type {import('next').NextConfig} */
const nextConfig = {
  // Remove 'export' for dev mode — enable API proxy
  // Set output: 'export' only for production Cloudflare Pages build
  ...(process.env.NODE_ENV === 'production' && process.env.CF_PAGES
    ? { output: 'export' }
    : {}),
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

export default nextConfig;
