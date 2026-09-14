"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AwsConnection, OwnerSummary } from "@/lib/types";
import { useApi } from "@/lib/useApi";

interface AttributionRunResultShape {
  resources: number;
  by_status: Record<string, number>;
}

export default function PeoplePage() {
  const api = useApi();
  const queryClient = useQueryClient();

  const connections = useQuery({
    queryKey: ["aws-connections"],
    queryFn: () => api<AwsConnection[]>("/aws/connections"),
  });
  const people = useQuery({
    queryKey: ["people"],
    queryFn: () => api<OwnerSummary>("/people"),
  });

  const connection = connections.data?.[0];

  const syncActivity = useMutation({
    mutationFn: () =>
      api<{ events_added: number; identities_seen: number }>(
        `/attributions/sync-activity?connection_id=${connection!.id}&days=90`,
        { method: "POST" },
      ),
    onSuccess: () => runAttribution.mutate(),
  });

  const runAttribution = useMutation({
    mutationFn: () =>
      api<AttributionRunResultShape>("/attributions/run", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["people"] }),
  });

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">People</h1>
          <p className="mt-1 text-white/60">
            Ownership inferred from tags and CloudTrail activity. Unknown and
            Shared are shown honestly — we never invent an owner.
          </p>
        </div>
        <button
          onClick={() => syncActivity.mutate()}
          disabled={
            !connection || syncActivity.isPending || runAttribution.isPending
          }
          className="rounded bg-white/10 px-4 py-2 text-sm hover:bg-white/20 disabled:opacity-50"
        >
          {syncActivity.isPending || runAttribution.isPending
            ? "Attributing…"
            : "Sync activity & attribute"}
        </button>
      </div>

      {runAttribution.isSuccess && (
        <p className="text-sm text-green-300">
          Attributed {runAttribution.data.resources} resources.
        </p>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded border border-white/10 p-4">
          <div className="text-xs text-white/50">Unknown owner</div>
          <div className="mt-1 text-2xl font-semibold">
            {people.data?.unknown_count ?? "—"}
          </div>
        </div>
        <div className="rounded border border-white/10 p-4">
          <div className="text-xs text-white/50">Shared</div>
          <div className="mt-1 text-2xl font-semibold">
            {people.data?.shared_count ?? "—"}
          </div>
        </div>
      </div>

      <section className="rounded border border-white/10 p-4">
        <h2 className="mb-3 text-lg font-medium">Owners</h2>
        {people.data && people.data.owners.length > 0 ? (
          <table className="w-full text-sm">
            <tbody>
              {people.data.owners.map((o) => (
                <tr key={o.owner_label} className="border-t border-white/5">
                  <td className="py-1.5">{o.owner_label}</td>
                  <td className="py-1.5 text-right text-white/60">
                    {o.resource_count} resource
                    {o.resource_count === 1 ? "" : "s"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-white/50">
            No attributed owners yet. Resources may lack owner tags or
            CloudTrail creation history.
          </p>
        )}
      </section>
    </div>
  );
}
