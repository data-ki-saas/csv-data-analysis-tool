import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// "/" is the public marketing page; everything else needs auth unless listed here.
const GUEST_ONLY_PATHS = ["/login", "/signup"];
// Public for everyone, including a signed-in visitor -- unlike GUEST_ONLY_PATHS,
// a logged-in user hitting their own (or someone else's) share link must NOT be
// bounced to /dashboard.
const SHARE_PATH_PREFIX = "/share/";

export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  const { data: { user } } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  const isGuestOnlyPath = GUEST_ONLY_PATHS.some((path) => pathname.startsWith(path));
  const isSharePath = pathname.startsWith(SHARE_PATH_PREFIX);
  const isPublicPath = pathname === "/" || isGuestOnlyPath || isSharePath;

  if (!user && !isPublicPath) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Signed-in users don't need the marketing page or the sign-in/sign-up forms.
  if (user && (pathname === "/" || isGuestOnlyPath)) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return response;
}
