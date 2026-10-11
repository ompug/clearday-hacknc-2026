"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import type { Cents, ForecastBill, ForecastDay, IsoDate } from "@/lib/api";
import { formatCents } from "@/lib/money";
import { cushionRisk, formatAxisDollars, formatLongDate, formatShortDate } from "./format";

/*
 * One series (the checking balance) drawn as a likely-range band (sky wash) around the most-likely
 * line (sky-600, 2px). The cushion is a status reference: a 1px solid red rule with a navy label.
 * Bills sit on the line as 8px dots with a 2px surface ring; a "likely short" bill is red and also
 * says so in the tooltip and the bills list, so colour is never the only signal.
 * Palette validated with the dataviz validator against the glass surface (#f7fbfe).
 */
const LINE = "#1675b0"; // sky-600, 4.9:1 on the glass
const BAND = "#2898d6"; // sky-500 as a wash
const CUSHION = "#c8102e"; // alert-600
const GRID = "#d5e3ee";
const AXIS_TEXT = "#0e3a6b"; // navy-800
const SURFACE = "#f7fbfe";

interface Point {
  date: IsoDate;
  low: Cents;
  mid: Cents;
  high: Cents;
  band: [Cents, Cents];
  bills: ForecastBill[];
  /** `mid` on days with a bill, else null (drives the bill dots). */
  billMid: Cents | null;
}

function toPoints(days: ForecastDay[], bills: ForecastBill[]): Point[] {
  return days.map((d) => {
    const today = bills.filter((b) => b.date === d.date);
    return {
      date: d.date,
      low: d.p10_cents,
      mid: d.p50_cents,
      high: d.p90_cents,
      band: [d.p10_cents, d.p90_cents],
      bills: today,
      billMid: today.length ? d.p50_cents : null,
    };
  });
}

function ChartTooltip({ active, payload }: TooltipContentProps) {
  const point = payload?.[0]?.payload as Point | undefined;
  if (!active || !point) return null;
  return (
    <div className="max-w-64 rounded-2xl border border-white bg-white px-4 py-3 text-sm text-navy-900 shadow-lg ring-1 ring-navy-900/10">
      <p className="font-semibold text-navy-800">{formatLongDate(point.date)}</p>
      <p className="mt-1 flex items-center gap-2">
        <span aria-hidden="true" className="h-0.5 w-4 rounded" style={{ background: LINE }} />
        <span className="text-base font-bold text-navy-950 tabular-nums">
          {formatCents(point.mid)}
        </span>
        <span>most likely</span>
      </p>
      <p className="mt-0.5 flex items-center gap-2">
        <span
          aria-hidden="true"
          className="h-3 w-4 rounded-sm"
          style={{ background: BAND, opacity: 0.3 }}
        />
        <span className="font-semibold text-navy-950 tabular-nums">
          {formatCents(point.low)} to {formatCents(point.high)}
        </span>
      </p>
      {point.bills.map((b) => (
        <p key={`${b.label}-${b.date}`} className="mt-2 border-t border-navy-900/10 pt-2">
          <span className="font-bold text-navy-950">{b.label}</span>{" "}
          <span className="tabular-nums">{formatCents(b.amount_cents)}</span>
          <span className="block text-navy-800">{cushionRisk(b.p_short)}</span>
        </p>
      ))}
    </div>
  );
}

function BillDot(props: { cx?: number; cy?: number; payload?: Point }) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null || !payload || payload.billMid === null) return <g />;
  const short = payload.bills.some((b) => b.weather === "tight");
  return (
    <circle cx={cx} cy={cy} r={5} fill={short ? CUSHION : LINE} stroke={SURFACE} strokeWidth={2} />
  );
}

/**
 * The 30-day balance chart. Decorative to assistive tech except through Recharts' keyboard layer;
 * the same numbers are in the table view next to it.
 */
export function ForecastChart({
  days,
  bills,
  thresholdCents,
  describedBy,
}: {
  days: ForecastDay[];
  bills: ForecastBill[];
  thresholdCents: Cents;
  describedBy: string;
}) {
  const data = toPoints(days, bills);
  return (
    <div className="h-72 w-full sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          margin={{ top: 12, right: 12, bottom: 8, left: 4 }}
          accessibilityLayer
          aria-describedby={describedBy}
          role="application"
          aria-label="Checking balance forecast. Use the left and right arrow keys to read each day."
        >
          <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
          <XAxis
            dataKey="date"
            tickFormatter={formatShortDate}
            interval="preserveStartEnd"
            minTickGap={24}
            tick={{ fill: AXIS_TEXT, fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: GRID }}
          />
          <YAxis
            tickFormatter={formatAxisDollars}
            width={56}
            tick={{ fill: AXIS_TEXT, fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
          />
          <Tooltip
            content={ChartTooltip}
            cursor={{ stroke: "#0a2a4f", strokeWidth: 1 }}
            isAnimationActive={false}
          />
          <Area
            dataKey="band"
            stroke="none"
            fill={BAND}
            fillOpacity={0.22}
            isAnimationActive={false}
            activeDot={false}
          />
          <ReferenceLine
            y={thresholdCents}
            stroke={CUSHION}
            strokeWidth={1}
            ifOverflow="extendDomain"
            label={{
              value: `Cushion ${formatCents(thresholdCents)}`,
              position: "insideBottomLeft",
              fill: AXIS_TEXT,
              fontSize: 12,
              fontWeight: 600,
            }}
          />
          <Line
            dataKey="mid"
            stroke={LINE}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            dot={false}
            activeDot={{ r: 5, fill: LINE, stroke: SURFACE, strokeWidth: 2 }}
            isAnimationActive={false}
          />
          <Line
            dataKey="billMid"
            stroke="none"
            dot={BillDot}
            activeDot={false}
            isAnimationActive={false}
            legendType="none"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
