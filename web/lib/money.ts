import type { Cents } from "./api/types";

const groupFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/**
 * The only place cents become a display string. Integer math only:
 * 123456 -> "$1,234.56", -5 -> "-$0.05".
 */
export function formatCents(cents: Cents): string {
  if (!Number.isSafeInteger(cents)) {
    throw new TypeError(`formatCents expects integer cents, got ${String(cents)}`);
  }
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const remainder = abs % 100;
  const dollars = (abs - remainder) / 100;
  return `${sign}$${groupFormatter.format(dollars)}.${String(remainder).padStart(2, "0")}`;
}
