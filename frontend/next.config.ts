import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    unoptimized: true,
  },
  // Host-based rewrite: on the public production domain (snugd.ai) serve
  // the marketing landing at root instead of the search app. Vercel applies
  // these rewrites in its routing layer BEFORE looking up the static HTML
  // cache, so this works for prerendered routes (middleware does not).
  // qa.snugd.ai and local dev are not matched, so they keep serving the
  // search app at `/` for beta testers.
  async rewrites() {
    // Return the object form so the rewrite runs in `beforeFiles` — BEFORE
    // Next.js's filesystem routing. The plain-array form runs in `afterFiles`,
    // which is too late: `app/page.tsx` exists and would already have matched
    // `/`, so the rewrite would never fire.
    return {
      beforeFiles: [
        {
          source: "/",
          has: [
            {
              type: "host",
              value: "(www\\.)?snugd\\.ai",
            },
          ],
          destination: "/landing",
        },
      ],
      afterFiles: [],
      fallback: [],
    };
  },
};

export default nextConfig;
