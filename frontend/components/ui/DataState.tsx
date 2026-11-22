"use client";

import type { ReactNode } from "react";
import { ApiError, NetworkError, isNotBuilt } from "@/lib/api";
import { EmptyState } from "./EmptyState";

/**
 * One place that turns "loading / failed / not built yet / ok" into UI,
 * so every page handles failure the same way.
 */
export function DataState({
  loading,
  error,
  onRetry,
  children,
}: {
  loading: boolean;
  error: unknown;
  onRetry?: () => void;
  children: ReactNode;
}) {
  if (error) {
    if (isNotBuilt(error)) {
      return (
        <EmptyState
          title="Not available yet"
          description="This screen is ready, but the backend route that feeds it has not been built in this phase."
        />
      );
    }
    if (error instanceof NetworkError) {
      return (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Cannot reach the CloudDesk API. Check that the backend is running on port 8000.
          {onRetry && (
            <button onClick={onRetry} className="ml-3 underline">
              Retry
            </button>
          )}
        </div>
      );
    }
    const message = error instanceof ApiError ? error.detail : "Something went wrong";
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        {message}
      </div>
    );
  }
  if (loading) return <p className="text-sm text-slate-500">Loading...</p>;
  return <>{children}</>;
}
