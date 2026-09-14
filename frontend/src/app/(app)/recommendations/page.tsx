"use client";

import { useQuery } from "@tanstack/react-query";
import type { ActionRequest, AuditLogEntry } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const STATUS_TONE: Record<string, string> = {
  EXECUTED: "text-green-300",
  BLOCKED: "text-yellow-300",
  FAILED: "text-red-300",
  PENDING: "text-white/60",
};

export default function RecommendationsPage() {
  const api = useApi();

  const actions = useQuery({
    queryKey: ["remediation-actions"],
    queryFn: () => api<ActionRequest[]>("/remediation/actions"),
  });
  const audit = useQuery({
    queryKey: ["audit-logs"],
    queryFn: () => api<AuditLogEntry[]>("/audit-logs"),
  });

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Actions & audit</h1>
        <p className="mt-1 text-white/60">
          Executed write actions and a complete audit trail of every attempt.
          Recommendations are advice; actions are user-approved and audited
          separately.
        </p>
      </div>

      <section>
        <h2 className="mb-2 text-lg font-medium">Action requests</h2>
        {actions.data?.length === 0 && (
          <p className="text-sm text-white/50">No actions taken yet.</p>
        )}
        <div className="space-y-2">
          {actions.data?.map((a) => (
            <div
              key={a.id}
              className="flex items-center justify-between rounded border border-white/10 p-3 text-sm"
            >
              <div>
                <span className="font-mono">{a.provider_resource_id}</span>
                <span className="text-white/50"> · {a.action_type}</span>
              </div>
              <span className={STATUS_TONE[a.status]}>{a.status}</span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Audit log</h2>
        {audit.data?.length === 0 && (
          <p className="text-sm text-white/50">No audit entries yet.</p>
        )}
        <div className="space-y-1">
          {audit.data?.map((e) => (
            <div
              key={e.id}
              className="rounded border border-white/10 p-2 text-xs"
            >
              <div className="flex items-center justify-between">
                <span>
                  {e.action}
                  {e.aws_api ? ` (${e.aws_api})` : ""} ·{" "}
                  <span className="font-mono">{e.resource_id}</span>
                </span>
                <span className={STATUS_TONE[e.result] ?? "text-white/60"}>
                  {e.result}
                </span>
              </div>
              <div className="mt-0.5 text-white/40">
                {new Date(e.created_at).toLocaleString()} ·{" "}
                {e.request_summary}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
