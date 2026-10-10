"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ApiError, api, type Account, type PaymentResult, type SkyBubble } from "@/lib/api";
import { bubbleState, canPay } from "@/lib/bubbles";
import { daysBetween, dueDayName, dueLabel, todayIso } from "@/lib/dates";
import { formatCents } from "@/lib/money";
import { CloseIcon, PeopleIcon } from "../icons";
import { StateBadge } from "../StateBadge";

const ACCOUNT_TYPE_LABEL: Record<Account["type"], string> = {
  checking: "Checking",
  savings: "Savings",
  credit_card: "Credit card",
};

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Bubble details plus the pop-to-pay confirmation. Uses the native <dialog>
 * for focus trapping, Escape to close and focus return.
 */
export function PayDialog({
  bubble,
  accounts,
  onClose,
  onPaid,
}: {
  bubble: SkyBubble | null;
  accounts: Account[];
  onClose: () => void;
  onPaid: (bubble: SkyBubble, result: PaymentResult) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [accountId, setAccountId] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (bubble) {
      // One key per confirmation: a double tap or retry reuses it, so it pays once.
      /* eslint-disable react-hooks/set-state-in-effect -- reset form when a new bubble opens */
      setIdempotencyKey(newIdempotencyKey());
      setAccountId(bubble.default_account_id ?? accounts[0]?.account_id ?? "");
      setError(null);
      setSubmitting(false);
      /* eslint-enable react-hooks/set-state-in-effect */
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [bubble, accounts]);

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    if (!bubble || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.pay({
        idempotency_key: idempotencyKey,
        bubble_id: bubble.bubble_id,
        account_id: accountId,
        amount_cents: bubble.your_share_cents,
      });
      onPaid(bubble, result);
    } catch (err) {
      setSubmitting(false);
      setError(
        err instanceof ApiError && err.status === 409
          ? "This bill changed since you opened it. Close and try again."
          : "Payment didn't go through. Nothing was charged. Try again.",
      );
    }
  }

  const state = bubble ? bubbleState(bubble) : "clear";
  const payable = bubble ? canPay(bubble) : false;
  const waitingOn = bubble ? bubble.participant_count - bubble.paid_count : 0;

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onClose={onClose}
      className="glass fixed inset-0 m-auto h-fit max-h-[calc(100dvh-2rem)] overflow-y-auto w-[min(32rem,calc(100vw-2rem))] max-w-none rounded-[2rem] p-0 text-navy-950 backdrop:bg-navy-950/60 backdrop:backdrop-blur-sm"
    >
      {bubble ? (
        <form onSubmit={(e) => void confirm(e)} className="flex flex-col gap-5 p-6 sm:p-8">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 id={titleId} className="text-2xl font-bold break-words">
                {bubble.label}
              </h2>
              <p className="mt-1 text-navy-800">
                {dueLabel(bubble.due_date)}
                {daysBetween(todayIso(), bubble.due_date) > 1
                  ? ` (${dueDayName(bubble.due_date)})`
                  : ""}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="grid size-11 shrink-0 place-items-center rounded-full bg-white text-navy-900 ring-1 ring-navy-900/20 hover:bg-sky-100"
            >
              <CloseIcon className="size-5" />
              <span className="sr-only">Close</span>
            </button>
          </div>

          <div className="flex flex-wrap items-end justify-between gap-3">
            <p>
              <span className="block text-sm font-semibold text-navy-800">
                {bubble.kind === "shared" ? "Your share" : "Amount"}
              </span>
              <span className="text-4xl font-extrabold tabular-nums">
                {formatCents(bubble.your_share_cents)}
              </span>
              {bubble.kind === "shared" ? (
                <span className="block text-navy-800">
                  of {formatCents(bubble.total_cents)} total
                </span>
              ) : null}
            </p>
            <StateBadge state={state} />
          </div>

          {bubble.kind === "shared" ? (
            <div>
              <p className="flex items-center gap-2 font-semibold">
                <PeopleIcon className="size-5" />
                {bubble.paid_count} of {bubble.participant_count} roommates paid
              </p>
              <div
                aria-hidden="true"
                className="mt-2 h-3 overflow-hidden rounded-full bg-sky-100 ring-1 ring-navy-900/15"
              >
                <div
                  className="h-full rounded-full bg-gradient-to-b from-sky-300 to-sky-500 transition-[width] duration-500"
                  style={{ width: `${Math.round(bubble.fill_fraction * 100)}%` }}
                />
              </div>
            </div>
          ) : null}

          {payable ? (
            <>
              <label className="flex flex-col gap-1.5 font-semibold">
                Pay from
                <select
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                  className="min-h-11 rounded-xl border-2 border-navy-900/30 bg-white px-3 font-normal"
                >
                  {accounts.map((a) => (
                    <option key={a.account_id} value={a.account_id}>
                      {a.nickname} ••{a.last4} ({ACCOUNT_TYPE_LABEL[a.type]})
                    </option>
                  ))}
                </select>
              </label>

              {error ? (
                <p
                  role="alert"
                  className="rounded-xl bg-alert-50 px-4 py-3 font-medium text-alert-700"
                >
                  {error}
                </p>
              ) : null}

              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={onClose}
                  className="min-h-12 rounded-full bg-white px-6 font-semibold text-navy-900 ring-2 ring-navy-900/25 hover:bg-sky-50"
                >
                  Not now
                </button>
                <button
                  type="submit"
                  disabled={submitting || !accountId}
                  className="min-h-12 rounded-full bg-gradient-to-b from-alert-600 to-alert-700 px-6 font-bold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.45),0_0.4rem_1rem_rgb(162_12_36/0.35)] hover:from-alert-700 disabled:opacity-60"
                >
                  {submitting ? "Paying…" : `Pop it: pay ${formatCents(bubble.your_share_cents)}`}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="rounded-2xl bg-sky-100 px-4 py-3 font-medium">
                {bubble.status === "disputed"
                  ? "This share is on hold while the household sorts it out. Reminders are paused."
                  : `Your share is paid. Waiting on ${waitingOn} ${waitingOn === 1 ? "roommate" : "roommates"}; the bubble pops for everyone when it's covered.`}
              </p>
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={onClose}
                  className="min-h-12 rounded-full bg-navy-900 px-6 font-semibold text-white hover:bg-navy-800"
                >
                  Close
                </button>
              </div>
            </>
          )}
        </form>
      ) : null}
    </dialog>
  );
}
