import type { NextConfig } from "next";

const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// The browser-call demo streams audio over a WebSocket to the same backend.
const API_WS_ORIGIN = API_ORIGIN.replace(/^http/, "ws");

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
          // Microphone only for this origin (browser-call demo).
          { key: "Permissions-Policy", value: "microphone=(self), camera=(), geolocation=()" },
          {
            key: "Content-Security-Policy",
            value: `default-src 'self'; connect-src 'self' ${API_ORIGIN} ${API_WS_ORIGIN}; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'`,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
