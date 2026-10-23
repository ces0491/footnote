import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A self-contained server for the container image (see Dockerfile).
  output: "standalone",
  poweredByHeader: false,
  // `next dev` would otherwise write an AGENTS.md for coding agents into the project.
  agentRules: false,
  // Loaded from node_modules at run time instead of bundled. @azure/identity pulls in `open`, whose
  // literal Windows paths break Turbopack's bundling; pg has optional native bindings.
  serverExternalPackages: ["@azure/identity", "@azure/web-pubsub", "pg"],
  cacheComponents: true,
  partialPrefetching: true,
  // On every response: HTTPS only once a browser has seen the site, no guessing at content types, no
  // framing by another site (which could dress the producer's buttons up as its own), and only the
  // origin in the Referer sent to other sites.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Strict-Transport-Security", value: "max-age=31536000" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
