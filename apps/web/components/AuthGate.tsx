"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth";

interface AuthGateProps {
  children: ReactNode;
  /**
   * Path the user is returned to after signing in. It is passed through to
   * the login page as the `redirect` query parameter.
   */
  redirect?: string;
  /** Text shown while the auth state is still being resolved. */
  loadingLabel?: string;
}

/**
 * Gate that renders its children only for an authenticated user.
 *
 * The gate has to live in its own component: the pages used to inline the
 * "is the user signed in?" check as an early `return` in the middle of the
 * page component, which placed that `return` *before* the page's remaining
 * hooks. The auth store starts out with `isLoading === true`, so the first
 * render of a page ran fewer hooks than the second one and React threw
 * "Rendered more hooks than during the previous render." for every
 * signed-in user.
 *
 * Rendering the page body as a child of the gate keeps the hook order of the
 * page body stable: it is either not mounted at all, or mounted with the
 * same hooks on every render.
 */
export function AuthGate({
  children,
  redirect = "/",
  loadingLabel = "Authenticating...",
}: AuthGateProps) {
  const { isAuthenticated, isLoading, initializeAuth } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (typeof initializeAuth === "function") {
      initializeAuth();
    }
  }, [initializeAuth]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push(`/login?redirect=${encodeURIComponent(redirect)}`);
    }
  }, [isAuthenticated, isLoading, router, redirect]);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 min-h-screen items-center justify-center p-8">
        <div className="flex h-8 w-8 animate-spin text-[var(--color-accent-fg)]">
          <svg
            className="h-8 w-8"
            viewBox="0 0 24 24"
            aria-hidden="true"
            focusable="false"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
              fill="none"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        </div>
        <p className="text-sm text-[var(--color-fg-muted)]">{loadingLabel}</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col gap-4 min-h-screen items-center justify-center p-8">
        <div className="flex h-8 w-8 animate-spin text-[var(--color-accent-fg)]">
          <svg
            className="h-8 w-8"
            viewBox="0 0 24 24"
            aria-hidden="true"
            focusable="false"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
              fill="none"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        </div>
        <p className="text-sm text-[var(--color-fg-muted)]">Redirecting to login...</p>
      </div>
    );
  }

  return <>{children}</>;
}

export default AuthGate;
