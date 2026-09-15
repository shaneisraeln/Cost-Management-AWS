import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Public routes (sign-in/up); everything else requires authentication.
const isPublicRoute = createRouteMatcher(["/sign-in(.*)", "/sign-up(.*)"]);

// Clerk's publishable key is inlined at build time. If it is missing from the
// build (misconfigured env), running clerkMiddleware throws a hard 500. Guard
// against that so the app still serves instead of returning
// MIDDLEWARE_INVOCATION_FAILED.
const clerkConfigured = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

const withClerk = clerkMiddleware(async (auth, req) => {
  if (isPublicRoute(req)) {
    return;
  }
  try {
    const { userId } = await auth();
    if (!userId) {
      return NextResponse.redirect(new URL("/sign-in", req.url));
    }
  } catch {
    return NextResponse.redirect(new URL("/sign-in", req.url));
  }
});

export default function middleware(req: NextRequest, event: unknown) {
  if (!clerkConfigured) {
    // Auth not configured in this build; let the request through so pages can
    // render (Clerk components will show their own configuration error).
    return NextResponse.next();
  }
  // @ts-expect-error - clerkMiddleware's event type is internal to Clerk.
  return withClerk(req, event);
}

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)", "/(api|trpc)(.*)"],
};
