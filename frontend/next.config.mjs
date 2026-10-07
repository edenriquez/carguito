/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    /**
     * Every previously shipped path lands somewhere real so no bookmark 404s.
     * `/statements` gets its Spanish successor; `/fijos`, `/pronostico` and
     * `/recurrentes` land on Plan, the view that absorbed both halves
     * (2026-09-05 IA audit) — Pronóstico on its own face. Everything older —
     * English (pre-F3) and Spanish (F3–F7) — lands on the root.
     */
    async redirects() {
        return [
            { source: "/statements", destination: "/documentos", permanent: false },
            { source: "/fijos", destination: "/plan", permanent: false },
            { source: "/pronostico", destination: "/plan?cara=ingresos", permanent: false },
            { source: "/recurrentes", destination: "/", permanent: false },
            { source: "/categorias", destination: "/", permanent: false },
            { source: "/precios", destination: "/", permanent: false },
            ...[
            "/dashboard",
            "/transactions",
            "/settings",
            "/spending",
            "/forecasts",
            "/inicio/:path*",
            "/movimientos",
            "/ajustes",
            "/w/:path*",
            "/kitchen-sink",
            ].map((source) => ({ source, destination: "/", permanent: false })),
        ];
    },
};

export default nextConfig;
