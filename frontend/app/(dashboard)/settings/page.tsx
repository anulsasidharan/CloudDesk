"use client";

import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { hasRole } from "@/lib/format";
import { useAuth } from "@/components/layout/AuthProvider";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { EmptyState } from "@/components/ui/EmptyState";

export default function SettingsPage() {
  const { user } = useAuth();
  const allowed = hasRole(user.role, "admin");
  const { data, error, loading, reload } = useAsync(
    () => (allowed ? api.settings() : Promise.reject(new Error("forbidden"))),
    [allowed],
  );

  if (!allowed) {
    return (
      <EmptyState title="Admins only" description="Settings are visible to the admin role. Your role is read or act only." />
    );
  }
  return (
    <>
      <PageHeader title="Settings" subtitle="How this environment is configured (read-only)" />
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Runtime">
              <ul className="space-y-1 text-sm">
                <li>Environment: {data.environment}</li>
                <li>Demo mode: {String(data.demo_mode)}</li>
                <li>Database: {data.database}</li>
                <li>Redis: {data.redis}</li>
                <li>Vector store: {data.vector_store}</li>
                <li>LLM: {data.llm.llm_provider} / {data.llm.llm_model}</li>
              </ul>
            </Card>
            <Card title="Approval policy">
              <ul className="space-y-1 text-sm">
                <li>Refunds need approval: {String(data.approval_policy.refunds_require_approval)}</li>
                <li>Refund allowed without approval up to: {data.approval_policy.max_refund_without_approval}</li>
                <li>Approval-required tools: {data.approval_policy.approval_required_tools.join(", ")}</li>
              </ul>
            </Card>
          </div>
        )}
      </DataState>
    </>
  );
}
