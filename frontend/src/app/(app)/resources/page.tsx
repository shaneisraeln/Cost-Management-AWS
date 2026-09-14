"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type {
  AwsConnection,
  Resource,
  ResourceSyncResult,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function ResourcesPage() {
  const api = useApi();
  const queryClient = useQueryClient();
  const [service, setService] = useState<string>("");

  const connections = useQuery({
    queryKey: ["aws-connections"],
    queryFn: () => api<AwsConnection[]>("/aws/connections"),
  });

  const resources = useQuery({
    queryKey: ["resources", service],
    queryFn: () =>
      api<Resource[]>(`/resources${service ? `?service=${service}` : ""}`),
  });

  const connection = connections.data?.[0];

  const sync = useMutation({
    mutationFn: () =>
      api<ResourceSyncResult>(`/resources/sync?connection_id=${connection!.id}`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      queryClient.invalidateQueries({ queryKey: ["aws-connections"] });
    },
  });

  const services = ["", "EC2", "EBS", "S3", "RDS"];

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Resource Inventory</h1>
          <p className="mt-1 text-white/60">
            Read-only discovery of EC2, EBS, S3, and RDS resources.
          </p>
        </div>
        <button
          onClick={() => sync.mutate()}
          disabled={!connection || sync.isPending}
          className="rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20 disabled:opacity-50"
        >
          {sync.isPending ? "Discovering…" : "Discover resources"}
        </button>
      </div>

      {!connection && (
        <div className="rounded border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm text-yellow-200">
          No AWS connection yet. Add one in Settings → AWS first.
        </div>
      )}

      {sync.isError && (
        <p className="text-sm text-red-300">{(sync.error as Error).message}</p>
      )}
      {sync.isSuccess && (
        <p className="text-sm text-green-300">
          Discovered {sync.data.discovered} resources (
          {Object.entries(sync.data.by_service)
            .map(([s, n]) => `${s}: ${n}`)
            .join(", ") || "none"}
          ).
        </p>
      )}

      {/* Service filter */}
      <div className="flex gap-2">
        {services.map((s) => (
          <button
            key={s || "all"}
            onClick={() => setService(s)}
            className={`rounded border px-3 py-1 text-sm ${
              service === s
                ? "border-white/40 bg-white/10"
                : "border-white/10 text-white/60 hover:bg-white/5"
            }`}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="rounded border border-white/10">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 text-left text-white/50">
              <th className="p-3">Resource</th>
              <th className="p-3">Service</th>
              <th className="p-3">Type</th>
              <th className="p-3">Region</th>
              <th className="p-3">State</th>
              <th className="p-3">Tags</th>
            </tr>
          </thead>
          <tbody>
            {resources.isLoading && (
              <tr>
                <td colSpan={6} className="p-4 text-white/50">
                  Loading…
                </td>
              </tr>
            )}
            {resources.data?.length === 0 && (
              <tr>
                <td colSpan={6} className="p-4 text-white/50">
                  No resources. Click “Discover resources”.
                </td>
              </tr>
            )}
            {resources.data?.map((r) => (
              <tr key={r.id} className="border-b border-white/5">
                <td className="p-3">
                  <Link
                    href={`/resources/${r.id}`}
                    className="font-mono text-blue-300 hover:underline"
                  >
                    {r.provider_resource_id}
                  </Link>
                </td>
                <td className="p-3">{r.service}</td>
                <td className="p-3">{r.resource_type}</td>
                <td className="p-3">{r.region ?? "—"}</td>
                <td className="p-3">{r.state ?? "—"}</td>
                <td className="p-3 text-white/60">
                  {Object.keys(r.tags).length > 0
                    ? Object.entries(r.tags)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(", ")
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
