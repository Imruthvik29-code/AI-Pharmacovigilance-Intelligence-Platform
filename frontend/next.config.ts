import type { NextConfig } from "next";

/**
 * Browser calls stay same-origin (`/api/v1/...`).
 * Next.js rewrites those to the FastAPI process.
 *
 * BACKEND_URL is server-side only. Do not expose DATABASE_URL,
 * service-role keys, or LLM keys here.
 */
function backendOrigin(): string {
  const raw = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  return raw.replace(/\/$/, "");
}

const nextConfig: NextConfig = {
  allowedDevOrigins: ["*.e2b.app"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin()}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
