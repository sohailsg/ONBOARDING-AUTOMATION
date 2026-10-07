import { NextResponse, type NextRequest } from "next/server";

const ROLE_COOKIE = "ob_role"; // MVP: set by /login (SSO stub). Prod: JWT in httpOnly cookie.

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const role = req.cookies.get(ROLE_COOKIE)?.value;

  if (pathname.startsWith("/hub")) {
    if (!role) {
      return NextResponse.redirect(new URL("/login?next=/hub", req.url));
    }
    // employees + hr_admin may view hub; service key never
    if (role !== "employee" && role !== "hr_admin") {
      return NextResponse.redirect(new URL("/login?error=forbidden", req.url));
    }
  }
  if (pathname.startsWith("/admin")) {
    if (role !== "hr_admin") {
      return NextResponse.redirect(new URL("/login?next=/admin", req.url));
    }
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/hub/:path*", "/admin/:path*"],
};
