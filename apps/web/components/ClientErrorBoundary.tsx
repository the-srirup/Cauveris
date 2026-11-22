"use client";

import { usePathname } from "next/navigation";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { useActiveIncident } from "@/lib/useIncident";

interface ClientErrorBoundaryProps {
  children: React.ReactNode;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

export function ClientErrorBoundary({ children, onError }: ClientErrorBoundaryProps) {
  // usePathname tracks client-side navigation, so a route change resets even
  // when the boundary component itself is never unmounted. Reading
  // window.location once on mount missed exactly that case.
  const pathname = usePathname() ?? "";
  const { incidentId } = useActiveIncident();

  return (
    <ErrorBoundary
      category="render"
      // Route change AND incident change both reset recoverable errors, so a
      // crash on one incident never follows the user into the next view.
      resetKeys={[pathname, incidentId ?? ""]}
      onError={(error, errorInfo) => {
        console.error(`[Global ErrorBoundary] Route: ${pathname}`, error, errorInfo);
        onError?.(error, errorInfo);
      }}
    >
      {children}
    </ErrorBoundary>
  );
}
