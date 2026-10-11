/** @type {import('next').NextConfig} */
const apiOrigin = (() => {
  try {
    return new URL(
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
    ).origin;
  } catch {
    return "http://localhost:8000";
  }
})();

const nextConfig = {
  reactStrictMode: true,
  // MSW's `msw/browser` entry is browser-only ("node": null in exports).
  // Keep it out of the server bundle; it only ever runs in a client effect.
  experimental: { serverComponentsExternalPackages: ["msw"] },
  // Same-origin API proxy: the browser must never call the gateway/RAG
  // directly (their ports aren't public and CSP would block them). Client
  // code uses relative URLs (NEXT_PUBLIC_API_URL empty) and Next forwards
  // server-side to the gateway. INTERNAL_API_URL is server-only.
  async rewrites() {
    const api =
      process.env.INTERNAL_API_URL ?? "http://localhost:8003";
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/openapi.json", destination: `${api}/openapi.json` },
    ];
  },
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
            // connect-src follows the configured API origin (this box runs
            // the API on :8003, not the :8000 default) + RAG for SSE traces.
            value:
              `default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://apis.google.com; style-src 'self' 'unsafe-inline'; connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://www.googleapis.com ${apiOrigin} http://localhost:8000 http://localhost:8001; img-src 'self' data:; frame-src https://*.firebaseapp.com https://accounts.google.com;`,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
