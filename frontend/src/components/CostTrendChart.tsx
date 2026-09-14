"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailyCostPoint } from "@/lib/types";

export function CostTrendChart({ data }: { data: DailyCostPoint[] }) {
  const points = data.map((p) => ({
    date: p.date.slice(5), // MM-DD
    amount: Number(p.amount),
  }));

  if (points.length === 0) {
    return <p className="text-sm text-white/50">No daily data for this range.</p>;
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points}>
          <CartesianGrid strokeDasharray="3 3" stroke="#ffffff14" />
          <XAxis dataKey="date" tick={{ fill: "#9aa4b2", fontSize: 11 }} />
          <YAxis tick={{ fill: "#9aa4b2", fontSize: 11 }} width={70} />
          <Tooltip
            contentStyle={{
              background: "#0b0f17",
              border: "1px solid #ffffff22",
              borderRadius: 6,
              fontSize: 12,
            }}
            formatter={(v: number) => [`$${v.toFixed(6)}`, "cost"]}
          />
          <Bar dataKey="amount" fill="#5b9dff" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
