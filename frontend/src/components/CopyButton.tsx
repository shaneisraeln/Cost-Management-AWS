"use client";

import { useState } from "react";

export function CopyButton({
  value,
  label = "Copy",
}: {
  value: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable; ignore */
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      className="rounded border border-white/15 px-2 py-1 text-xs hover:bg-white/10"
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}
