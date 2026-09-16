import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export: Firebase Hosting serves the built HTML/JS from the CDN and
  // rewrites /api/** to the Cloud Run service (see firebase.json). No Node server
  // to run for the frontend. Revisit only if a page genuinely needs SSR.
  output: "export",
  reactStrictMode: true,
};

export default nextConfig;
