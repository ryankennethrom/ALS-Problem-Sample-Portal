import type { NextConfig } from 'next';

const backendApiUrl = (
  process.env.BACKEND_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000/api'
).replace(/\/+$/, '');

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/backend-api/:path*',
        destination: `${backendApiUrl}/:path*/`,
      },
    ];
  },
  async headers() {
    return [{ source: '/track/:path*', headers: [
      { key: 'Referrer-Policy', value: 'no-referrer' },
      { key: 'Cache-Control', value: 'no-store' },
    ] }];
  },
};
export default nextConfig;
