import type { Cents } from "@/lib/api";

const DOLLARS = /^(\d{1,7})(?:\.(\d{0,2}))?$/;

/**
 * Parses what a person typed ("12", "12.5", "$1,234.56") into integer cents with string math only.
 * Returns null for anything that isn't a plain non-negative amount with at most two decimals.
 */
export function parseDollarsToCents(input: string): Cents | null {
  const cleaned = input.trim().replace(/^\$/, "").replace(/,/g, "").trim();
  const match = DOLLARS.exec(cleaned);
  if (!match) return null;
  const whole = Number(match[1]);
  const fraction = (match[2] ?? "").padEnd(2, "0");
  return whole * 100 + Number(fraction);
}

/** Cents back to an editable string ("1234.50"), no symbol or grouping. */
export function centsToInput(cents: Cents): string {
  const remainder = cents % 100;
  return `${(cents - remainder) / 100}.${String(remainder).padStart(2, "0")}`;
}

/**
 * Even split preview with the largest-remainder method, ties broken by user ID, the same rule as
 * analytics/splits.py. The server recomputes the real shares; this only previews them.
 */
export function previewEvenSplit(totalCents: Cents, userIds: string[]): Map<string, Cents> {
  const sorted = [...userIds].sort();
  const result = new Map<string, Cents>();
  if (sorted.length === 0) return result;
  const base = Math.floor(totalCents / sorted.length);
  let leftover = totalCents - base * sorted.length;
  for (const id of sorted) {
    const extra = leftover > 0 ? 1 : 0;
    leftover -= extra;
    result.set(id, base + extra);
  }
  return result;
}
