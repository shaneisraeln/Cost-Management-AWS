"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { formatMoney } from "@/lib/format";
import type {
  AwsConnection,
  CostChange,
  DetectionResult,
  Explanation,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

const CLASS_TONE: Record<string, string> = {
  GROWTH: "text-blue-300",
  ENGINEERING_CHANGE: "text-purple-300",
  WASTE: "text-yellow-300",
  SUSPICIOUS: "text-red-300",
  UNKNOWN: "text-white/60",
};

export default function AlertsPage() {
  const api = useApi();
  const queryClient = useQueryClient();
  const [openId, setOpenId] = useState<string | null>(null);

  const connections = useQuery({
    queryKey: ["aws-connections"],
    queryFn: () => api<AwsConnection[]>("/aws/connections"),
  });
  const changes = useQuery({
    queryKey: ["cost-changes"],
    queryFn: () => api<CostChange[]>("/cost-changes"),
  });

  const connection = connections.data?.[0];

  const detect = useMutation({
    mutationFn: () =>
      api<DetectionResult>("/investigate/detect?days=30", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cost-changes"] }),
  });

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Investigations</h1>
          <p className="mt-1 text-white/60">
            Detected cost changes. Click one to see what changed, when, what was
            affected, and the evidence behind it.
          </p>
        </div>
        <button
          onClick={() => detect.mutate()}
          disabled={!connection || detect.isPending}
          className="rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20 disabled:opacity-50"
        >
          {detect.isPending ? "Detecting…" : "Run detection"}
        </button>
      </div>

      {detect.isSuccess && (
        <p className="text-sm text-green-300">
          Analyzed {detect.data.services_analyzed} services; found{" "}
          {detect.data.cost_changes_created} new change(s).
        </p>
      )}

      {changes.data?.length === 0 && (
        <div className="rounded border border-white/10 p-4 text-sm text-white/50">
          No cost changes detected. Sync costs, then run detection. A flat,
          near-zero account will legitimately produce nothing.
        </div>
      )}

      <div className="space-y-2">
        {changes.data?.map((c) => (
          <ChangeCard
            key={c.id}
            change={c}
            open={openId === c.id}
            onToggle={() => setOpenId(openId === c.id ? null : c.id)}
          />
        ))}
      </div>
    </div>
  );
}

function ChangeCard({
  change,
  open,
  onToggle,
}: {
  change: CostChange;
  open: boolean;
  onToggle: () => void;
}) {
  const api = useApi();
  const explanation = useQuery({
    queryKey: ["explain", change.id],
    queryFn: () =>
      api<Explanation>(`/cost-changes/${change.id}/explain`, { method: "POST" }),
    enabled: open,
  });

  return (
    <div className="rounded border border-white/10">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between p-4 text-left hover:bg-white/5"
      >
        <div>
          <div className="font-medium">{change.service ?? "Account"}</div>
          <div className="text-xs text-white/50">{change.period_date}</div>
        </div>
        <div className="flex items-center gap-4">
          <span className={`text-sm ${CLASS_TONE[change.classification]}`}>
            {change.classification}
          </span>
          <span className="font-mono text-sm">
            {formatMoney(change.absolute_change)}
          </span>
        </div>
      </button>

      {open && (
        <div className="space-y-4 border-t border-white/10 p-4">
          {/* Facts */}
          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-white/40">
              Facts (deterministic)
            </div>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div>
                <div className="text-white/50">Baseline</div>
                <div className="font-mono">{formatMoney(change.baseline_cost)}</div>
              </div>
              <div>
                <div className="text-white/50">Observed</div>
                <div className="font-mono">{formatMoney(change.observed_cost)}</div>
              </div>
              <div>
                <div className="text-white/50">Confidence</div>
                <div className="font-mono">
                  {(change.confidence * 100).toFixed(0)}%
                </div>
              </div>
            </div>
          </div>

          {/* Evidence / correlations */}
          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-white/40">
              Evidence & correlations
            </div>
            {change.evidence.length > 0 ? (
              <ul className="space-y-1 text-sm text-white/70">
                {change.evidence.map((e, i) => (
                  <li key={i} className="font-mono text-xs">
                    {JSON.stringify(e)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-white/50">No correlating evidence.</p>
            )}
          </div>

          {/* AI / template explanation, clearly labeled */}
          <div>
            <div className="mb-1 flex items-center gap-2 text-xs uppercase tracking-wide text-white/40">
              Explanation
              {explanation.data && (
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] ${
                    explanation.data.generated_by === "ai"
                      ? "bg-purple-500/20 text-purple-200"
                      : "bg-white/10 text-white/50"
                  }`}
                >
                  {explanation.data.generated_by === "ai"
                    ? "AI-generated"
                    : "Templated"}
                </span>
              )}
            </div>
            {explanation.isLoading ? (
              <p className="text-sm text-white/50">Generating…</p>
            ) : (
              <p className="text-sm text-white/80">{explanation.data?.text}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
