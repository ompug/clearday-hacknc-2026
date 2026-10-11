"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { api, realtime, type ForecastResponse } from "@/lib/api";
import { dueDayName, dueLabel } from "@/lib/dates";
import { formatCents } from "@/lib/money";
import { ForecastChart } from "../forecast/ForecastChart";
import { cushionRisk } from "../forecast/format";
import { StormIcon, SunIcon } from "../icons";
import { StateBadge } from "../StateBadge";

/** Forecast tab: the tight-week card first (what to act on), then the 30-day chart and bills. */
export function MobileForecast() {
  const uid = useId();
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setForecast(await api.getForecast());
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    void refresh();
    return realtime.on("forecast.updated", () => void refresh());
  }, [refresh]);

  if (failed)
    return (
      <p role="alert" className="glass rounded-3xl p-5 font-semibold">
        Couldn&rsquo;t load your forecast.
      </p>
    );
  if (!forecast)
    return (
      <p role="status" className="glass rounded-full px-5 py-3 font-semibold">
        Loading your forecast…
      </p>
    );

  const tight = forecast.bills.filter((b) => b.weather === "tight");
  const first = tight[0];

  return (
    <div className="flex flex-col gap-4">
      <section
        aria-labelledby={`${uid}-tight`}
        className={`glass rounded-[1.75rem] p-5 ${first ? "m-tight-card" : ""}`}
      >
        <h2 id={`${uid}-tight`} className="flex items-center gap-2 text-xl font-bold text-navy-950">
          {first ? (
            <StormIcon aria-hidden="true" className="size-7 text-alert-700" />
          ) : (
            <SunIcon aria-hidden="true" className="size-7 text-navy-900" />
          )}
          {first ? "A tight week ahead" : "No tight weeks ahead"}
        </h2>
        <p className="mt-2 text-navy-900">
          {first
            ? `${first.label} (${dueLabel(first.date).toLowerCase()}) could leave you short. ${cushionRisk(first.p_short)} of ${formatCents(forecast.threshold_cents)}.`
            : "Every bill in the next 30 days looks covered, even on a rough week."}
        </p>
        <p className="mt-3 font-semibold text-navy-800">
          Likely safe to spend
          {forecast.next_payday ? ` until payday (${dueDayName(forecast.next_payday)})` : ""}
        </p>
        <p className="text-4xl font-extrabold tracking-tight text-navy-950 tabular-nums">
          {formatCents(forecast.safe_to_spend_cents)}
        </p>
        {forecast.wants_trimmed.safe_to_spend_cents > forecast.safe_to_spend_cents ? (
          <p className="mt-1 text-sm text-navy-800">
            Trim wants by a quarter for{" "}
            {formatCents(forecast.wants_trimmed.safe_to_spend_cents - forecast.safe_to_spend_cents)}{" "}
            more room.
          </p>
        ) : null}
      </section>

      <section aria-labelledby={`${uid}-chart`} className="glass rounded-[1.75rem] p-4">
        <h2 id={`${uid}-chart`} className="px-1 text-lg font-bold text-navy-950">
          Checking balance, next 30 days
        </h2>
        <p id={`${uid}-desc`} className="mt-1 px-1 text-sm text-navy-800">
          Line: most likely. Band: 8 in 10 outcomes. Red line: your cushion.
        </p>
        <div className="mt-2 -mx-1">
          <ForecastChart
            days={forecast.days}
            bills={forecast.bills}
            thresholdCents={forecast.threshold_cents}
            describedBy={`${uid}-desc`}
          />
        </div>
      </section>

      <section aria-labelledby={`${uid}-bills`} className="glass rounded-[1.75rem] p-4">
        <h2 id={`${uid}-bills`} className="px-1 text-lg font-bold text-navy-950">
          Bills ahead
        </h2>
        <ul className="mt-2 flex flex-col gap-2">
          {forecast.bills.map((b) => (
            <li
              key={`${b.label}-${b.date}`}
              className="flex items-start justify-between gap-3 rounded-2xl border border-white bg-white/85 px-4 py-3"
            >
              <span className="min-w-0">
                <span className="block font-bold break-words text-navy-950">{b.label}</span>
                <span className="block text-sm text-navy-800">{dueLabel(b.date)}</span>
              </span>
              <span className="flex shrink-0 flex-col items-end gap-1">
                <span className="font-bold text-navy-950 tabular-nums">
                  {formatCents(b.amount_cents)}
                </span>
                <StateBadge state={b.weather} small />
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
