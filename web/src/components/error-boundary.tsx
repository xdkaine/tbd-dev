"use client";

import React from "react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Optional fallback UI. Receives the error and a reset function. */
  fallback?: (props: { error: Error; reset: () => void }) => React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * React Error Boundary for catching render-time errors.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <SomeComponent />
 *   </ErrorBoundary>
 *
 * Or with a custom fallback:
 *   <ErrorBoundary fallback={({ error, reset }) => (
 *     <div>
 *       <p>Error: {error.message}</p>
 *       <button onClick={reset}>Try again</button>
 *     </div>
 *   )}>
 *     <SomeComponent />
 *   </ErrorBoundary>
 */
export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log to console in development; in production this could send to a
    // logging service (e.g. Loki via the API).
    console.error("[ErrorBoundary] Caught error:", error, errorInfo);
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    const { children, fallback } = this.props;

    if (error) {
      if (fallback) {
        return fallback({ error, reset: this.reset });
      }

      // Default fallback UI
      return (
        <div className="flex min-h-[200px] flex-col items-center justify-center rounded-lg border border-red-200 bg-red-50 p-6">
          <svg
            className="mb-3 h-10 w-10 text-red-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth="1.5"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
            />
          </svg>
          <h3 className="mb-1 text-sm font-semibold text-red-800">
            Something went wrong
          </h3>
          <p className="mb-4 text-center text-xs text-red-600">
            {error.message || "An unexpected error occurred."}
          </p>
          <button
            onClick={this.reset}
            className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
          >
            Try again
          </button>
        </div>
      );
    }

    return children;
  }
}
