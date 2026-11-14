import type { NextConfig } from "next";
const config: NextConfig = {
  outputFileTracingRoot: process.cwd(),
  output: process.env.DOCKER_BUILD === "1" ? "standalone" : undefined,
  experimental: { cpus: 1 },
  poweredByHeader: false,
};
export default config;

