"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import type {
  ActionRequest,
  Attribution,
  RemediationPreview,
  Resource,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded border border-white/10 p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-white/50">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-white/5 py-1.5 text-sm last:border-0">
      <span className="text-white/50">{label}</span>
      <span className="font-mono">{value ?? "—"}</span>
    </div>
  );
}

export default function ResourceDetailPage() {
  const api = useApi();
  const queryClient = useQueryClient();
  const params = useParams<{ id: string }>();
  const [owner, setOwner] = useState("");
  const [project, setProject] = useState("");
  const [environment, setEnvironment] = useState("");

  const query = useQuery({
    queryKey: ["resource", params.id],
    queryFn: () => api<Resource>(`/resources/${params.id}`),
  });

  const attributions = useQuery({
    queryKey: ["attributions"],
    queryFn: () => api<Attribution[]>("/attributions"),
  });

  const setManual = useMutation({
    mutationFn: () =>
      api<Attribution>("/attributions/manual", {
        method: "POST",
        body: JSON.stringify({
          resource_id: params.id,
          owner_label: owner || null,
          project_id: project || null,
          environment: environment || null,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["attributions"] });
      queryClient.invalidateQueries({ queryKey: ["resource", params.id] });
    },
  });

  if (query.isLoading) return <p className="text-sm text-white/50">Loading…</p>;
  if (query.isError)
    return (
      <p className="text-sm text-red-300">{(query.error as Error).message}</p>
    );

  const r = query.data!;
  const attribution = attributions.data?.find((a) => a.resource_id === r.id);

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <Link href="/resources" className="text-sm text-white/50 hover:underline">
          ← Inventory
        </Link>
        <h1 className="mt-2 font-mono text-2xl font-semibold">
          {r.provider_resource_id}
        </h1>
        <p className="text-white/60">
          {r.service} / {r.resource_type}
        </p>
      </div>

      <Section title="Identity">
        <Row label="Resource ID" value={r.provider_resource_id} />
        <Row label="ARN" value={r.arn} />
        <Row label="Account" value={r.account_id} />
        <Row label="Region" value={r.region} />
        <Row label="State" value={r.state} />
        <Row
          label="Created (AWS)"
          value={
            r.provider_created_at
              ? new Date(r.provider_created_at).toLocaleString()
              : null
          }
        />
      </Section>

      <Section title="Ownership & attribution">
        <Row label="Status" value={attribution?.status ?? r.attribution_status ?? "UNKNOWN"} />
        <Row label="Owner" value={attribution?.owner_label} />
        <Row label="Environment" value={attribution?.environment ?? r.environment} />
        <Row
          label="Confidence"
          value={
            attribution
              ? `${(attribution.confidence * 100).toFixed(0)}%`
              : null
          }
        />
        <Row label="Source" value={attribution?.source} />

        {attribution && attribution.evidence.length > 0 && (
          <div className="mt-3">
            <div className="mb-1 text-xs text-white/50">Evidence</div>
            <ul className="space-y-1 text-sm">
              {attribution.evidence.map((e, i) => (
                <li key={i} className="text-white/70">
                  <span className="text-white/40">
                    [{e.type}, weight {e.weight}]
                  </span>{" "}
                  {e.detail}
                </li>
              ))}
            </ul>
          </div>
        )}
        {attribution && attribution.evidence.length === 0 && (
          <p className="mt-2 text-sm text-white/50">
            No ownership evidence found — not attributed to any owner.
          </p>
        )}

        {/* Manual mapping (overrides inference; never auto-replaced) */}
        <div className="mt-4 border-t border-white/10 pt-4">
          <div className="mb-2 text-xs text-white/50">Manual mapping</div>
          <div className="flex flex-wrap items-end gap-2">
            <input
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
              placeholder="owner"
              className="rounded border border-white/15 bg-transparent px-2 py-1.5 text-sm"
            />
            <input
              value={project}
              onChange={(e) => setProject(e.target.value)}
              placeholder="project id"
              className="rounded border border-white/15 bg-transparent px-2 py-1.5 text-sm"
            />
            <input
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
              placeholder="environment"
              className="rounded border border-white/15 bg-transparent px-2 py-1.5 text-sm"
            />
            <button
              onClick={() => setManual.mutate()}
              disabled={setManual.isPending}
              className="rounded bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20 disabled:opacity-50"
            >
              {setManual.isPending ? "Saving…" : "Set owner"}
            </button>
          </div>
        </div>
      </Section>

      <Section title="Tags">
        {Object.keys(r.tags).length > 0 ? (
          <div className="space-y-1">
            {Object.entries(r.tags).map(([k, v]) => (
              <Row key={k} label={k} value={v} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-white/50">No tags.</p>
        )}
      </Section>

      <Section title="Metadata">
        {Object.keys(r.resource_metadata).length > 0 ? (
          <div className="space-y-1">
            {Object.entries(r.resource_metadata).map(([k, v]) => (
              <Row key={k} label={k} value={String(v ?? "—")} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-white/50">No metadata.</p>
        )}
      </Section>

      {r.service === "EC2" && (
        <Section title="Remediation (stop instance)">
          <RemediationSection resourceId={r.id} />
        </Section>
      )}

      <p className="text-xs text-white/40">
        Source: AWS read-only discovery (describe/list). Cost, utilization,
        activity, and recommendations attach in later phases.
      </p>
    </div>
  );
}

function RemediationSection({ resourceId }: { resourceId: string }) {
  const api = useApi();
  const [previewing, setPreviewing] = useState(false);
  const [result, setResult] = useState<ActionRequest | null>(null);

  const preview = useQuery({
    queryKey: ["remediation-preview", resourceId],
    queryFn: () =>
      api<RemediationPreview>(`/remediation/preview?resource_id=${resourceId}`),
    enabled: previewing,
  });

  const stop = useMutation({
    mutationFn: () =>
      api<ActionRequest>("/remediation/stop-instance", {
        method: "POST",
        body: JSON.stringify({ resource_id: resourceId, confirm: true }),
      }),
    onSuccess: (data) => setResult(data),
  });

  if (!previewing) {
    return (
      <button
        onClick={() => setPreviewing(true)}
        className="rounded border border-white/15 px-3 py-1.5 text-sm hover:bg-white/10"
      >
        Review stop action
      </button>
    );
  }

  return (
    <div className="space-y-3">
      {preview.isLoading && <p className="text-sm text-white/50">Checking policy…</p>}

      {preview.data && (
        <>
          <div className="rounded border border-white/10 p-3 text-sm">
            <div>
              Resource:{" "}
              <span className="font-mono">{preview.data.provider_resource_id}</span>
            </div>
            <div>Current state: {preview.data.current_state ?? "—"}</div>
            <div>Proposed action: {preview.data.proposed_action}</div>
          </div>

          <div className="space-y-1">
            {preview.data.checks.map((c) => (
              <div key={c.check} className="text-xs">
                <span className={c.passed ? "text-green-300" : "text-red-300"}>
                  {c.passed ? "✓" : "✕"}
                </span>{" "}
                <span className="text-white/50">{c.check}:</span> {c.detail}
              </div>
            ))}
          </div>

          {result ? (
            <div
              className={`rounded border p-3 text-sm ${
                result.status === "EXECUTED"
                  ? "border-green-500/30 bg-green-500/10 text-green-200"
                  : "border-red-500/30 bg-red-500/10 text-red-200"
              }`}
            >
              Action {result.status}.{" "}
              {typeof result.result?.detail === "string"
                ? result.result.detail
                : typeof result.result?.error === "string"
                  ? result.result.error
                  : ""}
            </div>
          ) : preview.data.allowed ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-yellow-300">
                This will call ec2:StopInstances. This is a real write action.
              </span>
              <button
                onClick={() => stop.mutate()}
                disabled={stop.isPending}
                className="rounded bg-red-500/20 px-3 py-1.5 text-sm text-red-100 hover:bg-red-500/30 disabled:opacity-50"
              >
                {stop.isPending ? "Stopping…" : "Confirm & stop instance"}
              </button>
            </div>
          ) : (
            <div className="rounded border border-yellow-500/30 bg-yellow-500/10 p-2 text-xs text-yellow-200">
              Blocked by policy: {preview.data.reasons.join("; ")}
            </div>
          )}
        </>
      )}
    </div>
  );
}
