export function formatMoney(amount: string | number, currency = "USD"): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  // Show more precision for tiny amounts so near-zero dev spend is still visible.
  const abs = Math.abs(value);
  const digits = abs > 0 && abs < 0.01 ? 6 : 2;
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(value);
  } catch {
    return `${value.toFixed(digits)} ${currency}`;
  }
}

export function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}
