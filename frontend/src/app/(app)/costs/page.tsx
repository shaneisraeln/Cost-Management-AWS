"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { CostTrendChart } from "@/components/CostTrendChart";
import { formatMoney, isoDate } from "@/lib/format";
import type { CostBreakdown, CostSummary, DailyCostPoint } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function defaultRange(): { from: string; to: string } {
  const to = new Date();
  to.setDate(to.getDate() + 1); // end is exclusive; include today
  const from = new Date(to);
  from.setDate(from.getDate() - 31);
  return { from: isoDate(from), to: isoDate(to) };
}

export default function CostsPage() {
  const api = useApi();
  const router = useRouter();
  const params = useSearchParams();

  const def = useMemo(defaultRange, []);
  const from = params.get("from") ?? def.from;
  const to = params.get("to") ?? def.to;
  const qs = `?from=${from}&to=${to}`;

  const summary = useQuery({
    queryKey: ["cost-summary", from, to],
    queryFn: () => api<CostSummary>(`/costs/summary${qs}`),
  });
  const daily = useQuery({
    queryKey: ["cost-daily", from, to],
    queryFn: () => api<DailyCostPoint[]>(`/costs${qs}`),
  });
  const breakdown = useQuery({
    queryKey: ["cost-breakdown", from, to],
    queryFn: () => api<CostBreakdown>(`/costs/breakdown${qs}`),
  });

  function updateRange(next: { from?: string; to?: string }) {
    const sp = new URLSearchParams(params.toString());
    sp.set("from", next.from ?? from);
    sp.set("to", next.to ?? to);
    router.replace(`/costs?${sp.toString()}`);
  }

  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Cost Explorer</h1>
        <p className="mt-1 text-white/60">
          Filter by date range and drill into service-level spend. Filters live
          in the URL so investigations are shareable.
        </p>
      </div>

      {/* Date range filter */}
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-white/60">From</span>
          <input
            type="date"
            value={from}
            onChange={(e) => updateRange({ from: e.target.value })}
            className="rounded border border-white/15 bg-transparent px-3 py-2 text-sm"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-white/60">To (exclusive)</span>
          <input
            type="date"
            value={to}
            onChange={(e) => updateRange({ to: e.target.value })}
            className="rounded border border-white/15 bg-transparent px-3 py-2 text-sm"
          />
        </label>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded border border-white/10 p-4">
          <div className="text-xs text-white/50">Total</div>
          <div className="mt-1 text-2xl font-semibold">
            {summary.data
              ? formatMoney(summary.data.total, summary.data.currency)
              : "—"}
          </div>
        </div>
        <div className="rounded border border-white/10 p-4">
          <div className="text-xs text-white/50">Records</div>
          <div className="mt-1 text-2xl font-semibold">
            {summary.data ? summary.data.record_count.toLocaleString() : "—"}
          </div>
        </div>
      </div>

      {/* Trend */}
      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">Daily trend</h2>
        {daily.isLoading ? (
          <p className="text-sm text-white/50">Loading…</p>
        ) : (
          <CostTrendChart data={daily.data ?? []} />
        )}
      </section>

      {/* Service breakdown */}
      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">Service breakdown</h2>
        {breakdown.data && breakdown.data.by_service.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-white/50">
                <th className="pb-2">Service</th>
                <th className="pb-2 text-right">Cost</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.data.by_service.map((row) => (
                <tr key={row.service} className="border-t border-white/5">
                  <td className="py-1.5">{row.service}</td>
                  <td className="py-1.5 text-right font-mono">
                    {formatMoney(row.amount, breakdown.data!.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-white/50">No data for this range.</p>
        )}
      </section>

      <p className="text-xs text-white/40">
        Source: AWS Cost Explorer, UnblendedCost, DAILY granularity, grouped by
        service. Every figure traces to a CostRecord with its source query.
      </p>
    </div>
  );
}
