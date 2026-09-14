"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CopyButton } from "@/components/CopyButton";
import { StatusBadge } from "@/components/StatusBadge";
import type {
  AwsConnection,
  ConnectionSetupInfo,
  ValidationResult,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export default function AwsSettingsPage() {
  const api = useApi();
  const queryClient = useQueryClient();

  const connectionsQuery = useQuery({
    queryKey: ["aws-connections"],
    queryFn: () => api<AwsConnection[]>("/aws/connections"),
  });

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Connect AWS Account</h1>
        <p className="mt-2 text-white/70">
          Your AWS account stays under your control. We use a read-only IAM role
          to retrieve cloud cost, resource, usage, and activity information. We
          never ask for your AWS password, access keys, or root credentials.
        </p>
      </div>

      <ConnectWizard
        onConnected={() =>
          queryClient.invalidateQueries({ queryKey: ["aws-connections"] })
        }
      />

      <FaqSection />

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Your connections</h2>
        {connectionsQuery.isLoading && (
          <p className="text-sm text-white/50">Loading…</p>
        )}
        {connectionsQuery.data?.length === 0 && (
          <p className="text-sm text-white/50">
            No AWS accounts connected yet.
          </p>
        )}
        {connectionsQuery.data?.map((conn) => (
          <ConnectionCard key={conn.id} conn={conn} />
        ))}
      </section>

      <LocalProfileAdvanced
        onCreated={() =>
          queryClient.invalidateQueries({ queryKey: ["aws-connections"] })
        }
      />
    </div>
  );
}

const STEPS = ["Account", "IAM Role", "Permissions", "Connect", "Verify"];

function ConnectWizard({ onConnected }: { onConnected: () => void }) {
  const api = useApi();
  const [step, setStep] = useState(0);
  const [accountId, setAccountId] = useState("");
  const [roleArn, setRoleArn] = useState("");
  const [region, setRegion] = useState("us-east-1");
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [showPolicy, setShowPolicy] = useState(false);
  const [showTrust, setShowTrust] = useState(false);

  const setup = useQuery({
    queryKey: ["aws-setup-info", region],
    queryFn: () =>
      api<ConnectionSetupInfo>(`/aws/connections/setup-info?region=${region}`),
  });

  const connect = useMutation({
    mutationFn: async () => {
      const conn = await api<AwsConnection>("/aws/connections", {
        method: "POST",
        body: JSON.stringify({
          auth_mode: "ASSUME_ROLE",
          account_id: accountId || null,
          role_arn: roleArn,
          region,
        }),
      });
      return api<ValidationResult>(`/aws/connections/${conn.id}/validate`, {
        method: "POST",
      });
    },
    onSuccess: (data) => {
      setResult(data);
      setStep(4);
      onConnected();
    },
  });

  const info = setup.data;
  const policyJson = info ? JSON.stringify(info.read_policy, null, 2) : "";
  const trustJson =
    info && info.trust_policy
      ? JSON.stringify(info.trust_policy, null, 2)
      : "";

  return (
    <section className="rounded border border-white/10 p-5">
      {/* Progress */}
      <ol className="mb-5 flex flex-wrap gap-2 text-xs">
        {STEPS.map((label, i) => (
          <li
            key={label}
            className={`rounded px-2 py-1 ${
              i === step
                ? "bg-white/15 text-white"
                : i < step
                  ? "bg-green-500/15 text-green-300"
                  : "bg-white/5 text-white/40"
            }`}
          >
            {i + 1}. {label}
          </li>
        ))}
      </ol>

      {info && !info.assume_role_available && (
        <div className="mb-4 rounded border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-200">
          This deployment isn&apos;t configured for cross-account connections
          yet. {info.prerequisite_note}
        </div>
      )}

      {/* Step 0: Account ID */}
      {step === 0 && (
        <div className="space-y-3">
          <h3 className="font-medium">Step 1 — Find your AWS Account ID</h3>
          <p className="text-sm text-white/60">
            Sign in to the AWS Console. Your 12-digit account ID is shown in the
            top-right account menu (click your account name → the ID appears at
            the top). Enter it below.
          </p>
          <input
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            placeholder="123456789012"
            className="w-64 rounded border border-white/15 bg-transparent px-3 py-2 text-sm"
          />
          <div>
            <button
              onClick={() => setStep(1)}
              className="rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Step 1: Create the role */}
      {step === 1 && (
        <div className="space-y-3">
          <h3 className="font-medium">Step 2 — Create the IAM role</h3>
          <p className="text-sm text-white/60">
            In the AWS Console, open <strong>IAM → Roles → Create role</strong>.
            Choose <strong>Custom trust policy</strong> (we&apos;ll give you the
            exact text on the Permissions step). Name the role something like{" "}
            <code className="text-white/80">CloudCostControlReadOnly</code>.
          </p>
          <p className="text-sm text-white/60">
            This role lets our application access your account temporarily and
            read-only. You can delete it any time to revoke access.
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setStep(0)}
              className="rounded border border-white/15 px-4 py-2 text-sm hover:bg-white/10"
            >
              Back
            </button>
            <button
              onClick={() => setStep(2)}
              className="rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Permissions + trust */}
      {step === 2 && (
        <div className="space-y-4">
          <h3 className="font-medium">Step 3 — Permissions & trust</h3>

          {/* Trust policy */}
          <div className="rounded border border-white/10 p-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium">Trust policy</div>
              {!!info?.trust_policy && (
                <CopyButton value={trustJson} label="Copy trust policy" />
              )}
            </div>
            <p className="mt-1 text-xs text-white/60">
              Paste this as the role&apos;s trust relationship. It allows only
              our application to assume the role, and only when the External ID
              matches.
            </p>
            {info?.app_principal_arn && (
              <div className="mt-2 flex items-center gap-2 text-xs">
                <span className="text-white/50">Trusted principal:</span>
                <code className="text-white/80">{info.app_principal_arn}</code>
                <CopyButton value={info.app_principal_arn} />
              </div>
            )}
            {info && (
              <div className="mt-2 flex items-center gap-2 text-xs">
                <span className="text-white/50">External ID:</span>
                <code className="text-white/80">{info.external_id}</code>
                <CopyButton value={info.external_id} label="Copy External ID" />
              </div>
            )}
            {!!info?.trust_policy && (
              <button
                onClick={() => setShowTrust((v) => !v)}
                className="mt-2 text-xs text-white/50 underline"
              >
                {showTrust ? "Hide" : "Show"} trust policy JSON
              </button>
            )}
            {showTrust && (
              <pre className="mt-2 overflow-auto rounded bg-black/30 p-2 text-[11px] text-white/70">
                {trustJson}
              </pre>
            )}
          </div>

          {/* Read policy */}
          <div className="rounded border border-white/10 p-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium">
                Read-only permissions policy
              </div>
              <CopyButton value={policyJson} label="Copy policy" />
            </div>
            <p className="mt-1 text-xs text-white/60">
              Attach this policy to the role. It is strictly read-only — no
              permission here can create, modify, stop, or delete anything.
            </p>
            <button
              onClick={() => setShowPolicy((v) => !v)}
              className="mt-2 text-xs text-white/50 underline"
            >
              {showPolicy ? "Hide" : "Show"} IAM policy JSON
            </button>
            {showPolicy && (
              <pre className="mt-2 overflow-auto rounded bg-black/30 p-2 text-[11px] text-white/70">
                {policyJson}
              </pre>
            )}
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setStep(1)}
              className="rounded border border-white/15 px-4 py-2 text-sm hover:bg-white/10"
            >
              Back
            </button>
            <button
              onClick={() => setStep(3)}
              className="rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Paste Role ARN + connect */}
      {step === 3 && (
        <div className="space-y-3">
          <h3 className="font-medium">Step 4 — Paste the Role ARN & connect</h3>
          <p className="text-sm text-white/60">
            After creating the role, open it in IAM and copy its{" "}
            <strong>Role ARN</strong> (top of the role summary). Paste it here.
          </p>
          <input
            value={roleArn}
            onChange={(e) => setRoleArn(e.target.value)}
            placeholder="arn:aws:iam::123456789012:role/CloudCostControlReadOnly"
            className="w-full rounded border border-white/15 bg-transparent px-3 py-2 text-sm"
          />
          <label className="block text-sm">
            <span className="mb-1 block text-white/60">Primary region</span>
            <input
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-40 rounded border border-white/15 bg-transparent px-3 py-2 text-sm"
            />
          </label>
          {connect.isError && (
            <p className="text-sm text-red-300">
              {(connect.error as Error).message}
            </p>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => setStep(2)}
              className="rounded border border-white/15 px-4 py-2 text-sm hover:bg-white/10"
            >
              Back
            </button>
            <button
              onClick={() => connect.mutate()}
              disabled={!roleArn || connect.isPending}
              className="rounded bg-blue-500/20 px-4 py-2 text-sm text-blue-100 hover:bg-blue-500/30 disabled:opacity-50"
            >
              {connect.isPending ? "Connecting…" : "Connect & Validate"}
            </button>
          </div>
        </div>
      )}

      {/* Step 4: Result */}
      {step === 4 && result && (
        <div className="space-y-3">
          <h3 className="font-medium">Step 5 — Result</h3>
          {result.status === "CONNECTED" ? (
            <div className="rounded border border-green-500/30 bg-green-500/10 p-3 text-sm text-green-200">
              ✓ AWS account connected — {result.account_id}
            </div>
          ) : result.status === "DEGRADED" ? (
            <div className="rounded border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-200">
              Connected, but some capabilities are unavailable.
              {result.error_message ? ` ${result.error_message}` : ""}
            </div>
          ) : (
            <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
              {result.error_message ?? "Could not connect."}
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {result.permissions.map((p) => (
              <span
                key={p.capability}
                className={`rounded border px-2 py-0.5 text-xs ${
                  p.available
                    ? "border-green-500/30 bg-green-500/10 text-green-300"
                    : "border-red-500/30 bg-red-500/10 text-red-300"
                }`}
                title={p.detail ?? ""}
              >
                {p.available ? "✓" : "✕"} {p.label}
              </span>
            ))}
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => {
                setStep(0);
                setResult(null);
              }}
              className="rounded border border-white/15 px-4 py-2 text-sm hover:bg-white/10"
            >
              Connect another account
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function ConnectionCard({ conn }: { conn: AwsConnection }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const revalidate = useMutation({
    mutationFn: () =>
      api<ValidationResult>(`/aws/connections/${conn.id}/validate`, {
        method: "POST",
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["aws-connections"] }),
  });

  return (
    <div className="rounded border border-white/10 p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-mono text-sm">
            {conn.account_id ?? "Account not yet discovered"}
          </div>
          <div className="text-xs text-white/50">
            {conn.auth_mode} · {conn.region}
            {conn.read_only ? " · read-only" : ""}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={conn.status} />
          <button
            onClick={() => revalidate.mutate()}
            disabled={revalidate.isPending}
            className="rounded bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20 disabled:opacity-50"
          >
            {revalidate.isPending ? "Validating…" : "Re-validate"}
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-white/60">
        <div>Last cost sync: {formatDate(conn.last_cost_sync)}</div>
        <div>Last resource sync: {formatDate(conn.last_resource_sync)}</div>
      </div>

      {Object.keys(conn.permission_status).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(conn.permission_status).map(([cap, ok]) => (
            <span
              key={cap}
              className={`rounded border px-2 py-0.5 text-xs ${
                ok
                  ? "border-green-500/30 bg-green-500/10 text-green-300"
                  : "border-red-500/30 bg-red-500/10 text-red-300"
              }`}
            >
              {ok ? "✓" : "✕"} {cap}
            </span>
          ))}
        </div>
      )}

      {conn.last_error && (
        <p className="mt-2 text-xs text-red-300">{conn.last_error}</p>
      )}
    </div>
  );
}

function FaqSection() {
  const items = [
    {
      q: "Why do we need this?",
      a: "To read your AWS cost, resource, usage, and activity data so we can show you spending, attribution, and recommendations.",
    },
    {
      q: "Is this safe?",
      a: "We use a read-only IAM role and temporary credentials obtained through AWS STS. We never receive your password, access keys, or root credentials. No setup is completely risk-free, but the role cannot perform write actions.",
    },
    {
      q: "What permissions are we requesting?",
      a: "Read-only Cost Explorer, EC2/EBS/S3/RDS describe/list, CloudTrail lookup, and CloudWatch (for Bedrock usage). No write permissions of any kind.",
    },
    {
      q: "How can I remove access later?",
      a: "Delete the IAM role in your AWS account, or remove our application's principal from the role's trust relationship. Access stops immediately.",
    },
  ];
  return (
    <section className="rounded border border-white/10 p-4">
      <h2 className="mb-2 text-lg font-medium">Good to know</h2>
      <div className="space-y-3">
        {items.map((it) => (
          <div key={it.q}>
            <div className="text-sm font-medium">{it.q}</div>
            <p className="text-sm text-white/60">{it.a}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function LocalProfileAdvanced({ onCreated }: { onCreated: () => void }) {
  const api = useApi();
  const [open, setOpen] = useState(false);
  const [profileName, setProfileName] = useState("");
  const [region, setRegion] = useState("us-east-1");

  const create = useMutation({
    mutationFn: async () => {
      const conn = await api<AwsConnection>("/aws/connections", {
        method: "POST",
        body: JSON.stringify({
          auth_mode: "LOCAL_PROFILE",
          profile_name: profileName || null,
          region,
        }),
      });
      await api(`/aws/connections/${conn.id}/validate`, { method: "POST" });
      return conn;
    },
    onSuccess: onCreated,
  });

  return (
    <section className="rounded border border-white/10 p-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-sm text-white/50 underline"
      >
        {open ? "Hide" : "Show"} advanced: local development profile
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-white/50">
            For local development only. Uses a host AWS profile via the default
            credential chain — not for production customers.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <input
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              placeholder="profile (optional)"
              className="rounded border border-white/15 bg-transparent px-3 py-2 text-sm"
            />
            <input
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-32 rounded border border-white/15 bg-transparent px-3 py-2 text-sm"
            />
            <button
              onClick={() => create.mutate()}
              disabled={create.isPending}
              className="rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20 disabled:opacity-50"
            >
              {create.isPending ? "Creating…" : "Create local connection"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
