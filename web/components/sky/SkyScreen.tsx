"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  realtime,
  type Account,
  type Me,
  type PaymentResult,
  type SkyBubble,
  type SkyResponse,
} from "@/lib/api";
import { skyEntries, STATE_LABELS, type BubbleState } from "@/lib/bubbles";
import { dueDayName } from "@/lib/dates";
import { formatCents } from "@/lib/money";
import { usePreferences, type ViewMode } from "@/lib/preferences";
import { AppHeader } from "../AppHeader";
import { BubblesIcon, ListIcon } from "../icons";
import { StateIcon } from "../StateBadge";
import { ListView } from "./ListView";
import { PayDialog } from "./PayDialog";
import { SkyView } from "./SkyView";

const LEGEND: BubbleState[] = ["clear", "watch", "tight", "waiting"];

const ACCOUNT_TYPE_SHORT: Record<Account["type"], string> = {
  checking: "Checking",
  savings: "Savings",
  credit_card: "Card owed",
};

export function SkyScreen() {
  const router = useRouter();
  const { view, setView } = usePreferences();
  const [me, setMe] = useState<Me | null>(null);
  const [sky, setSky] = useState<SkyResponse | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [openBubble, setOpenBubble] = useState<SkyBubble | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);

  const refresh = useCallback(async () => {
    const [nextSky, nextAccounts] = await Promise.all([api.getSky(), api.getAccounts()]);
    setSky(nextSky);
    setAccounts(nextAccounts.accounts);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then(async (session) => {
        if (cancelled) return;
        if (!session) {
          router.replace("/login");
          return;
        }
        setMe(session);
        await refresh();
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [refresh, router]);

  // Live updates from roommates (Socket.IO in production, an in-memory bus in mock mode).
  useEffect(() => {
    const offShare = realtime.on("share.updated", () => void refresh());
    const offPop = realtime.on("bubble.popped", (event) => {
      setAnnouncement(`${event.label} is fully covered. Bubble popped for the household.`);
      void refresh();
    });
    return () => {
      offShare();
      offPop();
    };
  }, [refresh]);

  useEffect(() => {
    if (!announcement) return;
    const timer = setTimeout(() => setAnnouncement(""), 5000);
    return () => clearTimeout(timer);
  }, [announcement]);

  const entries = useMemo(() => (sky ? skyEntries(sky.bubbles, sky.clusters) : []), [sky]);

  function handlePaid(bubble: SkyBubble, result: PaymentResult) {
    setOpenBubble(null);
    if (result.popped) {
      setAnnouncement(`${bubble.label} paid. Bubble popped!`);
      // The bubble (and the button that opened the dialog) is going away.
      requestAnimationFrame(() => headingRef.current?.focus());
    } else {
      setAnnouncement(
        `Your share of ${bubble.label} is paid. ${result.paid_count} of ${bubble.participant_count} roommates paid.`,
      );
    }
    void refresh();
  }

  async function signOut() {
    await api.logout();
    router.push("/login");
  }

  return (
    <>
      <AppHeader me={me} onSignOut={() => void signOut()} />
      <main id="main" className="mx-auto w-full max-w-6xl px-4 pt-6 pb-16">
        {loadError ? (
          <p role="alert" className="glass rounded-3xl p-6 text-lg font-semibold">
            Couldn&rsquo;t load your sky. Check your connection and reload.
          </p>
        ) : null}

        <section aria-labelledby="summary-heading" className="glass rounded-[1.75rem] p-5 sm:p-6">
          <h1 id="summary-heading" className="sr-only">
            {me ? `${me.user.display_name}'s bills` : "Your bills"}
          </h1>
          {sky ? (
            <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
              <div>
                <p className="font-semibold text-navy-800">
                  Likely safe to spend until payday ({dueDayName(sky.next_payday)})
                </p>
                <p className="text-4xl font-extrabold tracking-tight text-navy-950 tabular-nums">
                  {formatCents(sky.safe_to_spend_cents)}
                </p>
                <p className="mt-1 max-w-prose text-sm text-navy-800">
                  After your bills and your share of the household&rsquo;s, with a cushion for a
                  rough week.
                </p>
              </div>
              <ul aria-label="Your accounts" className="flex flex-wrap gap-2">
                {accounts.map((a) => (
                  <li
                    key={a.account_id}
                    className="rounded-2xl border border-white bg-white/80 px-3 py-2 shadow-sm"
                  >
                    <span className="block text-sm font-semibold text-navy-800">
                      {a.nickname} ••{a.last4}
                    </span>
                    <span className="block font-bold text-navy-950 tabular-nums">
                      <span className="sr-only">{ACCOUNT_TYPE_SHORT[a.type]} balance </span>
                      <span aria-hidden="true" className="text-sm font-semibold text-navy-800">
                        {ACCOUNT_TYPE_SHORT[a.type]}{" "}
                      </span>
                      {formatCents(a.balance_cents)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p role="status" className="font-semibold">
              Loading your sky…
            </p>
          )}
        </section>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="glass-navy rounded-full px-5 py-2 text-xl font-bold"
          >
            Upcoming bills
          </h2>
          <ViewToggle view={view} onChange={setView} />
        </div>

        <ul
          aria-label="What the bubble colours mean"
          className="glass mt-4 flex flex-wrap gap-x-5 gap-y-2 rounded-2xl px-4 py-2.5 text-sm font-semibold"
        >
          {LEGEND.map((state) => (
            <li key={state} className="flex items-center gap-1.5">
              <StateIcon
                state={state}
                className={`size-4 ${state === "tight" ? "text-alert-700" : ""}`}
              />
              {STATE_LABELS[state]}
            </li>
          ))}
        </ul>

        <div className="mt-5">
          {sky ? (
            view === "list" ? (
              <ListView entries={entries} onOpen={setOpenBubble} />
            ) : (
              <SkyView entries={entries} onOpen={setOpenBubble} />
            )
          ) : null}
        </div>
      </main>

      <PayDialog
        bubble={openBubble}
        accounts={accounts}
        onClose={() => setOpenBubble(null)}
        onPaid={handlePaid}
      />

      <div
        role="status"
        aria-live="polite"
        className={`fixed inset-x-0 bottom-4 z-50 mx-auto w-fit max-w-[calc(100vw-2rem)] transition-opacity ${
          announcement ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        {announcement ? (
          <p className="glass rounded-full px-5 py-3 text-center font-bold text-navy-950">
            {announcement}
          </p>
        ) : null}
      </div>
    </>
  );
}

function ViewToggle({ view, onChange }: { view: ViewMode; onChange: (v: ViewMode) => void }) {
  const options: { id: ViewMode; label: string; icon: React.ReactNode }[] = [
    { id: "list", label: "List", icon: <ListIcon className="size-5" /> },
    { id: "sky", label: "Sky", icon: <BubblesIcon className="size-5" /> },
  ];
  return (
    <div role="group" aria-label="View" className="glass flex rounded-full p-1">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          aria-pressed={view === o.id}
          onClick={() => onChange(o.id)}
          className={`inline-flex min-h-11 items-center gap-2 rounded-full px-4 font-semibold ${
            view === o.id ? "bg-navy-900 text-white shadow" : "text-navy-900 hover:bg-white"
          }`}
        >
          {o.icon}
          {o.label}
        </button>
      ))}
    </div>
  );
}
