"use client";

import { useCallback, useEffect, useState } from "react";
import { api, realtime, type FeedEvent } from "@/lib/api";
import { CheckIcon, PlusIcon } from "../icons";
import { PageShell } from "./PageShell";

const TEXT: Record<FeedEvent["type"], (e: FeedEvent) => string> = {
  share_paid: (e) => `${e.actor_display_name} paid their share of ${e.subject_label}`,
  bubble_popped: (e) => `${e.actor_display_name} cleared ${e.subject_label}`,
  expense_created: (e) => `${e.actor_display_name} added ${e.subject_label}`,
};

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Celebrations without amounts. Icon plus text for each event type. */
function Feed() {
  const [events, setEvents] = useState<FeedEvent[] | null>(null);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setEvents((await api.getFeed()).events);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    return realtime.on("feed.created", () => void refresh());
  }, [refresh]);

  if (failed)
    return (
      <p role="alert" className="glass mt-4 rounded-3xl p-6 font-semibold">
        Couldn&rsquo;t load the feed.
      </p>
    );
  if (!events) return <p role="status">Loading the feed…</p>;

  return (
    <section
      aria-label="Recent household events"
      className="glass mt-4 rounded-[1.75rem] p-5 sm:p-6"
    >
      {events.length === 0 ? (
        <p className="text-navy-800">Nothing yet. Pay a share or add an expense to start it off.</p>
      ) : (
        <ul className="flex flex-col gap-2" aria-live="polite">
          {events.map((e, i) => {
            const Icon = e.type === "expense_created" ? PlusIcon : CheckIcon;
            return (
              <li
                key={`${e.created_at}-${i}`}
                className="flex items-start gap-3 rounded-2xl border border-white bg-white/85 px-4 py-3"
              >
                <Icon aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-navy-900" />
                <div>
                  <p className="font-semibold break-words text-navy-950">{TEXT[e.type](e)}</p>
                  <p className="text-sm text-navy-800">{when(e.created_at)}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-3 text-sm text-navy-800">
        Only your household sees this, and it never shows amounts.
      </p>
    </section>
  );
}

export function FeedScreen() {
  return (
    <PageShell title="Household feed" intro="What your household has been up to.">
      {() => <Feed />}
    </PageShell>
  );
}
