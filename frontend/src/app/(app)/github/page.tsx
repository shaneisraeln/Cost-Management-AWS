"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { formatMoney } from "@/lib/format";
import type {
  CostEstimate,
  Explanation,
  GithubRepository,
  Guardrail,
  Variance,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

const SAMPLE_PLAN = `{
  "resource_changes": [
    {"address": "aws_instance.api", "type": "aws_instance",
     "change": {"actions": ["create"], "before": null, "after": {"instance_type": "m5.large"}}},
    {"address": "aws_ebs_volume.data", "type": "aws_ebs_volume",
     "change": {"actions": ["create"], "before": null, "after": {"size": 200, "type": "gp3"}}}
  ]
}`;

export default function GithubPage() {
  const api = useApi();
  const queryClient = useQueryClient();
  const [repoName, setRepoName] = useState("");
  const [prNumber, setPrNumber] = useState("");
  const [planText, setPlanText] = useState(SAMPLE_PLAN);
  const [result, setResult] = useState<CostEstimate | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  const repos = useQuery({
    queryKey: ["github-repos"],
    queryFn: () => api<GithubRepository[]>("/github/repositories"),
  });

  const addRepo = useMutation({
    mutationFn: () =>
      api<GithubRepository>("/github/repositories", {
        method: "POST",
        body: JSON.stringify({ full_name: repoName }),
      }),
    onSuccess: () => {
      setRepoName("");
      queryClient.invalidateQueries({ queryKey: ["github-repos"] });
    },
  });

  const submitPlan = useMutation({
    mutationFn: () => {
      let plan: unknown;
      try {
        plan = JSON.parse(planText);
        setParseError(null);
      } catch (e) {
        setParseError((e as Error).message);
        throw e;
      }
      return api<CostEstimate>("/estimates", {
        method: "POST",
        body: JSON.stringify({
          iac_format: "terraform_plan",
          plan,
          pr_number: prNumber ? Number(prNumber) : null,
        }),
      });
    },
    onSuccess: (data) => setResult(data),
  });

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">GitHub cost awareness</h1>
        <p className="mt-1 text-white/60">
          Estimate the AWS cost impact of an infrastructure change before it
          ships. Paste a <code>terraform show -json</code> plan. Figures are{" "}
          <span className="text-yellow-300">estimates, not actual billing</span>.
        </p>
      </div>

      {/* Link repository */}
      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">Repositories</h2>
        <div className="flex gap-2">
          <input
            value={repoName}
            onChange={(e) => setRepoName(e.target.value)}
            placeholder="owner/repo"
            className="flex-1 rounded border border-white/15 bg-transparent px-3 py-2 text-sm"
          />
          <button
            onClick={() => addRepo.mutate()}
            disabled={!repoName || addRepo.isPending}
            className="rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20 disabled:opacity-50"
          >
            Link
          </button>
        </div>
        {repos.data && repos.data.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm text-white/70">
            {repos.data.map((r) => (
              <li key={r.id} className="font-mono">
                {r.full_name}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Submit plan */}
      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">Estimate a plan</h2>
        <div className="mb-2 flex gap-2">
          <input
            value={prNumber}
            onChange={(e) => setPrNumber(e.target.value)}
            placeholder="PR # (optional)"
            className="w-40 rounded border border-white/15 bg-transparent px-3 py-2 text-sm"
          />
        </div>
        <textarea
          value={planText}
          onChange={(e) => setPlanText(e.target.value)}
          rows={10}
          className="w-full rounded border border-white/15 bg-transparent p-3 font-mono text-xs"
        />
        {parseError && (
          <p className="mt-1 text-sm text-red-300">Invalid JSON: {parseError}</p>
        )}
        <button
          onClick={() => submitPlan.mutate()}
          disabled={submitPlan.isPending}
          className="mt-2 rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20 disabled:opacity-50"
        >
          {submitPlan.isPending ? "Estimating…" : "Estimate cost impact"}
        </button>
      </section>

      {result && <EstimateResultView estimate={result} />}
    </div>
  );
}

function EstimateResultView({ estimate }: { estimate: CostEstimate }) {
  const api = useApi();
  const [deployed, setDeployed] = useState(!!estimate.deployed_at);
  const explanation = useQuery({
    queryKey: ["explain-estimate", estimate.id],
    queryFn: () =>
      api<Explanation>(`/estimates/${estimate.id}/explain`, { method: "POST" }),
  });

  const delta = Number(estimate.estimated_monthly_delta);

  return (
    <section className="rounded border border-white/10 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-medium">Cost impact</h2>
        <span className="rounded bg-yellow-500/15 px-2 py-0.5 text-xs text-yellow-200">
          Estimate — not actual billing
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div>
          <div className="text-white/50">Baseline / mo</div>
          <div className="font-mono">{formatMoney(estimate.baseline_monthly)}</div>
        </div>
        <div>
          <div className="text-white/50">Proposed / mo</div>
          <div className="font-mono">{formatMoney(estimate.proposed_monthly)}</div>
        </div>
        <div>
          <div className="text-white/50">Monthly delta</div>
          <div
            className={`font-mono ${delta > 0 ? "text-red-300" : delta < 0 ? "text-green-300" : ""}`}
          >
            {delta > 0 ? "+" : ""}
            {formatMoney(estimate.estimated_monthly_delta)}
          </div>
        </div>
      </div>

      {/* Cost Guardrail */}
      <div className="mt-4 border-t border-white/10 pt-3">
        <GuardrailCard estimateId={estimate.id} />
      </div>

      {/* Line items: what changed */}
      <div className="mt-4">
        <div className="mb-1 text-xs uppercase tracking-wide text-white/40">
          What changed
        </div>
        <table className="w-full text-sm">
          <tbody>
            {estimate.line_items.map((li) => (
              <tr key={li.address} className="border-t border-white/5">
                <td className="py-1.5 font-mono text-xs">{li.address}</td>
                <td className="py-1.5">{li.action}</td>
                <td className="py-1.5 text-right font-mono">
                  {li.estimated ? formatMoney(li.delta_monthly) : "not estimated"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {estimate.unsupported.length > 0 && (
        <p className="mt-3 text-xs text-white/50">
          Not estimated (unsupported types): {estimate.unsupported.join(", ")}
        </p>
      )}

      <p className="mt-2 text-xs text-white/40">
        Pricing source: {estimate.pricing_source ?? "n/a"}. Deterministic
        calculation; the explanation below only phrases this result.
      </p>

      {/* Explanation */}
      <div className="mt-4 border-t border-white/10 pt-3">
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
              {explanation.data.generated_by === "ai" ? "AI-generated" : "Templated"}
            </span>
          )}
        </div>
        {explanation.isLoading ? (
          <p className="text-sm text-white/50">Generating…</p>
        ) : (
          <p className="text-sm text-white/80">{explanation.data?.text}</p>
        )}
      </div>

      {/* Predicted vs actual */}
      <div className="mt-4 border-t border-white/10 pt-3">
        <VarianceSection
          estimate={estimate}
          deployed={deployed}
          onDeployed={() => setDeployed(true)}
        />
      </div>
    </section>
  );
}

const GUARDRAIL_UI: Record<
  string,
  { label: string; icon: string; box: string; text: string }
> = {
  PASS: {
    label: "PASS",
    icon: "🟢",
    box: "border-green-500/30 bg-green-500/10",
    text: "text-green-200",
  },
  WARNING: {
    label: "WARNING",
    icon: "🟡",
    box: "border-yellow-500/30 bg-yellow-500/10",
    text: "text-yellow-200",
  },
  REVIEW_REQUIRED: {
    label: "REVIEW REQUIRED",
    icon: "🔴",
    box: "border-red-500/30 bg-red-500/10",
    text: "text-red-200",
  },
};

function GuardrailCard({ estimateId }: { estimateId: string }) {
  const api = useApi();
  const guardrail = useQuery({
    queryKey: ["guardrail", estimateId],
    queryFn: () => api<Guardrail>(`/estimates/${estimateId}/guardrail`),
  });

  if (guardrail.isLoading) {
    return <p className="text-sm text-white/50">Evaluating cost guardrail…</p>;
  }
  if (guardrail.isError || !guardrail.data) {
    return (
      <p className="text-sm text-red-300">
        {(guardrail.error as Error)?.message ?? "Guardrail unavailable"}
      </p>
    );
  }

  const g = guardrail.data;
  const ui = GUARDRAIL_UI[g.status] ?? GUARDRAIL_UI.PASS;
  const delta = Number(g.monthly_delta);

  return (
    <div className={`rounded border p-4 ${ui.box}`}>
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-white/50">
          Cost Guardrail
        </div>
        <span className="rounded bg-black/20 px-2 py-0.5 text-[10px] text-white/50">
          Estimate — not actual billing
        </span>
      </div>

      <div className={`mt-1 flex items-center gap-2 text-lg font-semibold ${ui.text}`}>
        <span>{ui.icon}</span>
        <span>{ui.label}</span>
      </div>

      {/* Headline number: savings vs increase */}
      <div className="mt-2 text-sm">
        {g.is_savings ? (
          <span className="text-green-200">
            Estimated savings: {formatMoney(String(Math.abs(delta)))}/month
          </span>
        ) : (
          <span>
            Estimated monthly change:{" "}
            <span className={delta > 0 ? "text-red-200" : ""}>
              {delta > 0 ? "+" : ""}
              {formatMoney(g.monthly_delta)}/month
            </span>
          </span>
        )}
      </div>

      <p className="mt-2 text-sm text-white/80">{g.message}</p>

      {/* Policy thresholds */}
      <div className="mt-2 text-xs text-white/50">
        Policy: warning at {formatMoney(g.warning_threshold)} · review required at{" "}
        {formatMoney(g.review_threshold)}
      </div>

      {/* Cost drivers */}
      {g.cost_drivers.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-xs uppercase tracking-wide text-white/40">
            Cost drivers
          </div>
          <table className="w-full text-sm">
            <tbody>
              {g.cost_drivers.map((d) => (
                <tr key={d.address} className="border-t border-white/5">
                  <td className="py-1 font-mono text-xs">{d.address}</td>
                  <td className="py-1 text-right font-mono">
                    {Number(d.delta_monthly) > 0 ? "+" : ""}
                    {formatMoney(d.delta_monthly)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Completeness caveat */}
      {!g.estimate_complete && g.incomplete_note && (
        <p className="mt-3 rounded bg-black/20 p-2 text-xs text-white/60">
          ⚠ {g.incomplete_note}
          {g.unsupported.length > 0
            ? ` Unsupported: ${g.unsupported.join(", ")}.`
            : ""}
        </p>
      )}

      <p className="mt-2 text-[11px] text-white/40">
        Deterministic evaluation from the pricing source
        {g.pricing_source ? ` (${g.pricing_source})` : ""}. Advisory only — this
        does not block, deploy, or modify anything.
      </p>
    </div>
  );
}

const VERDICT_TONE: Record<string, string> = {
  HIGHER: "bg-red-500/15 text-red-200",
  LOWER: "bg-green-500/15 text-green-200",
  CLOSE: "bg-blue-500/15 text-blue-200",
  INSUFFICIENT_DATA: "bg-white/10 text-white/60",
};

function VarianceSection({
  estimate,
  deployed,
  onDeployed,
}: {
  estimate: CostEstimate;
  deployed: boolean;
  onDeployed: () => void;
}) {
  const api = useApi();
  const [accountId, setAccountId] = useState(estimate.account_id ?? "");

  const markDeployed = useMutation({
    mutationFn: () =>
      api<CostEstimate>(`/estimates/${estimate.id}/mark-deployed`, {
        method: "POST",
        body: JSON.stringify({ account_id: accountId || null }),
      }),
    onSuccess: () => {
      onDeployed();
      variance.refetch();
    },
  });

  const variance = useQuery({
    queryKey: ["variance", estimate.id],
    queryFn: () => api<Variance>(`/estimates/${estimate.id}/variance`),
    enabled: deployed,
  });

  return (
    <div>
      <div className="mb-1 text-xs uppercase tracking-wide text-white/40">
        Predicted vs actual
      </div>

      {!deployed && (
        <div className="flex flex-wrap items-end gap-2">
          <input
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            placeholder="AWS account id (optional)"
            className="rounded border border-white/15 bg-transparent px-2 py-1.5 text-sm"
          />
          <button
            onClick={() => markDeployed.mutate()}
            disabled={markDeployed.isPending}
            className="rounded bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20 disabled:opacity-50"
          >
            {markDeployed.isPending ? "Marking…" : "Mark deployed & compare"}
          </button>
          <span className="text-xs text-white/40">
            Records deployment time so actual cost can be measured afterward.
          </span>
        </div>
      )}

      {deployed && variance.isLoading && (
        <p className="text-sm text-white/50">Measuring actual cost…</p>
      )}

      {deployed && variance.data && (
        <div className="space-y-3">
          {variance.data.verdict === "INSUFFICIENT_DATA" ? (
            <div className="rounded border border-white/10 bg-white/5 p-3 text-sm text-white/70">
              Not enough actual billing data yet (
              {variance.data.actual_days_observed} day(s) observed).
              {variance.data.possible_reasons[0]
                ? ` ${variance.data.possible_reasons[0]}`
                : ""}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <div className="text-white/50">Predicted / mo</div>
                  <div className="font-mono">
                    {formatMoney(variance.data.predicted_monthly)}
                  </div>
                </div>
                <div>
                  <div className="text-white/50">Actual / mo</div>
                  <div className="font-mono">
                    {formatMoney(variance.data.actual_monthly)}
                  </div>
                </div>
                <div>
                  <div className="text-white/50">Variance</div>
                  <div className="font-mono">
                    {formatMoney(variance.data.absolute_variance)}
                    {variance.data.percentage_variance !== null
                      ? ` / ${variance.data.percentage_variance.toFixed(1)}%`
                      : ""}
                  </div>
                </div>
              </div>

              <span
                className={`inline-block rounded px-2 py-0.5 text-xs ${
                  VERDICT_TONE[variance.data.verdict]
                }`}
              >
                Actual is {variance.data.verdict.toLowerCase()} than predicted
              </span>

              {variance.data.service_breakdown.length > 0 && (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-white/50">
                      <th className="pb-1">Service</th>
                      <th className="pb-1 text-right">Actual / mo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {variance.data.service_breakdown.map((s) => (
                      <tr key={s.service} className="border-t border-white/5">
                        <td className="py-1">{s.service}</td>
                        <td className="py-1 text-right font-mono">
                          {formatMoney(s.observed_monthly)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}

          <p className="text-xs text-white/40">{variance.data.note}</p>
        </div>
      )}
    </div>
  );
}
