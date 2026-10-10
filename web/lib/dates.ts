import type { IsoDate } from "./api/types";

/** Due dates display in the household's time zone. */
export const DISPLAY_TIME_ZONE = "America/New_York";

const isoFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: DISPLAY_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** Today's date in America/New_York as `YYYY-MM-DD`. */
export function todayIso(now: Date = new Date()): IsoDate {
  return isoFormatter.format(now);
}

function isoToUtcMs(iso: IsoDate): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

const DAY_MS = 86_400_000;

export function addDays(iso: IsoDate, days: number): IsoDate {
  return new Date(isoToUtcMs(iso) + days * DAY_MS).toISOString().slice(0, 10);
}

/** Whole days from `from` to `to` (negative when `to` is in the past). */
export function daysBetween(from: IsoDate, to: IsoDate): number {
  return Math.round((isoToUtcMs(to) - isoToUtcMs(from)) / DAY_MS);
}

const weekdayFormatter = new Intl.DateTimeFormat("en-US", { weekday: "long", timeZone: "UTC" });
const shortDateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

/** "Due today", "Due tomorrow", "Due in 3 days", "Overdue by 2 days". */
export function dueLabel(due: IsoDate, today: IsoDate = todayIso()): string {
  const days = daysBetween(today, due);
  if (days < 0) return `Overdue by ${-days} ${-days === 1 ? "day" : "days"}`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `Due in ${days} days`;
}

/** "Friday" within the next week, otherwise "Oct 21". */
export function dueDayName(due: IsoDate, today: IsoDate = todayIso()): string {
  const days = daysBetween(today, due);
  const date = new Date(isoToUtcMs(due));
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days > 1 && days < 7) return weekdayFormatter.format(date);
  return shortDateFormatter.format(date);
}
