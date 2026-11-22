/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output keeps the container image small (Phase 14 Dockerfile).
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
