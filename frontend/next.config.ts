import type { NextConfig } from "next";

// The browser calls /api/*; Next forwards it to the FastAPI server, so no CORS setup is needed.
const API_URL = process.env.CITETAX_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
