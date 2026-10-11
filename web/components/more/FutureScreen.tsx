"use client";

import { useEffect, useId, useState } from "react";
import { api, type FutureResponse } from "@/lib/api";
import { formatCents } from "@/lib/money";
import { PageShell } from "./PageShell";

const DISCLAIMER = "Hypothetical, not investment advice";
const RATE_KEYS = ["low", "mid", "high"] as const;
const RATE_NAMES = { low: "Low", mid: "Middle", high: "High" } as const;

/** Whole dollars from a text field to cents; null when it isn't a plain non-negative number. */
function dollarsToCents(text: string): number | null {
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(text.trim())) return null;
  const [d, c = ""] = text.trim().split(".");
  return Number(d) * 100 + Number(c.padEnd(2, "0"));
}

/** Integer cents to an input value like "250.00" (integer math only). */
function centsToDollars(cents: number): string {
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;
}

/** Hypothetical 10-year range. Every figure sits next to the disclaimer; the assumptions are editable. */
function Future() {
  const uid = useId();
  const [data, setData] = useState<FutureResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [monthly, setMonthly] = useState("");
  const [rates, setRates] = useState({ low: "3", mid: "6", high: "8" });
  const [problem, setProblem] = useState<string | null>(null);

  async function load(next?: Parameters<typeof api.getFuture>[0]) {
    try {
      const res = await api.getFuture(next);
      setData(res);
      setFailed(false);
      setMonthly((m) => (m === "" ? centsToDollars(res.monthly_surplus_cents) : m));
    } catch {
      setFailed(true);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, []);

  function apply(e: React.FormEvent) {
    e.preventDefault();
    const cents = dollarsToCents(monthly);
    const r = { low: Number(rates.low), mid: Number(rates.mid), high: Number(rates.high) };
    if (cents === null) return setProblem("Enter the monthly amount as dollars, like 250.00.");
    if (![r.low, r.mid, r.high].every((x) => Number.isFinite(x) && x >= 0 && x <= 15))
      return setProblem("Return rates must be between 0% and 15%.");
    if (!(r.low <= r.mid && r.mid <= r.high)) return setProblem("Rates must run from low to high.");
    setProblem(null);
    void load({
      monthly_cents: cents,
      rates: { low: r.low / 100, mid: r.mid / 100, high: r.high / 100 },
    });
  }

  if (failed && !data)
    return (
      <p role="alert" className="glass mt-4 rounded-3xl p-6 font-semibold">
        Couldn&rsquo;t load the projection.
      </p>
    );
  if (!data) return <p role="status">Loading…</p>;
  const last = data.series.at(-1);
  if (!last) return null;

  return (
    <>
      <section aria-labelledby={`${uid}-h`} className="glass mt-4 rounded-[1.75rem] p-5 sm:p-6">
        <p className="inline-block rounded-full bg-navy-900 px-3 py-1 text-sm font-bold text-white">
          {DISCLAIMER}
        </p>
        <h2 id={`${uid}-h`} className="mt-3 text-xl font-bold text-navy-950">
          Saving {formatCents(data.monthly_surplus_cents)} a month for {data.years} years could grow
          to
        </h2>
        <p className="mt-1 text-3xl font-extrabold text-navy-950">
          {formatCents(last.low_cents)} to {formatCents(last.high_cents)}
        </p>
        <p className="text-navy-800">Middle estimate: {formatCents(last.mid_cents)}.</p>
        <p className="mt-2 max-w-prose text-sm text-navy-800">
          {data.from_history
            ? "Based on your steady monthly surplus over the last three months."
            : "Based on the monthly amount you entered."}{" "}
          {data.note}
        </p>

        <form onSubmit={apply} className="mt-4 grid gap-3 sm:grid-cols-4" aria-label="Assumptions">
          <label className="flex flex-col gap-1 font-semibold text-navy-950">
            Monthly amount ($)
            <input
              value={monthly}
              onChange={(e) => setMonthly(e.target.value)}
              inputMode="decimal"
              className="min-h-11 rounded-xl border border-navy-900/40 bg-white px-3 text-navy-950"
            />
          </label>
          {RATE_KEYS.map((k) => (
            <label key={k} className="flex flex-col gap-1 font-semibold text-navy-950">
              {RATE_NAMES[k]} yearly return (%)
              <input
                value={rates[k]}
                onChange={(e) => setRates({ ...rates, [k]: e.target.value })}
                inputMode="decimal"
                className="min-h-11 rounded-xl border border-navy-900/40 bg-white px-3 text-navy-950"
              />
            </label>
          ))}
          <div className="sm:col-span-4">
            <button
              type="submit"
              className="inline-flex min-h-11 items-center rounded-full bg-navy-900 px-5 font-semibold text-white hover:bg-navy-800"
            >
              Update the range
            </button>
            {problem ? (
              <p role="alert" className="mt-2 font-semibold text-navy-950">
                {problem}
              </p>
            ) : null}
          </div>
        </form>
      </section>

      <section aria-labelledby={`${uid}-t`} className="glass mt-4 rounded-[1.75rem] p-5 sm:p-6">
        <h2 id={`${uid}-t`} className="text-xl font-bold text-navy-950">
          Year by year ({DISCLAIMER.toLowerCase()})
        </h2>
        {/* A scrollable region must take keyboard focus so it can be scrolled without a mouse. */}
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
        <div
          className="mt-3 overflow-x-auto"
          role="region"
          aria-label="Projection table"
          tabIndex={0}
        >
          <table className="w-full min-w-[28rem] text-left text-navy-950">
            <caption className="sr-only">
              Projected balance by year for low, middle and high returns
            </caption>
            <thead>
              <tr className="border-b border-navy-900/30">
                <th scope="col" className="py-2 pr-3">
                  Year
                </th>
                <th scope="col" className="py-2 pr-3">
                  Low ({Math.round(data.assumptions.low * 1000) / 10}%)
                </th>
                <th scope="col" className="py-2 pr-3">
                  Middle ({Math.round(data.assumptions.mid * 1000) / 10}%)
                </th>
                <th scope="col" className="py-2">
                  High ({Math.round(data.assumptions.high * 1000) / 10}%)
                </th>
              </tr>
            </thead>
            <tbody>
              {data.series.map((row) => (
                <tr key={row.year} className="border-b border-navy-900/10">
                  <th scope="row" className="py-2 pr-3 font-semibold">
                    {row.year}
                  </th>
                  <td className="py-2 pr-3 tabular-nums">{formatCents(row.low_cents)}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatCents(row.mid_cents)}</td>
                  <td className="py-2 tabular-nums">{formatCents(row.high_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export function FutureScreen() {
  return (
    <PageShell
      title="Future view"
      intro="A look at what a steady surplus could grow to. An educational range, not a forecast."
    >
      {() => <Future />}
    </PageShell>
  );
}
