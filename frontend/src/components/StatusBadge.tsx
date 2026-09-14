import type { ConnectionStatus } from "@/lib/types";

const STYLES: Record<ConnectionStatus, string> = {
  CONNECTED: "bg-green-500/15 text-green-300 border-green-500/30",
  DEGRADED: "bg-yellow-500/15 text-yellow-300 border-yellow-500/30",
  ERROR: "bg-red-500/15 text-red-300 border-red-500/30",
  PENDING: "bg-white/10 text-white/60 border-white/20",
};

export function StatusBadge({ status }: { status: ConnectionStatus }) {
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}
