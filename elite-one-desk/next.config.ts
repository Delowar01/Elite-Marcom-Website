import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Hostinger VPS (PM2 / systemd).
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // Uploads are re-encoded to WebP with fixed derivative widths at upload time
  // (see src/lib/media/process.ts) and served with srcset, so the built-in
  // optimiser would only add a second, slower cache in front of our own.
  images: { unoptimized: true },
  eslint: { dirs: ["src", "scripts"] },
  experimental: {
    // Server Actions receive uploads; the media validator enforces the real cap.
    serverActions: { bodySizeLimit: "12mb" },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-DNS-Prefetch-Control", value: "on" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
        ],
      },
      {
        source: "/fonts/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
      {
        source: "/brand/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
    ];
  },
};

export default nextConfig;
