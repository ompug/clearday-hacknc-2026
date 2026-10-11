"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";
import { api, realtime, type ForecastResponse, type Me } from "@/lib/api";
import { dueDayName, dueLabel } from "@/lib/dates";
import { formatCents } from "@/lib/money";
import { AppHeader } from "../AppHeader";
import { ArrowLeftIcon } from "../icons";
import { StateBadge } from "../StateBadge";
import { ForecastChart } from "./ForecastChart";
import { categoryLabel, cushionRisk, formatLongDate } from "./format";

export function ForecastScreen() {
  const router = useRouter();
  const uid = useId();
  const [me, setMe] = useState<Me | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [trimWants, setTrimWants] = useState(false);

  const refresh = useCallback(async () => {
    setForecast(await api.getForecast());
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

  useEffect(() => realtime.on("forecast.updated", () => void refresh()), [refresh]);

  async function signOut() {
    await api.logout();
    router.push("/login");
  }

  const safe = forecast
    ? trimWants
      ? forecast.wants_trimmed.safe_to_spend_cents
      : forecast.safe_to_spend_cents
    : 0;
  const gain = forecast
    ? forecast.wants_trimmed.safe_to_spend_cents - forecast.safe_to_spend_cents
    : 0;
  const bills = forecast
    ? forecast.bills.map((bill, i) => {
        const trimmed = forecast.wants_trimmed.bills[i];
        return trimWants && trimmed
          ? { ...bill, p_short: trimmed.p_short, weather: trimmed.weather }
          : bill;
      })
    : [];
  const tightCount = bills.filter((b) => b.weather === "tight").length;

  return (
    <>
      <AppHeader me={me} onSignOut={() => void signOut()} />
      <main id="main" className="mx-auto w-full max-w-6xl px-4 pt-6 pb-16">
        <Link
          href="/sky"
          className="glass inline-flex min-h-11 items-center gap-2 rounded-full px-4 font-semibold text-navy-900"
        >
          <ArrowLeftIcon className="size-5" />
          Back to your bills
        </Link>

        {loadError ? (
          <p role="alert" className="glass mt-4 rounded-3xl p-6 text-lg font-semibold">
            Couldn&rsquo;t load your forecast. Check your connection and reload.
          </p>
        ) : null}

        <section
          aria-labelledby={`${uid}-title`}
          className="glass mt-4 rounded-[1.75rem] p-5 sm:p-6"
        >
          <h1 id={`${uid}-title`} className="text-2xl font-bold text-navy-950 sm:text-3xl">
            Your money weather, next 30 days
          </h1>
          {forecast ? (
            <div className="mt-4 flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
              <div aria-live="polite">
                <p className="font-semibold text-navy-800">
                  Likely safe to spend
                  {forecast.next_payday
                    ? ` until payday (${dueDayName(forecast.next_payday)})`
                    : " this month"}
                </p>
                <p className="text-5xl font-extrabold tracking-tight text-navy-950">
                  {formatCents(safe)}
                </p>
                <p className="mt-1 max-w-prose text-sm text-navy-800">
                  {trimWants
                    ? gain > 0
                      ? `${formatCents(gain)} more room than now, if wants like dining out and rideshares drop by a quarter.`
                      : "Trimming wants doesn't add room before payday this time."
                    : `Even on a rough week, after bills and a ${formatCents(forecast.threshold_cents)} cushion.`}
                </p>
              </div>
              <WantsToggle checked={trimWants} onChange={setTrimWants} gain={gain} />
            </div>
          ) : !loadError ? (
            <p role="status" className="mt-4 font-semibold">
              Loading your forecast…
            </p>
          ) : null}
        </section>

        {forecast ? (
          <>
            <section
              aria-labelledby={`${uid}-chart`}
              className="glass mt-6 rounded-[1.75rem] p-5 sm:p-6"
            >
              <h2 id={`${uid}-chart`} className="text-xl font-bold text-navy-950">
                Your checking balance, day by day
              </h2>
              <p id={`${uid}-chart-desc`} className="mt-1 max-w-prose text-navy-800">
                {summarize(forecast)}
              </p>
              <ul
                aria-label="Chart key"
                className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm font-semibold text-navy-900"
              >
                <li className="flex items-center gap-2">
                  <span aria-hidden="true" className="h-0.5 w-5 rounded bg-sky-600" />
                  Most likely
                </li>
                <li className="flex items-center gap-2">
                  <span aria-hidden="true" className="h-3 w-5 rounded-sm bg-sky-500/30" />
                  Likely range (8 in 10 outcomes)
                </li>
                <li className="flex items-center gap-2">
                  <span aria-hidden="true" className="h-px w-5 bg-alert-600" />
                  Your cushion
                </li>
                <li className="flex items-center gap-2">
                  <span aria-hidden="true" className="size-2.5 rounded-full bg-sky-600" />
                  Bill due
                </li>
              </ul>
              {trimWants ? (
                <p className="mt-2 text-sm text-navy-800">
                  The chart shows your current path; the trimmed-wants numbers are above and in the
                  bills list.
                </p>
              ) : null}
              <div className="mt-3">
                <ForecastChart
                  days={forecast.days}
                  bills={forecast.bills}
                  thresholdCents={forecast.threshold_cents}
                  describedBy={`${uid}-chart-desc`}
                />
              </div>
              <ForecastTable forecast={forecast} />
            </section>

            <div className="mt-6 grid items-start gap-6 lg:grid-cols-[3fr_2fr]">
              <section
                aria-labelledby={`${uid}-bills`}
                className="glass rounded-[1.75rem] p-5 sm:p-6"
              >
                <h2 id={`${uid}-bills`} className="text-xl font-bold text-navy-950">
                  Bills ahead
                </h2>
                <p className="mt-1 text-navy-800">
                  {tightCount === 0
                    ? "No bill looks likely to leave you short."
                    : `${tightCount} ${tightCount === 1 ? "bill looks" : "bills look"} likely to leave you short.`}
                </p>
                <ul className="mt-3 flex flex-col gap-2">
                  {bills.map((b) => (
                    <li
                      key={`${b.label}-${b.date}`}
                      className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 rounded-2xl border border-white bg-white/85 px-4 py-3 shadow-sm"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block font-bold break-words text-navy-950">{b.label}</span>
                        <span className="block text-sm text-navy-800">
                          {dueLabel(b.date)} · {cushionRisk(b.p_short)}
                        </span>
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

              <section
                aria-labelledby={`${uid}-drivers`}
                className="glass rounded-[1.75rem] p-5 sm:p-6"
              >
                <h2 id={`${uid}-drivers`} className="text-xl font-bold text-navy-950">
                  What moves your forecast most
                </h2>
                <p className="mt-1 text-navy-800">
                  Spending that swings the most from week to week.
                </p>
                <ul className="mt-4 flex flex-col gap-4">
                  {forecast.drivers.map((d) => {
                    const pct = Math.round(d.share_of_variance * 100);
                    return (
                      <li key={d.category}>
                        <p className="flex justify-between gap-3 font-semibold text-navy-950">
                          <span>{categoryLabel(d.category)}</span>
                          <span className="tabular-nums">{pct}% of the swing</span>
                        </p>
                        <div
                          aria-hidden="true"
                          className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-sky-100 ring-1 ring-navy-900/10"
                        >
                          <div
                            className="h-full rounded-full bg-sky-600"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            </div>
          </>
        ) : null}
      </main>
    </>
  );
}

/** One plain-language sentence for the chart: where it bottoms out and whether that's tight. */
function summarize(forecast: ForecastResponse): string {
  if (forecast.days.length === 0) return "No forecast yet.";
  const lowest = forecast.days.reduce((a, b) => (b.p10_cents < a.p10_cents ? b : a));
  const end = forecast.days[forecast.days.length - 1]!;
  const dip =
    lowest.p10_cents < forecast.threshold_cents
      ? `On a rough week you could dip below your ${formatCents(forecast.threshold_cents)} cushion around ${formatLongDate(lowest.date)}.`
      : `Even on a rough week you likely stay above your ${formatCents(forecast.threshold_cents)} cushion.`;
  return `${dip} Most likely you end the month near ${formatCents(end.p50_cents)}.`;
}

function WantsToggle({
  checked,
  onChange,
  gain,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  gain: number;
}) {
  const id = useId();
  return (
    <div className="flex max-w-sm items-start gap-4 rounded-2xl border border-white bg-white/85 p-4 shadow-sm">
      <div className="min-w-0">
        <p id={`${id}-label`} className="font-semibold text-navy-950">
          Trim wants by 25%
        </p>
        <p id={`${id}-desc`} className="text-sm text-navy-800">
          See your month if dining out, rideshares and shopping drop by a quarter
          {gain > 0 ? ` (+${formatCents(gain)})` : ""}.
        </p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-desc`}
        onClick={() => onChange(!checked)}
        className={`relative mt-1 inline-flex h-8 w-14 shrink-0 items-center rounded-full border-2 border-navy-900 transition-colors ${
          checked ? "bg-navy-900" : "bg-white"
        }`}
      >
        <span
          aria-hidden="true"
          className={`inline-block size-5 rounded-full transition-transform ${
            checked ? "translate-x-7 bg-white" : "translate-x-1 bg-navy-900"
          }`}
        />
        <span className="sr-only">{checked ? "On" : "Off"}</span>
      </button>
    </div>
  );
}

/** The chart's accessible twin: every day's numbers, behind a disclosure. */
function ForecastTable({ forecast }: { forecast: ForecastResponse }) {
  return (
    <details className="mt-4 rounded-2xl bg-white/70 ring-1 ring-navy-900/10">
      <summary className="min-h-11 cursor-pointer rounded-2xl px-4 py-2.5 font-semibold text-navy-900">
        Show the numbers as a table
      </summary>
      <div className="max-h-96 overflow-auto px-2 pb-2">
        <table className="w-full border-collapse text-left text-sm text-navy-950">
          <caption className="sr-only">Checking balance forecast by day</caption>
          <thead className="sticky top-0 bg-white">
            <tr>
              <th scope="col" className="px-2 py-2">
                Day
              </th>
              <th scope="col" className="px-2 py-2 text-right">
                Rough week
              </th>
              <th scope="col" className="px-2 py-2 text-right">
                Most likely
              </th>
              <th scope="col" className="px-2 py-2 text-right">
                Good week
              </th>
              <th scope="col" className="px-2 py-2">
                Bills
              </th>
            </tr>
          </thead>
          <tbody>
            {forecast.days.map((d) => (
              <tr key={d.date} className="border-t border-navy-900/10">
                <th scope="row" className="px-2 py-1.5 font-semibold whitespace-nowrap">
                  {formatLongDate(d.date)}
                </th>
                <td className="px-2 py-1.5 text-right tabular-nums">{formatCents(d.p10_cents)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{formatCents(d.p50_cents)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{formatCents(d.p90_cents)}</td>
                <td className="px-2 py-1.5">
                  {forecast.bills
                    .filter((b) => b.date === d.date)
                    .map((b) => b.label)
                    .join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
