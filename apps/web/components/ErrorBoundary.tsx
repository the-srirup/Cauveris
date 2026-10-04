"use client";

import { Component, ReactNode, ErrorInfo } from "react";
import { Button, Card } from "@/components/ui";
import { AlertTriangle, RotateCcw, Home, Bug } from "lucide-react";
import { notify } from "@/components/Notification";

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  resetKeys?: unknown[];
  resetOnPropsChange?: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({
      error,
      errorInfo,
    });

    // Log error to console (in production, send to error tracking service)
    console.error("ErrorBoundary caught an error:", error, errorInfo);

    // Notify error tracking (could integrate with Sentry, etc.)
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }

    // Show notification to user
    notify("An unexpected error occurred. Please try refreshing the page.", "error");
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    if (this.state.hasError && this.props.resetKeys) {
      const hasResetKeyChanged = this.props.resetKeys.some((key, index) => key !== prevProps.resetKeys?.[index]);
      if (hasResetKeyChanged) {
        this.reset();
      }
    }

    if (this.state.hasError && this.props.resetOnPropsChange) {
      this.reset();
    }
  }

  reset = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      // Custom fallback UI
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback UI
      return (
        <div className="min-h-screen bg-[var(--theme-background)] text-foreground flex items-center justify-center p-6">
          <Card className="max-w-md w-full p-6 text-center space-y-6">
            <div className="w-16 h-16 mx-auto bg-[var(--color-brand-danger)]/10 border border-danger/20 rounded-2xl flex items-center justify-center">
              <AlertTriangle className="h-8 w-8 text-[var(--color-brand-danger)]" />
            </div>

            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">Something went wrong</h2>
              <p className="text-[var(--color-text-muted)] text-sm">
                An unexpected error occurred while rendering this component.
              </p>
            </div>

            {this.state.error && (
              <details className="text-left p-4 bg-[var(--color-surface-2)]/50 border border-[var(--color-border)] rounded-xl space-y-2">
                <summary className="font-mono text-xs text-[var(--color-text-muted)] cursor-pointer">
                  Error Details (click to expand)
                </summary>
                <pre className="font-mono text-[10px] text-[var(--color-brand-danger)]/80 overflow-x-auto max-h-40">
                  {this.state.error.message}
                  {this.state.errorInfo?.componentStack && `\n\n${this.state.errorInfo.componentStack}`}
                </pre>
              </details>
            )}

            <div className="flex flex-col sm:flex-row gap-3 pt-4">
              <Button
                variant="primary"
                onClick={this.reset}
                className="flex-1"
              >
                <RotateCcw className="h-4 w-4 mr-2" />
                Try Again
              </Button>
              <Button
                variant="outline"
                onClick={() => window.location.href = "/"}
                className="flex-1"
              >
                <Home className="h-4 w-4 mr-2" />
                Go Home
              </Button>
            </div>

            <details className="text-left p-3 bg-[var(--color-surface-2)]/50 border border-[var(--color-border)] rounded-xl">
              <summary className="font-mono text-xs text-[var(--color-text-muted)] cursor-pointer">
                Troubleshooting
              </summary>
              <ul className="text-[11px] text-[var(--color-text-muted)] mt-2 space-y-1 list-disc list-inside">
                <li>Refresh the page to reset the component state</li>
                <li>Check browser console for detailed error information</li>
                <li>Ensure the backend API is running on port 8000</li>
                <li>Clear browser cache and localStorage if issues persist</li>
                <li>Report this issue with the error details above</li>
              </ul>
            </details>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}

// Hook for functional components to access error boundary state
export function useErrorHandler(): (error: Error) => void {
  // This would be connected to a global error boundary context in a real implementation
  return (error: Error) => {
    console.error("Error caught by useErrorHandler:", error);
    throw error; // Re-throw to be caught by nearest ErrorBoundary
  };
}

// Route-level error boundary wrapper
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  errorBoundaryProps?: Partial<ErrorBoundaryProps>
): React.FC<P> {
  return function WithErrorBoundary(props: P) {
    return (
      <ErrorBoundary {...errorBoundaryProps}>
        <WrappedComponent {...props} />
      </ErrorBoundary>
    );
  };
}

// Specialized error boundaries for different page types
export const PageErrorBoundary: React.FC<{ children: ReactNode }> = ({ children }) => (
  <ErrorBoundary
    fallback={
      <div className="min-h-screen bg-[var(--theme-background)] text-foreground flex items-center justify-center p-6">
        <Card className="max-w-lg w-full p-6 text-center space-y-4">
          <div className="w-16 h-16 mx-auto bg-[var(--color-brand-danger)]/10 border border-danger/20 rounded-2xl flex items-center justify-center">
            <Bug className="h-8 w-8 text-[var(--color-brand-danger)]" />
          </div>
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Page Error</h2>
          <p className="text-[var(--color-text-muted)] text-sm">
            This page encountered an error and couldn&apos;t load properly.
          </p>
          <Button variant="primary" onClick={() => window.location.reload()}>
            <RotateCcw className="h-4 w-4 mr-2" />
            Reload Page
          </Button>
        </Card>
      </div>
    }
  >
    {children}
  </ErrorBoundary>
);

export const GraphErrorBoundary: React.FC<{ children: ReactNode }> = ({ children }) => (
  <ErrorBoundary
    fallback={
      <div className="min-h-screen bg-[var(--theme-background)] text-foreground flex items-center justify-center p-6">
        <Card className="max-w-lg w-full p-6 text-center space-y-4">
          <div className="w-16 h-16 mx-auto bg-[var(--color-brand-warning)]/10 border border-warning/20 rounded-2xl flex items-center justify-center">
            <AlertTriangle className="h-8 w-8 text-warning" />
          </div>
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Graph Visualization Error</h2>
          <p className="text-[var(--color-text-muted)] text-sm">
            The causal graph couldn&apos;t be rendered. This may be due to large dataset size.
          </p>
          <div className="flex gap-3 justify-center">
            <Button variant="primary" onClick={() => window.location.reload()}>
              <RotateCcw className="h-4 w-4 mr-2" />
              Reload
            </Button>
            <Button variant="outline" onClick={() => window.location.href = "/evidence-vault"}>
              View Evidence Instead
            </Button>
          </div>
        </Card>
      </div>
    }
  >
    {children}
  </ErrorBoundary>
);

export const DataErrorBoundary: React.FC<{ children: ReactNode }> = ({ children }) => (
  <ErrorBoundary
    fallback={
      <div className="min-h-screen bg-[var(--theme-background)] text-foreground flex items-center justify-center p-6">
        <Card className="max-w-lg w-full p-6 text-center space-y-4">
          <div className="w-16 h-16 mx-auto bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20 rounded-2xl flex items-center justify-center">
            <AlertTriangle className="h-8 w-8 text-[var(--color-accent)]" />
          </div>
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Data Loading Error</h2>
          <p className="text-[var(--color-text-muted)] text-sm">
            Failed to load data from the backend. Please check your connection.
          </p>
          <Button variant="primary" onClick={() => window.location.reload()}>
            <RotateCcw className="h-4 w-4 mr-2" />
            Retry
          </Button>
        </Card>
      </div>
    }
  >
    {children}
  </ErrorBoundary>
);