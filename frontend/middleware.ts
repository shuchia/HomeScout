import { NextResponse, type NextRequest } from 'next/server';

/**
 * On the production domain (snugd.ai) we want the root URL to serve the
 * marketing landing page, NOT the in-app search experience. The backend
 * api.snugd.ai is currently dormant, so showing the search UI to a
 * cold visitor would render a broken-looking app.
 *
 * Beta testers reach the actual app via qa.snugd.ai, which keeps its root
 * pointed at the search UI (no rewrite applied).
 */
export function middleware(request: NextRequest) {
  const host = request.headers.get('host') ?? '';
  const isProdHost = host === 'snugd.ai' || host === 'www.snugd.ai';
  const pathname = request.nextUrl.pathname;

  if (isProdHost && pathname === '/') {
    const url = request.nextUrl.clone();
    url.pathname = '/landing';
    return NextResponse.rewrite(url);
  }

  return NextResponse.next();
}

// Only run the middleware on the root path; everything else (assets, _next,
// API routes, sub-routes) skips it for free.
export const config = {
  matcher: '/',
};
