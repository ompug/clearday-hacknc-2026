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

export interface ItemizedLine {
  amount_cents: Cents;
  /** Who shares this item; each owner pays an equal part. */
  user_ids: string[];
}

/** `total` divided in proportion to integer `weights`, largest remainder, ties by user ID. */
function largestRemainder(total: Cents, weights: Map<string, number>): Map<string, Cents> {
  const ids = [...weights.keys()].sort();
  const weightSum = ids.reduce((s, id) => s + weights.get(id)!, 0);
  const base = new Map<string, Cents>();
  const rest = new Map<string, number>();
  for (const id of ids) {
    const product = total * weights.get(id)!;
    base.set(id, Math.floor(product / weightSum));
    rest.set(id, product % weightSum);
  }
  let leftover = total - [...base.values()].reduce((s, v) => s + v, 0);
  for (const id of [...ids].sort((a, b) => rest.get(b)! - rest.get(a)! || (a < b ? -1 : 1))) {
    if (leftover <= 0) break;
    base.set(id, base.get(id)! + 1);
    leftover -= 1;
  }
  return base;
}

/**
 * Itemized preview, the same rules as `analytics.splits` (items split evenly among their owners;
 * tax and tip follow each person's item subtotal). The server stores the per-person totals as a
 * custom split and checks they add up.
 */
export function previewItemizedSplit(
  items: ItemizedLine[],
  taxCents: Cents,
  tipCents: Cents,
  userIds: string[],
): Map<string, Cents> {
  const result = new Map<string, Cents>(userIds.map((id) => [id, 0]));
  for (const item of items) {
    const owners = new Map(item.user_ids.filter((id) => result.has(id)).map((id) => [id, 1]));
    if (owners.size === 0) continue;
    for (const [id, cents] of largestRemainder(item.amount_cents, owners)) {
      result.set(id, result.get(id)! + cents);
    }
  }
  const subtotals = new Map(result);
  const anySubtotal = [...subtotals.values()].some((v) => v > 0);
  const basis = anySubtotal ? subtotals : new Map(userIds.map((id) => [id, 1]));
  if (basis.size === 0) return result;
  for (const extra of [taxCents, tipCents]) {
    for (const [id, cents] of largestRemainder(extra, basis)) {
      result.set(id, result.get(id)! + cents);
    }
  }
  return result;
}
