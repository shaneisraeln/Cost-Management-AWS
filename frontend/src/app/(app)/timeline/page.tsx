"use client";

import { useQuery } from "@tanstack/react-query";
import type { TimelineItem } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const KIND_TONE: Record<string, string> = {
  event: "border-blue-500/40 bg-blue-500/5",
  anomaly: "border-red-500/40 bg-red-500/5",
  cost_change: "border-yellow-500/40 bg-yellow-500/5",
};

const KIND_LABEL: Record<string, string> = {
  event: "Activity",
  anomaly: "Anomaly",
  cost_change: "Cost change",
};

export default function TimelinePage() {
  const api = useApi();
  const timeline = useQuery({
    queryKey: ["timeline"],
    queryFn: () => api<TimelineItem[]>("/timeline?days=30"),
  });

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Event Timeline</h1>
        <p className="mt-1 text-white/60">
          Activity, anomalies, and cost changes in chronological order.
          Correlation is evidence, not proof of causality.
        </p>
      </div>

      {timeline.isLoading && <p className="text-sm text-white/50">Loading…</p>}
      {timeline.data?.length === 0 && (
        <p className="text-sm text-white/50">
          Nothing on the timeline yet. Sync activity and run detection.
        </p>
      )}

      <div className="space-y-2">
        {timeline.data?.map((item, i) => (
          <div
            key={i}
            className={`rounded border p-3 ${KIND_TONE[item.kind] ?? "border-white/10"}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{item.title}</span>
              <span className="text-xs text-white/50">
                {item.timestamp
                  ? new Date(item.timestamp).toLocaleString()
                  : "—"}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase text-white/60">
                {KIND_LABEL[item.kind] ?? item.kind}
              </span>
              <span className="font-mono text-xs text-white/60">
                {Object.entries(item.detail)
                  .filter(([, v]) => v !== null && v !== undefined && v !== "")
                  .map(([k, v]) => `${k}=${v}`)
                  .join("  ")}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
