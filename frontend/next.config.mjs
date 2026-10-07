/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // MSW's `msw/browser` entry is browser-only ("node": null in exports).
  // Keep it out of the server bundle; it only ever runs in a client effect.
  experimental: { serverComponentsExternalPackages: ["msw"] },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://localhost:8000 http://localhost:8001; img-src 'self' data:;",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
