"use client";

import { AuthGate } from "@/components/AuthGate";
import { WorkspaceLauncher } from "@/components/workspace/WorkspaceLauncher";

/**
 * The workspace launcher — where every session starts.
 *
 * Signing in lands here rather than on the dashboard: an operator opens the
 * console the way they open Photoshop, by choosing what to work on first.
 */
export default function WorkspacePage() {
  return (
    <AuthGate redirect="/workspace">
      <WorkspaceLauncher />
    </AuthGate>
  );
}
