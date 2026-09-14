"use client";

import { useQuery } from "@tanstack/react-query";
import { formatMoney } from "@/lib/format";
import type { BedrockIntelligence, Explanation } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function fmtNum(n: number | null): string {
  return n === null ? "unavailable" : n.toLocaleString();
}

export default function BedrockPage() {
  const api = useApi();

  const intel = useQuery({
    queryKey: ["bedrock-intelligence"],
    queryFn: () => api<BedrockIntelligence>("/bedrock/intelligence"),
  });

  const explanation = useQuery({
    queryKey: ["bedrock-explain"],
    queryFn: () => api<Explanation>("/bedrock/explain", { method: "POST" }),
    enabled: intel.data?.has_any_data === true,
  });

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Bedrock</h1>
        <p className="mt-1 text-white/60">
          How much Bedrock costs, how much you use it, which models, and whether
          anything is worth investigating. Cost comes from Cost Explorer; usage
          from CloudWatch. Metrics AWS doesn&apos;t provide are shown as
          unavailable, never zero.
        </p>
      </div>

      {intel.isLoading && <p className="text-sm text-white/50">Loading…</p>}
      {intel.isError && (
        <p className="text-sm text-red-300">{(intel.error as Error).message}</p>
      )}

      {intel.data && (
        <>
          {!intel.data.has_any_data && (
            <div className="rounded border border-white/10 bg-white/5 p-4 text-sm text-white/70">
              No Bedrock cost or usage found for this period.
              {intel.data.notes.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-white/50">
                  {intel.data.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* 1 + 2: cost and usage headline */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Card label="Cost (30d)">
              {intel.data.cost.available
                ? formatMoney(intel.data.cost.total_cost, intel.data.cost.currency)
                : "unavailable"}
            </Card>
            <Card label="Invocations">
              {fmtNum(intel.data.usage.invocations)}
            </Card>
            <Card label="Input tokens">
              {fmtNum(intel.data.usage.input_tokens)}
            </Card>
            <Card label="Output tokens">
              {fmtNum(intel.data.usage.output_tokens)}
            </Card>
          </div>

          {/* Investigate banner */}
          {intel.data.spike.detected && (
            <div className="rounded border border-yellow-500/30 bg-yellow-500/10 p-4">
              <div className="text-sm font-medium text-yellow-200">
                Worth investigating
              </div>
              <p className="mt-1 text-sm text-white/80">
                {intel.data.spike.message}
              </p>
              <div className="mt-2 grid grid-cols-3 gap-3 text-xs text-white/60">
                <div>
                  Baseline / day:{" "}
                  <span className="font-mono">
                    {Number(intel.data.spike.baseline).toLocaleString()}
                  </span>
                </div>
                <div>
                  Observed:{" "}
                  <span className="font-mono">
                    {Number(intel.data.spike.observed).toLocaleString()}
                  </span>
                </div>
                <div>
                  Associated cost change:{" "}
                  <span className="font-mono">
                    {intel.data.spike.associated_cost_change !== null
                      ? formatMoney(intel.data.spike.associated_cost_change)
                      : "unavailable"}
                  </span>
                </div>
              </div>
              <p className="mt-2 text-[11px] text-white/40">
                Association over the same window — not a proven cause.
              </p>
            </div>
          )}
          {!intel.data.spike.detected && intel.data.spike.reason && (
            <p className="text-xs text-white/40">{intel.data.spike.reason}</p>
          )}

          {/* 3: usage by model */}
          <section className="rounded border border-white/10 p-4">
            <h2 className="mb-2 text-lg font-medium">Usage by model</h2>
            {intel.data.by_model.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-white/50">
                    <th className="pb-1">Model</th>
                    <th className="pb-1 text-right">Invocations</th>
                    <th className="pb-1 text-right">Input tok</th>
                    <th className="pb-1 text-right">Output tok</th>
                  </tr>
                </thead>
                <tbody>
                  {intel.data.by_model.map((m) => (
                    <tr key={m.model_id} className="border-t border-white/5">
                      <td className="py-1 font-mono text-xs">{m.model_id}</td>
                      <td className="py-1 text-right font-mono">
                        {fmtNum(m.invocations)}
                      </td>
                      <td className="py-1 text-right font-mono">
                        {fmtNum(m.input_tokens)}
                      </td>
                      <td className="py-1 text-right font-mono">
                        {fmtNum(m.output_tokens)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-white/50">
                {intel.data.usage.available
                  ? "AWS did not report per-model usage for this period."
                  : `Usage unavailable${
                      intel.data.usage.reason
                        ? ` (${intel.data.usage.reason})`
                        : ""
                    }.`}
              </p>
            )}
          </section>

          {/* Efficiency — our calculation */}
          <section className="rounded border border-white/10 p-4">
            <div className="mb-2 flex items-center gap-2">
              <h2 className="text-lg font-medium">Efficiency</h2>
              <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-white/50">
                our calculation
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-white/50">Cost per invocation</div>
                <div className="font-mono">
                  {intel.data.efficiency.cost_per_invocation !== null
                    ? formatMoney(intel.data.efficiency.cost_per_invocation)
                    : "unavailable"}
                </div>
              </div>
              <div>
                <div className="text-white/50">Tokens per invocation</div>
                <div className="font-mono">
                  {intel.data.efficiency.tokens_per_invocation ?? "unavailable"}
                </div>
              </div>
            </div>
            <p className="mt-2 text-[11px] text-white/40">
              {intel.data.efficiency.note}
            </p>
          </section>

          {/* Explanation */}
          {intel.data.has_any_data && (
            <section className="rounded border border-white/10 p-4">
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
                <p className="text-sm text-white/80">
                  {explanation.data?.text}
                </p>
              )}
            </section>
          )}

          {/* Data provenance */}
          <p className="text-xs text-white/40">
            Cost source: {intel.data.cost.source} (authoritative for cost).
            Usage source: {intel.data.usage.source} (authoritative for usage).
            Read-only.
          </p>
        </>
      )}
    </div>
  );
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded border border-white/10 p-4">
      <div className="text-xs text-white/50">{label}</div>
      <div className="mt-1 text-lg font-semibold">{children}</div>
    </div>
  );
}
