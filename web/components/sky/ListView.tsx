"use client";

import type { SkyBubble } from "@/lib/api";
import { bubbleState, progressLabel, type SkyEntry } from "@/lib/bubbles";
import { dueLabel } from "@/lib/dates";
import { formatCents } from "@/lib/money";
import { PeopleIcon, StackIcon } from "../icons";
import { StateBadge } from "../StateBadge";

function Row({ bubble, onOpen }: { bubble: SkyBubble; onOpen: (b: SkyBubble) => void }) {
  const state = bubbleState(bubble);
  const progress = progressLabel(bubble);
  return (
    <button
      type="button"
      onClick={() => onOpen(bubble)}
      data-bubble-id={bubble.bubble_id}
      className="aero-tile flex w-full items-start justify-between gap-4 rounded-2xl px-4 py-3 text-left transition hover:shadow-md"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-lg font-bold break-words text-navy-950">{bubble.label}</span>
        <span className="block text-navy-800">
          {dueLabel(bubble.due_date)}
          {progress ? (
            <>
              {" · "}
              <PeopleIcon className="inline size-4 align-[-0.15em]" /> {progress}
            </>
          ) : null}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1 text-right">
        <span className="block text-lg font-bold text-navy-950 tabular-nums">
          {formatCents(bubble.your_share_cents)}
        </span>
        {bubble.kind === "shared" ? (
          <span className="block text-sm text-navy-800">
            your share of {formatCents(bubble.total_cents)}
          </span>
        ) : null}
        <StateBadge state={state} />
      </span>
    </button>
  );
}

/** Accessible default view: every bubble as a row, soonest first. */
export function ListView({
  entries,
  onOpen,
}: {
  entries: SkyEntry[];
  onOpen: (bubble: SkyBubble) => void;
}) {
  if (entries.length === 0) {
    return (
      <p className="rounded-2xl bg-white/80 px-4 py-6 text-lg font-semibold">
        Clear skies. Every bill is paid.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-3" aria-label="Bills, soonest due first">
      {entries.map((entry) =>
        entry.type === "bubble" ? (
          <li key={entry.bubble.bubble_id}>
            <Row bubble={entry.bubble} onOpen={onOpen} />
          </li>
        ) : (
          <li key={entry.summary.cluster.cluster_id}>
            <section
              aria-labelledby={`${entry.summary.cluster.cluster_id}-heading`}
              className="rounded-3xl border border-white/80 bg-sky-100/70 p-3"
            >
              <h3
                id={`${entry.summary.cluster.cluster_id}-heading`}
                className="flex items-center gap-2 px-1 pb-2 font-bold text-navy-950"
              >
                <StackIcon className="size-5" />
                {entry.summary.cluster.label}
                <span className="font-medium text-navy-800">
                  · {entry.summary.members.length} bills · {formatCents(entry.summary.totalCents)}
                </span>
              </h3>
              <ul className="flex flex-col gap-2">
                {entry.summary.members.map((bubble) => (
                  <li key={bubble.bubble_id}>
                    <Row bubble={bubble} onOpen={onOpen} />
                  </li>
                ))}
              </ul>
            </section>
          </li>
        ),
      )}
    </ul>
  );
}
