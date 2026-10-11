"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  realtime,
  type Account,
  type AnnouncementResponse,
  type PaymentResult,
  type SkyBubble,
  type SkyResponse,
} from "@/lib/api";
import { bubbleAccessibleName, bubbleState, progressLabel, STATE_LABELS } from "@/lib/bubbles";
import { dueDayName, dueLabel } from "@/lib/dates";
import { formatCents } from "@/lib/money";
import { AeroBubble, aeroButtonClass } from "../aero";
import { CloudSunIcon } from "../icons";
import { PayDialog } from "../sky/PayDialog";
import { VoiceAnnouncement } from "../sky/VoiceAnnouncement";
import { StateIcon } from "../StateBadge";
import { useMobileSession } from "./MobileShell";

/** Bigger share, bigger bubble, within thumb-friendly bounds (rem). */
function diameter(cents: number, max: number): number {
  if (max <= 0) return 9;
  return 8 + 2.5 * Math.sqrt(cents / max);
}

export function MobileSky() {
  const { announce } = useMobileSession();
  const [sky, setSky] = useState<SkyResponse | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<SkyBubble | null>(null);
  const [voice, setVoice] = useState<AnnouncementResponse | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextSky, nextAccounts] = await Promise.all([api.getSky(), api.getAccounts()]);
      setSky(nextSky);
      setAccounts(nextAccounts.accounts);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    void refresh();
    const offs = [
      realtime.on("share.updated", () => void refresh()),
      realtime.on("bubble.popped", (event) => {
        announce(`${event.label} is fully covered. Bubble popped for the household.`);
        void refresh();
        api
          .getAnnouncement()
          .then(setVoice)
          .catch(() => undefined);
      }),
      realtime.on("feed.created", (event) => {
        if (event.type === "expense_created")
          announce(`${event.actor_display_name} added ${event.subject_label}.`);
        void refresh();
      }),
      realtime.on("forecast.updated", () => void refresh()),
    ];
    return () => offs.forEach((off) => off());
  }, [refresh, announce]);

  function handlePaid(bubble: SkyBubble, result: PaymentResult) {
    setOpen(null);
    if (result.popped) {
      announce(`${bubble.label} paid. Bubble popped!`);
      requestAnimationFrame(() => headingRef.current?.focus());
    } else {
      announce(
        `Your share of ${bubble.label} is paid. ${result.paid_count} of ${bubble.participant_count} roommates paid.`,
      );
    }
    void refresh();
  }

  if (failed)
    return (
      <p role="alert" className="glass rounded-3xl p-5 font-semibold">
        Couldn&rsquo;t load your sky. Pull down or reload.
      </p>
    );
  if (!sky)
    return (
      <p role="status" className="glass rounded-full px-5 py-3 font-semibold">
        Loading your sky…
      </p>
    );

  const bubbles = [...sky.bubbles].sort((a, b) => a.due_date.localeCompare(b.due_date));
  const max = Math.max(0, ...bubbles.map((b) => b.your_share_cents));

  return (
    <div className="flex flex-col gap-4">
      <section aria-labelledby="m-safe" className="glass rounded-[1.75rem] p-5">
        <h2 id="m-safe" className="font-semibold text-navy-800">
          Likely safe to spend until payday ({dueDayName(sky.next_payday)})
        </h2>
        <p className="text-4xl font-extrabold tracking-tight text-navy-950 tabular-nums">
          {formatCents(sky.safe_to_spend_cents)}
        </p>
        <ul aria-label="Your accounts" className="mt-3 flex gap-2 overflow-x-auto pb-1">
          {accounts.map((a) => (
            <li
              key={a.account_id}
              className="shrink-0 rounded-2xl border border-white bg-white/85 px-3 py-2 shadow-sm"
            >
              <span className="block text-sm font-semibold text-navy-800">
                {a.nickname} ••{a.last4}
              </span>
              <span className="block font-bold text-navy-950 tabular-nums">
                {formatCents(a.balance_cents)}
              </span>
            </li>
          ))}
        </ul>
        <Link
          href="/m/forecast"
          className={aeroButtonClass("secondary", "m-press mt-3 inline-flex items-center gap-2")}
        >
          <CloudSunIcon aria-hidden="true" className="size-5" />
          See your forecast
        </Link>
      </section>

      {voice ? <VoiceAnnouncement announcement={voice} onDismiss={() => setVoice(null)} /> : null}

      <section aria-labelledby="m-bills">
        <h2
          id="m-bills"
          ref={headingRef}
          tabIndex={-1}
          className="glass-navy w-fit rounded-full px-5 py-2 text-lg font-bold"
        >
          Upcoming bills · tap to pay
        </h2>
        {bubbles.length === 0 ? (
          <p className="glass mt-4 rounded-3xl p-5 font-semibold">
            Clear skies. Nothing due right now.
          </p>
        ) : (
          <ul className="mt-4 grid grid-cols-2 gap-x-3 gap-y-5">
            {bubbles.map((b, i) => {
              const state = bubbleState(b);
              const d = diameter(b.your_share_cents, max);
              const progress = progressLabel(b);
              return (
                <li
                  key={b.bubble_id}
                  className={`flex flex-col items-center gap-2 ${i % 2 === 1 ? "mt-6" : ""}`}
                >
                  <AeroBubble
                    state={state}
                    fill={b.kind === "shared" && b.fill_fraction > 0 ? b.fill_fraction : undefined}
                    size={`${d}rem`}
                    aria-label={bubbleAccessibleName(b)}
                    onClick={() => setOpen(b)}
                    className="m-press m-bubble shrink-0 !p-0"
                  >
                    <span className="flex h-full flex-col items-center justify-center px-[12%] text-center">
                      <StateIcon
                        state={state}
                        className={`size-6 ${state === "tight" ? "text-alert-700" : "text-navy-800"}`}
                      />
                      <span className="line-clamp-2 leading-tight font-bold break-words">
                        {b.label}
                      </span>
                      <span className="text-lg font-extrabold tabular-nums">
                        {formatCents(b.your_share_cents)}
                      </span>
                    </span>
                  </AeroBubble>
                  <span className="glass flex max-w-full flex-col items-center rounded-2xl px-3 py-1 text-center text-sm font-semibold text-navy-900">
                    <span className="flex items-center gap-1">
                      <StateIcon
                        state={state}
                        className={`size-4 ${state === "tight" ? "text-alert-700" : ""}`}
                      />
                      {STATE_LABELS[state]}
                    </span>
                    <span className="text-navy-800">
                      {dueLabel(b.due_date)}
                      {progress ? ` · ${progress}` : ""}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <PayDialog
        bubble={open}
        accounts={accounts}
        onClose={() => setOpen(null)}
        onPaid={handlePaid}
      />
    </div>
  );
}
