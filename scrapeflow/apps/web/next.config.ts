import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // Playwright drives the dev server through 127.0.0.1 while Next defaults to
  // localhost; without this, dev-only HMR resources are blocked cross-origin.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
