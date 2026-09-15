import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Public routes (sign-in/up); everything else requires authentication.
const isPublicRoute = createRouteMatcher(["/sign-in(.*)", "/sign-up(.*)"]);

export default clerkMiddleware(async (auth, req) => {
  if (isPublicRoute(req)) {
    return;
  }
  try {
    const { userId } = await auth();
    if (!userId) {
      // Not signed in -> send to sign-in rather than throwing a 500.
      const signIn = new URL("/sign-in", req.url);
      return NextResponse.redirect(signIn);
    }
  } catch {
    // If Clerk cannot initialize (e.g. transient/config issue), fail open to
    // the sign-in page instead of a hard middleware 500.
    const signIn = new URL("/sign-in", req.url);
    return NextResponse.redirect(signIn);
  }
});

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)", "/(api|trpc)(.*)"],
};
