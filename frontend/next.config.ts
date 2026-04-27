import type { NextConfig } from "next";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "https://backend-wine-eight-21.vercel.app";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
