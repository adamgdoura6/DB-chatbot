import type { NextConfig } from "next";

// The page calls /api/* on its own origin; Next forwards it to the FastAPI backend.
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // This folder is the app root (a stray lockfile higher up would otherwise be picked).
  turbopack: { root: __dirname },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
