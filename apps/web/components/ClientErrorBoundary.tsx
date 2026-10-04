"use client";

import { useEffect, useState } from "react";
import { ErrorBoundary } from "@/components/ErrorBoundary";

interface ClientErrorBoundaryProps {
  children: React.ReactNode;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

export function ClientErrorBoundary({ children, onError }: ClientErrorBoundaryProps) {
  const [pathname, setPathname] = useState("");

  useEffect(() => {
    setPathname(window.location.pathname);
  }, []);

  return (
    <ErrorBoundary
      resetKeys={[pathname]}
      onError={(error, errorInfo) => {
        console.error(`[Global ErrorBoundary] Route: ${pathname || window.location.pathname}`, error, errorInfo);
        onError?.(error, errorInfo);
      }}
    >
      {children}
    </ErrorBoundary>
  );
}