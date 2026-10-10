"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { SkyBubble } from "@/lib/api";
import {
  bubbleAccessibleName,
  bubbleState,
  clusterAccessibleName,
  type BubbleState,
  type ClusterSummary,
  type SkyEntry,
} from "@/lib/bubbles";
import { dueLabel } from "@/lib/dates";
import { formatCents } from "@/lib/money";
import { usePreferences } from "@/lib/preferences";
import { PeopleIcon, StackIcon } from "../icons";
import { StateBadge, StateIcon } from "../StateBadge";

// Layout constants, in rem so they scale with the text-size control and zoom.
const CELL_REM = 12;
const MIN_CELL_REM = 9.5;
const PILL_REM = 3.25;
const COLUMN_DROP = 0.3;
const MIN_D_REM = 7.75;
const MAX_D_REM = 10.5;
const MEMBER_D_REM = 7.75;
const CLUSTER_D_REM = 9;

/** Bigger bills are bigger bubbles (log scale, clamped so text always fits). */
function diameterRem(cents: number): number {
  const lo = Math.log10(500);
  const hi = Math.log10(60_000);
  const t = Math.min(1, Math.max(0, (Math.log10(Math.max(cents, 1)) - lo) / (hi - lo)));
  return MIN_D_REM + t * (MAX_D_REM - MIN_D_REM);
}

/** Small deterministic jitter so the sky looks organic but never reshuffles. */
function jitter(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return ((h >>> 0) % 1000) / 1000 - 0.5;
}

type Placed =
  | { key: string; kind: "bubble"; bubble: SkyBubble; member: boolean; d: number }
  | { key: string; kind: "cluster"; summary: ClusterSummary; expanded: boolean; d: number };

function useContainerMetrics() {
  const ref = useRef<HTMLDivElement>(null);
  const [metrics, setMetrics] = useState<{ width: number; rem: number } | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      setMetrics({ width: el.clientWidth, rem });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    observer.observe(document.documentElement);
    return () => observer.disconnect();
  }, []);
  return { ref, metrics };
}

function Float({ index, children }: { index: number; children: React.ReactNode }) {
  const { motionReduced } = usePreferences();
  if (motionReduced) return <>{children}</>;
  return (
    <motion.div
      animate={{ y: [0, -9, 0] }}
      transition={{
        duration: 5.5 + (index % 3) * 0.9,
        repeat: Infinity,
        ease: "easeInOut",
        delay: index * 0.35,
      }}
    >
      {children}
    </motion.div>
  );
}

function BubbleFace({
  state,
  label,
  amount,
  sub,
  fill,
  d,
  icon,
}: {
  state: BubbleState;
  label: string;
  amount: string;
  sub?: React.ReactNode;
  fill: number;
  d: number;
  icon: React.ReactNode;
}) {
  return (
    <>
      {fill > 0 ? (
        <span
          aria-hidden="true"
          className="bubble-fill"
          style={{ height: `${Math.round(fill * 100)}%` }}
        />
      ) : null}
      <span
        className="bubble-content flex h-full flex-col items-center justify-center px-[11%] text-center"
        style={{ fontSize: `${Math.min(1, d / 9)}rem` }}
      >
        <span aria-hidden="true" className={state === "tight" ? "text-alert-700" : "text-navy-800"}>
          {icon}
        </span>
        <span className="line-clamp-2 leading-tight font-bold break-words">{label}</span>
        <span className="mt-0.5 text-[1.05em] font-extrabold tabular-nums">{amount}</span>
        {sub ? <span className="mt-0.5 text-[0.8em] font-semibold">{sub}</span> : null}
      </span>
    </>
  );
}

export function SkyView({
  entries,
  onOpen,
}: {
  entries: SkyEntry[];
  onOpen: (bubble: SkyBubble) => void;
}) {
  const { ref, metrics } = useContainerMetrics();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const placed = useMemo<Placed[]>(() => {
    const out: Placed[] = [];
    for (const entry of entries) {
      if (entry.type === "bubble") {
        out.push({
          key: entry.bubble.bubble_id,
          kind: "bubble",
          bubble: entry.bubble,
          member: false,
          d: diameterRem(entry.bubble.your_share_cents),
        });
        continue;
      }
      const id = entry.summary.cluster.cluster_id;
      const isOpen = expanded.has(id);
      out.push({
        key: id,
        kind: "cluster",
        summary: entry.summary,
        expanded: isOpen,
        d: CLUSTER_D_REM,
      });
      if (isOpen) {
        for (const bubble of entry.summary.members) {
          out.push({
            key: bubble.bubble_id,
            kind: "bubble",
            bubble,
            member: true,
            d: MEMBER_D_REM,
          });
        }
      }
    }
    return out;
  }, [entries, expanded]);

  const rem = metrics?.rem ?? 16;
  const width = metrics?.width ?? 0;
  const cols = metrics ? Math.max(1, Math.min(4, Math.floor(width / (MIN_CELL_REM * rem)))) : 1;
  const cellPx = width / cols;
  // On narrow screens bubbles shrink a little so two columns still fit.
  const scale = Math.min(1, cellPx / (CELL_REM * rem));
  const rowRem = MAX_D_REM * scale + PILL_REM;
  const rows = Math.ceil(placed.length / cols);
  const heightRem = rows * rowRem + (cols > 1 ? rowRem * COLUMN_DROP : 0) + 1;

  /** Row-major by due date, so sooner bills float higher; odd columns drop a little. */
  function position(index: number, item: Placed) {
    const row = Math.floor(index / cols);
    const col = index % cols;
    const j = jitter(item.key);
    const drop = col % 2 === 1 ? COLUMN_DROP * rowRem : 0;
    const top = (row * rowRem + drop + (MAX_D_REM - item.d) * 0.5 * scale + j * 0.8 + 0.5) * rem;
    return { left: col * cellPx, top, d: item.d * scale };
  }

  function toggleCluster(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div ref={ref} className="relative w-full" style={{ height: `${heightRem}rem` }}>
      {metrics ? (
        <ol aria-label="Bill sky, soonest due at the top" className="absolute inset-0">
          <AnimatePresence>
            {placed.map((item, index) => {
              const { left, top, d } = position(index, item);
              const size = `${d}rem`;
              return (
                <motion.li
                  key={item.key}
                  layout="position"
                  initial={{ opacity: 0, scale: 0.6 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{
                    opacity: 0,
                    scale: 1.4,
                    filter: "blur(2px)",
                    transition: { duration: 0.45 },
                  }}
                  transition={{ type: "spring", stiffness: 160, damping: 20 }}
                  className="absolute flex flex-col items-center"
                  style={{ left, top, width: cellPx }}
                >
                  <Float index={index}>
                    {item.kind === "bubble" ? (
                      <SkyBubbleButton bubble={item.bubble} d={d} onOpen={onOpen} />
                    ) : (
                      <button
                        type="button"
                        aria-expanded={item.expanded}
                        aria-label={clusterAccessibleName(item.summary, item.expanded)}
                        onClick={() => toggleCluster(item.summary.cluster.cluster_id)}
                        className="bubble block"
                        data-state={item.summary.state}
                        style={{ width: size, height: size }}
                      >
                        <BubbleFace
                          state={item.summary.state}
                          d={d}
                          fill={0}
                          label={item.summary.cluster.label}
                          amount={formatCents(item.summary.totalCents)}
                          sub={`${item.summary.members.length} bills · ${item.expanded ? "hide" : "show"}`}
                          icon={<StackIcon className="mx-auto size-[1.3em]" />}
                        />
                      </button>
                    )}
                  </Float>
                  <StateBadge
                    hidden
                    small
                    className="mt-2 max-w-[95%] justify-center text-center"
                    state={item.kind === "bubble" ? bubbleState(item.bubble) : item.summary.state}
                    extra={dueLabel(
                      item.kind === "bubble" ? item.bubble.due_date : item.summary.earliestDue,
                    )}
                  />
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ol>
      ) : null}
    </div>
  );
}

function SkyBubbleButton({
  bubble,
  d,
  onOpen,
}: {
  bubble: SkyBubble;
  d: number;
  onOpen: (b: SkyBubble) => void;
}) {
  const state = bubbleState(bubble);
  const size = `${d}rem`;
  return (
    <button
      type="button"
      aria-label={bubbleAccessibleName(bubble)}
      onClick={() => onOpen(bubble)}
      data-bubble-id={bubble.bubble_id}
      data-state={state}
      className="bubble block transition-transform hover:scale-[1.04] active:scale-95"
      style={{ width: size, height: size }}
    >
      <BubbleFace
        state={state}
        d={d}
        fill={bubble.kind === "shared" ? bubble.fill_fraction : 0}
        label={bubble.label}
        amount={formatCents(bubble.your_share_cents)}
        sub={
          bubble.kind === "shared" ? (
            <span className="inline-flex items-center gap-1">
              <PeopleIcon className="size-[1.1em]" />
              {bubble.paid_count}/{bubble.participant_count}
            </span>
          ) : undefined
        }
        icon={<StateIcon state={state} className="mx-auto size-[1.3em]" />}
      />
    </button>
  );
}
