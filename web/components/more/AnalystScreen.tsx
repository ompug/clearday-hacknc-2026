"use client";

import { useEffect, useState } from "react";
import { api, type AnalystSegmentsResponse } from "@/lib/api";
import { PageShell } from "./PageShell";

/** Segment hardship rates over synthetic households. Bars carry a number and a text label. */
function Segments() {
  const [data, setData] = useState<AnalystSegmentsResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api
      .getAnalystSegments()
      .then(setData)
      .catch(() => setFailed(true));
  }, []);

  if (failed)
    return (
      <p role="alert" className="glass mt-4 rounded-3xl p-6 font-semibold">
        Couldn&rsquo;t load the segments.
      </p>
    );
  if (!data) return <p role="status">Loading segments…</p>;

  return (
    <section aria-labelledby="segments-h" className="glass mt-4 rounded-[1.75rem] p-5 sm:p-6">
      <p className="inline-block rounded-full bg-navy-900 px-3 py-1 text-sm font-bold text-white">
        Synthetic households only: {data.total_households} invented households, no real customers
      </p>
      <h2 id="segments-h" className="mt-3 text-xl font-bold text-navy-950">
        Households likely to come up short in the next 30 days
      </h2>
      <ul className="mt-3 flex flex-col gap-3">
        {data.segments.map((s) => {
          const pct = Math.round(s.share_at_risk * 100);
          return (
            <li key={s.segment} className="rounded-2xl border border-white bg-white/85 px-4 py-3">
              <p className="flex flex-wrap justify-between gap-2 font-bold text-navy-950">
                <span>{s.label}</span>
                <span>
                  {pct}% at risk <span className="font-medium">({s.households} households)</span>
                </span>
              </p>
              <div
                role="img"
                aria-label={`${pct} percent of ${s.label} households at risk`}
                className="mt-2 h-4 overflow-hidden rounded-full bg-sky-100 ring-1 ring-navy-900/20"
              >
                <div className="h-full bg-navy-800" style={{ width: `${pct}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 max-w-prose text-sm text-navy-800">
        Segments with fewer than {data.min_segment_size} households are hidden. {data.note}
      </p>
    </section>
  );
}

export function AnalystScreen() {
  return (
    <PageShell
      title="Analyst view"
      intro="What a bank could see, anonymously, to offer help before a customer falls behind."
    >
      {() => <Segments />}
    </PageShell>
  );
}
