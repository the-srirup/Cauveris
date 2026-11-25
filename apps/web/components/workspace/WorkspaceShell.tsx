"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { LogOut } from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { Button } from "@/components/ui";

/**
 * The slim header the workspace routes wear.
 *
 * The launcher is an interstitial between signing in and working, so it
 * deliberately does *not* use the console shell: the top bar's incident chip
 * is bound to an active incident, and on this screen there is none.  Showing
 * it would put "no incident" furniture on the one page whose job is to pick
 * an incident.
 */
export function WorkspaceShell({
  children,
  title,
  subtitle,
  backHref,
  backLabel = "Back to workspace",
  contentClassName,
}: {
  children: ReactNode;
  title: string;
  subtitle?: string;
  backHref?: string;
  backLabel?: string;
  contentClassName?: string;
}) {
  const router = useRouter();
  const { user, logout } = useAuthStore();

  const handleSignOut = async () => {
    try {
      await logout?.();
    } catch {
      // A failed sign-out must not trap the operator on this page.
    }
    router.push("/login");
  };

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-canvas)]">
      <header className="bg-[var(--surface-well,var(--color-canvas-inset))] shadow-[0_1px_0_rgba(255,255,255,0.04),0_2px_8px_rgba(0,0,0,0.22)]">
        <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
          <div className="flex min-h-14 py-2.5 items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              {backHref && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => router.push(backHref)}
                  aria-label={backLabel}
                >
                  ←
                </Button>
              )}
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)]">
                    Cauveris
                  </p>
                  <span className="text-xs text-[var(--color-border-default)]">/</span>
                  <h1 className="truncate text-sm font-semibold text-[var(--color-fg-default)]">
                    {title}
                  </h1>
                </div>
                {subtitle && (
                  <p className="text-xs text-[var(--color-fg-muted)] truncate mt-0.5">{subtitle}</p>
                )}
              </div>
            </div>

            <div className="flex items-center gap-3 flex-shrink-0">
              {user && (
                <span className="hidden text-xs text-[var(--color-fg-muted)] sm:inline">
                  {user.email || user.full_name || "Signed in"}
                </span>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSignOut}
                leadingIcon={<LogOut className="h-3.5 w-3.5" />}
                aria-label="Sign out"
              >
                <span className="hidden sm:inline">Sign out</span>
              </Button>
            </div>
          </div>
        </div>
      </header>

      <main className={contentClassName ?? "flex-1 mx-auto w-full max-w-6xl px-4 sm:px-6 py-8"}>
        {children}
      </main>
    </div>
  );
}

export default WorkspaceShell;
