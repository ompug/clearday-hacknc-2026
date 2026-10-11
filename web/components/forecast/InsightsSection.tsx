"use client";

import { useEffect, useId, useState } from "react";
import { api, type BacktestSummary, type DuplicateSubscription } from "@/lib/api";
import { formatCents } from "@/lib/money";

function joinNames(names: string[]): string {
  if (names.length <= 2) return names.join(" and ");
  return `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
}

/** Duplicate household subscriptions and the forecast's honest track record. */
export function InsightsSection() {
  const uid = useId();
  const [duplicates, setDuplicates] = useState<DuplicateSubscription[] | null>(null);
  const [backtest, setBacktest] = useState<BacktestSummary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getDuplicateSubscriptions(), api.getBacktest()])
      .then(([d, b]) => {
        if (cancelled) return;
        setDuplicates(d.duplicates);
        setBacktest(b);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) return null;
  if (!duplicates || !backtest) return null;

  return (
    <div className="mt-6 grid items-start gap-6 lg:grid-cols-2">
      <section aria-labelledby={`${uid}-subs`} className="glass rounded-[1.75rem] p-5 sm:p-6">
        <h2 id={`${uid}-subs`} className="text-xl font-bold text-navy-950">
          Subscriptions you may be doubling up on
        </h2>
        {duplicates.length === 0 ? (
          <p className="mt-2 text-navy-800">No one in your household pays for the same service.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {duplicates.map((d) => (
              <li
                key={d.merchant}
                className="rounded-2xl border border-white bg-white/85 px-4 py-3 shadow-sm"
              >
                <p className="font-bold break-words text-navy-950">{d.merchant}</p>
                <p className="text-sm text-navy-800">
                  {joinNames(d.members.map((m) => m.display_name))} each pay for it, together{" "}
                  {formatCents(d.monthly_cost_cents)} a month. Sharing one plan could free up{" "}
                  <strong>{formatCents(d.possible_savings_cents)}</strong> a month.
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby={`${uid}-bt`} className="glass rounded-[1.75rem] p-5 sm:p-6">
        <h2 id={`${uid}-bt`} className="text-xl font-bold text-navy-950">
          How the forecast has done
        </h2>
        <p className="mt-2 text-3xl font-extrabold text-navy-950">
          {Math.round(backtest.coverage * 100)}%
        </p>
        <p className="text-navy-800">
          of the last {backtest.holdout_days} days landed inside the likely range, with a typical
          miss of {formatCents(backtest.median_abs_error_cents)}.
        </p>
        {backtest.is_preview ? (
          <p className="mt-2 rounded-xl bg-white/70 px-3 py-2 text-sm font-semibold text-navy-900 ring-1 ring-navy-900/10">
            Preview number: the real backtest isn&rsquo;t connected yet, so this is a placeholder,
            not a measured result.
          </p>
        ) : null}
      </section>
    </div>
  );
}
