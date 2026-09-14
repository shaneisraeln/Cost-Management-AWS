"use client";

import Link from "next/link";
import { useAccounts } from "@/lib/account";

export function AccountSelector() {
  const { connections, selectedAccountId, setSelectedAccountId, isLoading } =
    useAccounts();

  if (isLoading) {
    return <span className="text-xs text-white/40">Loading accounts…</span>;
  }

  if (connections.length === 0) {
    return (
      <Link
        href="/settings/aws"
        className="rounded bg-white/10 px-3 py-1.5 text-xs hover:bg-white/20"
      >
        + Connect AWS account
      </Link>
    );
  }

  return (
    <label className="flex items-center gap-2 text-xs text-white/60">
      <span>AWS account</span>
      <select
        value={selectedAccountId ?? ""}
        onChange={(e) => setSelectedAccountId(e.target.value)}
        className="rounded border border-white/15 bg-transparent px-2 py-1 text-sm text-white"
      >
        {connections.map((c) => (
          <option key={c.id} value={c.account_id!} className="bg-[#0b0f17]">
            {c.account_id}
            {c.status !== "CONNECTED" ? ` (${c.status})` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
