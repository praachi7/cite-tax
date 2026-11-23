import type { NextConfig } from "next";

// The browser calls /api/*; Next forwards it to the FastAPI server, so no CORS setup is needed.
// The target is read when `next build` runs (the Docker image passes it as a build argument).
const API_URL = process.env.CITETAX_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Standalone output for the Docker image only: on Windows it needs symlink rights, so local builds skip it.
  output: process.env.NEXT_STANDALONE === "1" ? "standalone" : undefined,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
