import type { NextConfig } from "next";

const config: NextConfig = {
  outputFileTracingRoot: process.cwd(),
  output: process.env.DOCKER_BUILD === "1" ? "standalone" : undefined,
  experimental: { cpus: 1 },
  poweredByHeader: false,
  async rewrites() {
    const backendUrl = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL;
    if (backendUrl && (backendUrl.startsWith("http://") || backendUrl.startsWith("https://"))) {
      const target = backendUrl.replace(/\/+$/, "");
      return [
        {
          source: "/api/v1/:path*",
          destination: `${target}/:path*`,
        },
      ];
    }
    return [];
  },
};

export default config;

