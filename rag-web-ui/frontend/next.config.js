const backendUrl = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
module.exports = {
  async redirects() {
    return [
      {
        source: "/login",
        destination: "/dashboard/knowledge",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/chat",
        destination: `${backendUrl}/api/chat`,
      },
      {
        source: "/api/chat/:path*",
        destination: `${backendUrl}/api/chat/:path*`,
      },
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  output: "standalone",
  experimental: {
    // This is needed for standalone output to work correctly
    outputFileTracingRoot: undefined,
    outputStandalone: true,
    skipMiddlewareUrlNormalize: true,
    skipTrailingSlashRedirect: true,
  },
};
