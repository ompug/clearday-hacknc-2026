"use client";

import { useCallback, useEffect, useState } from "react";
import { api, realtime, type FeedEvent } from "@/lib/api";
import { AeroWindow } from "../aero";
import { CheckIcon, PeopleIcon, PlusIcon } from "../icons";

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

/** Household celebrations, no amounts. Icon plus text for each event. */
export function MobileFeed() {
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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    void refresh();
    return realtime.on("feed.created", () => void refresh());
  }, [refresh]);

  if (failed)
    return (
      <p role="alert" className="glass rounded-3xl p-5 font-semibold">
        Couldn&rsquo;t load the feed.
      </p>
    );
  if (!events)
    return (
      <p role="status" className="glass rounded-full px-5 py-3 font-semibold">
        Loading the feed…
      </p>
    );

  return (
    <AeroWindow
      title="Household activity"
      icon={<PeopleIcon className="size-5" />}
      controls={false}
      bodyClassName="p-4"
    >
      {events.length === 0 ? (
        <p className="px-1 text-navy-800">
          Nothing yet. Pay a share or add an expense to start it off.
        </p>
      ) : (
        <ul className="flex flex-col gap-2" aria-live="polite">
          {events.map((e, i) => {
            const Icon = e.type === "expense_created" ? PlusIcon : CheckIcon;
            return (
              <li
                key={`${e.created_at}-${i}`}
                className="flex items-start gap-3 rounded-2xl border border-white bg-white/85 px-4 py-3"
              >
                <span
                  aria-hidden="true"
                  className="bubble grid size-10 shrink-0 place-items-center"
                  data-state="clear"
                >
                  <Icon className="bubble-content size-5 text-navy-900" />
                </span>
                <div className="min-w-0">
                  <p className="font-semibold break-words text-navy-950">{TEXT[e.type](e)}</p>
                  <p className="text-sm text-navy-800">{when(e.created_at)}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-3 px-1 text-sm text-navy-800">
        Only your household sees this, and it never shows amounts.
      </p>
    </AeroWindow>
  );
}
