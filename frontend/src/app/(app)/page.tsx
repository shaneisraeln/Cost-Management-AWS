"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CostTrendChart } from "@/components/CostTrendChart";
import { formatMoney } from "@/lib/format";
import type {
  AwsConnection,
  CostBreakdown,
  CostSummary,
  CostSyncResult,
  DailyCostPoint,
  Reconciliation,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function OverviewPage() {
  const api = useApi();
  const queryClient = useQueryClient();

  const connections = useQuery({
    queryKey: ["aws-connections"],
    queryFn: () => api<AwsConnection[]>("/aws/connections"),
  });

  const summary = useQuery({
    queryKey: ["cost-summary"],
    queryFn: () => api<CostSummary>("/costs/summary"),
  });

  const daily = useQuery({
    queryKey: ["cost-daily"],
    queryFn: () => api<DailyCostPoint[]>("/costs"),
  });

  const breakdown = useQuery({
    queryKey: ["cost-breakdown"],
    queryFn: () => api<CostBreakdown>("/costs/breakdown"),
  });

  const reconciliation = useQuery({
    queryKey: ["cost-reconciliation"],
    queryFn: () => api<Reconciliation>("/costs/reconciliation"),
  });

  const connection = connections.data?.[0];

  const sync = useMutation({
    mutationFn: () =>
      api<CostSyncResult>(
        `/costs/sync?connection_id=${connection!.id}&days=30`,
        { method: "POST" },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cost-summary"] });
      queryClient.invalidateQueries({ queryKey: ["cost-daily"] });
      queryClient.invalidateQueries({ queryKey: ["cost-breakdown"] });
      queryClient.invalidateQueries({ queryKey: ["aws-connections"] });
    },
  });

  return (
    <div className="max-w-4xl space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Overview</h1>
          <p className="mt-1 text-white/60">
            Real AWS spend from Cost Explorer. How much are we spending and
            what&apos;s changing?
          </p>
        </div>
        <button
          onClick={() => sync.mutate()}
          disabled={!connection || sync.isPending}
          className="rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20 disabled:opacity-50"
          title={connection ? "" : "Connect an AWS account first"}
        >
          {sync.isPending ? "Syncing…" : "Sync now"}
        </button>
      </div>

      {!connection && (
        <div className="rounded border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm text-yellow-200">
          No AWS connection yet. Add one in Settings → AWS, then click Sync now.
        </div>
      )}

      {sync.isError && (
        <p className="text-sm text-red-300">{(sync.error as Error).message}</p>
      )}

      {sync.isSuccess && (
        <p className="text-sm text-green-300">
          Synced {sync.data.records_upserted} records from{" "}
          {sync.data.lines_fetched} Cost Explorer lines (
          {sync.data.period_start} → {sync.data.period_end}).
        </p>
      )}

      {/* Totals */}
      <div className="grid grid-cols-3 gap-4">
        <Card label="Total spend (30d)">
          {summary.data
            ? formatMoney(summary.data.total, summary.data.currency)
            : "—"}
        </Card>
        <Card label="Cost records">
          {summary.data ? summary.data.record_count.toLocaleString() : "—"}
        </Card>
        <Card label="Account">
          <span className="font-mono text-base">
            {connection?.account_id ?? "—"}
          </span>
        </Card>
      </div>

      {/* Reconciliation: every dollar buckets into Attributed/Shared/Unknown */}
      <section className="rounded border border-white/10 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-medium">Cost reconciliation</h2>
          {reconciliation.data && (
            <span
              className={`text-xs ${
                reconciliation.data.reconciles
                  ? "text-green-300"
                  : "text-red-300"
              }`}
            >
              {reconciliation.data.reconciles
                ? "Total = Attributed + Shared + Unknown ✓"
                : "Reconciliation mismatch"}
            </span>
          )}
        </div>
        {reconciliation.data ? (
          <div className="grid grid-cols-3 gap-4 text-sm">
            <ReconCell
              label="Attributed"
              value={reconciliation.data.attributed}
              currency={reconciliation.data.currency}
              tone="text-green-300"
            />
            <ReconCell
              label="Shared"
              value={reconciliation.data.shared}
              currency={reconciliation.data.currency}
              tone="text-yellow-300"
            />
            <ReconCell
              label="Unknown"
              value={reconciliation.data.unknown}
              currency={reconciliation.data.currency}
              tone="text-white/60"
            />
          </div>
        ) : (
          <p className="text-sm text-white/50">Loading…</p>
        )}
        <p className="mt-2 text-xs text-white/40">
          Attribution coverage:{" "}
          {reconciliation.data
            ? `${(reconciliation.data.coverage * 100).toFixed(1)}%`
            : "—"}
          . Cost Explorer groups by service, so spend is bucketed by the
          attribution state of each service&apos;s resources — not faked to the
          resource level.
        </p>
      </section>

      {/* Daily trend */}
      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">Daily spend</h2>
        {daily.isLoading ? (
          <p className="text-sm text-white/50">Loading…</p>
        ) : (
          <CostTrendChart data={daily.data ?? []} />
        )}
      </section>

      {/* Top services */}
      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">Top services</h2>
        {breakdown.data && breakdown.data.by_service.length > 0 ? (
          <table className="w-full text-sm">
            <tbody>
              {breakdown.data.by_service.slice(0, 10).map((row) => (
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
          <p className="text-sm text-white/50">No service data yet.</p>
        )}
      </section>

      {/* Traceability */}
      <p className="text-xs text-white/40">
        Source: AWS Cost Explorer (UnblendedCost, DAILY, grouped by service).
        {connection?.last_cost_sync
          ? ` Last sync ${new Date(connection.last_cost_sync).toLocaleString()}.`
          : " Not yet synced."}
        {connection?.last_error ? (
          <span className="text-red-300"> Error: {connection.last_error}</span>
        ) : null}
      </p>
    </div>
  );
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded border border-white/10 p-4">
      <div className="text-xs text-white/50">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{children}</div>
    </div>
  );
}

function ReconCell({
  label,
  value,
  currency,
  tone,
}: {
  label: string;
  value: string;
  currency: string;
  tone: string;
}) {
  return (
    <div>
      <div className="text-xs text-white/50">{label}</div>
      <div className={`mt-1 font-mono ${tone}`}>{formatMoney(value, currency)}</div>
    </div>
  );
}
