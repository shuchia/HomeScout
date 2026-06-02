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
const PROD_HOSTS = new Set(['snugd.ai', 'www.snugd.ai']);

export function middleware(request: NextRequest) {
  // On Vercel, the public host may land in `x-forwarded-host` instead of the
  // `host` header. Check both. Strip any port suffix just in case.
  const forwardedHost = request.headers.get('x-forwarded-host') ?? '';
  const host = request.headers.get('host') ?? '';
  const publicHost = (forwardedHost || host).split(':')[0].toLowerCase();

  if (PROD_HOSTS.has(publicHost) && request.nextUrl.pathname === '/') {
    const url = request.nextUrl.clone();
    url.pathname = '/landing';
    return NextResponse.rewrite(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: '/',
};
