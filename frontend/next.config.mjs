/** @type {import('next').NextConfig} */

// El panel llama al API en otro origen (NEXT_PUBLIC_API_URL, p.ej. :8002 en
// local o la IP/URL de produccion). Hay que permitirlo en connect-src de la CSP.
const apiOrigin = process.env.NEXT_PUBLIC_API_URL || "";
const connectSrc = ["'self'", apiOrigin].filter(Boolean).join(" ");

// Dos destinos de build:
//   NEXT_OUTPUT=export → HTML estatico en out/ (Firebase Hosting). El panel es
//     100% cliente (todas las paginas "use client", token en localStorage), asi
//     que no se pierde nada. Las cabeceras las sirve Firebase (firebase.json).
//   por defecto        → standalone (server.js) para Docker/Render.
const isExport = process.env.NEXT_OUTPUT === "export";

const nextConfig = {
  reactStrictMode: true,
  output: isExport ? "export" : "standalone",
  images: { unoptimized: true },

  // headers() no existe en el export estatico (no hay servidor Node que las
  // emita); en ese modo las define firebase.json con el mismo contenido.
  ...(isExport
    ? {}
    : {
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
      }),
};

export default nextConfig;
