import type { Cents, IsoDate } from "@/lib/api";

const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Axis ticks only: whole dollars, compact from 1,000 up ("$450", "$1.2K", "-$80"). */
export function formatAxisDollars(cents: Cents): string {
  const dollars = Math.round(Math.abs(cents) / 100);
  return `${cents < 0 ? "-" : ""}$${compact.format(dollars)}`;
}

const shortDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});
const longDate = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function toUtc(iso: IsoDate): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1));
}

/** "Oct 12" */
export function formatShortDate(iso: IsoDate): string {
  return shortDate.format(toUtc(iso));
}

/** "Mon, Oct 12" */
export function formatLongDate(iso: IsoDate): string {
  return longDate.format(toUtc(iso));
}

/** Plain-language risk of dipping below the cushion, never a raw probability. */
export function cushionRisk(p: number): string {
  const tenths = Math.round(p * 10);
  if (tenths <= 0) return "Less than 1 in 10 chance of dipping below your cushion";
  if (tenths >= 10) return "Almost certain to dip below your cushion";
  return `About ${tenths} in 10 chance of dipping below your cushion`;
}

/** "groceries" -> "Groceries", "rideshare" -> "Rideshare". */
export function categoryLabel(category: string): string {
  const text = category.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
