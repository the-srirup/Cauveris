"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { AuthGate } from "@/components/AuthGate";
import { CreateWorkspaceWizard } from "@/components/workspace/CreateWorkspaceWizard";

/**
 * The create-an-incident wizard.
 *
 * It reads `?mode=` to open on a specific step-1 card — the top bar's Upload
 * button deep-links here with `?mode=upload` rather than owning its own
 * file picker, so the archive format is described in exactly one place.
 */
function NewWorkspaceWizardRoute() {
  const searchParams = useSearchParams();
  const mode = searchParams.get("mode");

  const initialMode =
    mode === "upload" || mode === "archive"
      ? "archive"
      : mode === "source" || mode === "manual"
        ? (mode as "source" | "manual")
        : undefined;

  return <CreateWorkspaceWizard initialMode={initialMode} />;
}

export default function NewWorkspacePage() {
  return (
    <AuthGate redirect="/workspace/new">
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center bg-[var(--color-canvas)]">
            <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent-fg)]" />
          </div>
        }
      >
        <NewWorkspaceWizardRoute />
      </Suspense>
    </AuthGate>
  );
}
