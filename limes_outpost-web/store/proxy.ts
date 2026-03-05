import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public routes through
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Check for access token in cookies (set on login)
  // We use a cookie here rather than localStorage because middleware
  // runs on the server — localStorage isn't available.
  // The auth flow sets this cookie alongside the localStorage token.
  const token = request.cookies.get("ff_access")?.value;

  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Protect everything except static files, API routes, and auth pages
    "/((?!_next/static|_next/image|favicon.ico|login|register).*)",
  ],
};
