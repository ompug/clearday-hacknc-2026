import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  poweredByHeader: false,
  // scripts/dev.sh --e2e runs a second dev server from this folder; it needs its own build dir.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
