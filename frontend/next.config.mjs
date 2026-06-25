/** @type {import('next').NextConfig} */

// El panel llama al API en otro origen (NEXT_PUBLIC_API_URL, p.ej. :8002 en
// local o la URL de Render). Hay que permitirlo en connect-src de la CSP.
const apiOrigin = process.env.NEXT_PUBLIC_API_URL || "";
const connectSrc = ["'self'", apiOrigin].filter(Boolean).join(" ");

const nextConfig = {
  reactStrictMode: true,
  // Servidor Node autocontenido (server.js) — patrón oficial para Docker/Render.
  output: "standalone",
  images: { unoptimized: true },

  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            // Next inyecta scripts/estilos inline al hidratar → unsafe-inline/eval.
            // connect-src incluye el origen del API para que el login conecte.
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              `connect-src ${connectSrc}`,
              "font-src 'self' data:",
              "media-src 'self' https: blob:",
              "frame-ancestors 'none'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
