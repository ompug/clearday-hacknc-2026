import type { SkyBubble, SkyCluster } from "./api/types";
import { dueDayName } from "./dates";
import { formatCents } from "./money";

/**
 * Display state of a bubble. Every state has an icon and a text label so
 * colour is never the only signal.
 */
export type BubbleState = "clear" | "watch" | "tight" | "waiting" | "disputed";

export const STATE_LABELS: Record<BubbleState, string> = {
  clear: "Likely covered",
  watch: "Could be tight",
  tight: "Likely short",
  waiting: "Your share paid",
  disputed: "On hold",
};

export function bubbleState(bubble: SkyBubble): BubbleState {
  if (bubble.status === "disputed") return "disputed";
  if (bubble.status === "paid") return "waiting";
  return bubble.weather;
}

export function canPay(bubble: SkyBubble): boolean {
  return bubble.payable && (bubble.status === "open" || bubble.status === "partial");
}

/** Why an open bubble can't be paid here, or null. Read out with the bubble's name. */
export function notPayableReason(bubble: SkyBubble): string | null {
  if (bubble.payable || bubble.status === "paid" || bubble.status === "disputed") return null;
  return "Renews automatically, nothing to pay here";
}

export function progressLabel(bubble: SkyBubble): string | null {
  if (bubble.kind !== "shared") return null;
  return `${bubble.paid_count} of ${bubble.participant_count} paid`;
}

/** e.g. "Rent, $600.00 your share, due Friday, 1 of 3 paid, could be tight". */
export function bubbleAccessibleName(bubble: SkyBubble): string {
  const amount =
    bubble.kind === "shared"
      ? `${formatCents(bubble.your_share_cents)} your share`
      : formatCents(bubble.your_share_cents);
  const parts = [bubble.label, amount, `due ${dueDayName(bubble.due_date)}`];
  const progress = progressLabel(bubble);
  if (progress) parts.push(progress);
  parts.push(STATE_LABELS[bubbleState(bubble)].toLowerCase());
  const reason = notPayableReason(bubble);
  if (reason) parts.push(reason.toLowerCase());
  return parts.join(", ");
}

const SEVERITY: Record<BubbleState, number> = {
  tight: 4,
  watch: 3,
  disputed: 2,
  clear: 1,
  waiting: 0,
};

export interface ClusterSummary {
  cluster: SkyCluster;
  members: SkyBubble[];
  totalCents: number;
  earliestDue: string;
  state: BubbleState;
}

export function summarizeCluster(cluster: SkyCluster, bubbles: SkyBubble[]): ClusterSummary {
  const members = bubbles.filter((b) => cluster.bubble_ids.includes(b.bubble_id));
  const state = members
    .map(bubbleState)
    .reduce<BubbleState>((worst, s) => (SEVERITY[s] > SEVERITY[worst] ? s : worst), "waiting");
  return {
    cluster,
    members,
    totalCents: members.reduce((sum, b) => sum + b.your_share_cents, 0),
    earliestDue: members.map((b) => b.due_date).sort()[0] ?? "",
    state,
  };
}

export function clusterAccessibleName(summary: ClusterSummary, expanded: boolean): string {
  return [
    `${summary.cluster.label}, ${summary.members.length} bills`,
    `${formatCents(summary.totalCents)} total`,
    `next due ${dueDayName(summary.earliestDue)}`,
    STATE_LABELS[summary.state].toLowerCase(),
    expanded ? "expanded" : "collapsed",
  ].join(", ");
}

/** A sky entry is either a single bubble or a cluster of them. */
export type SkyEntry =
  | { type: "bubble"; bubble: SkyBubble; due: string }
  | { type: "cluster"; summary: ClusterSummary; due: string };

export function skyEntries(bubbles: SkyBubble[], clusters: SkyCluster[]): SkyEntry[] {
  const entries: SkyEntry[] = bubbles
    .filter((b) => !b.cluster_id)
    .map((bubble) => ({ type: "bubble", bubble, due: bubble.due_date }));
  for (const cluster of clusters) {
    const summary = summarizeCluster(cluster, bubbles);
    if (summary.members.length > 0)
      entries.push({ type: "cluster", summary, due: summary.earliestDue });
  }
  return entries.sort((a, b) => a.due.localeCompare(b.due));
}
