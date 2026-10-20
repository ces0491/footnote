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
