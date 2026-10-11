"use client";

import { useId, useRef, useState } from "react";
import {
  ApiError,
  api,
  type AssistantResponse,
  type AssistantSplitProposal,
  type CreateExpenseResult,
} from "@/lib/api";
import { formatCents } from "@/lib/money";
import { CheckIcon, CloseIcon, PeopleIcon } from "../icons";

const MESSAGE_MAX = 500;
const EXAMPLE = "Split last night's pizza with Jake";

/**
 * "Split with words": the user types a request, the backend (Gemma behind the AI gateway, or a
 * template when the model is busy) finds the purchase and proposes an even split computed from the
 * ledger. Nothing is saved until the user confirms; confirming calls POST /api/expenses, which
 * validates the split again.
 */
export function SplitAssistant({
  disabled,
  onCreated,
}: {
  disabled: boolean;
  onCreated: (result: CreateExpenseResult, names: string[]) => void;
}) {
  const uid = useId();
  const proposalHeadingRef = useRef<HTMLHeadingElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<AssistantResponse | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    const text = message.trim();
    if (!text || asking) return;
    setAsking(true);
    setError(null);
    setAnswer(null);
    try {
      const res = await api.askAssistant({ message: text });
      setAnswer(res);
      setIdempotencyKey(crypto.randomUUID());
      if (res.proposal) requestAnimationFrame(() => proposalHeadingRef.current?.focus());
    } catch {
      setError("Couldn't reach the assistant. Try again, or use New shared expense.");
    } finally {
      setAsking(false);
    }
  }

  async function confirm(proposal: AssistantSplitProposal) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.createExpense({
        idempotency_key: idempotencyKey,
        label: proposal.label,
        total_cents: proposal.total_cents,
        split_method: proposal.split_method,
        participants: proposal.participants.map((p) => ({ user_id: p.user_id })),
        source_txn_id: proposal.source_txn_id,
      });
      const myId = result.payer_id;
      onCreated(
        result,
        proposal.participants.filter((p) => p.user_id !== myId).map((p) => p.display_name),
      );
      setAnswer(null);
      setMessage("");
      inputRef.current?.focus();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "That purchase is already split."
          : err instanceof ApiError && err.status === 422
            ? "That split no longer matches your household. Ask again."
            : "Couldn't save the split. Nothing was added. Try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  function dismiss() {
    setAnswer(null);
    inputRef.current?.focus();
  }

  const proposal = answer?.proposal ?? null;
  const headingId = `${uid}-heading`;
  const proposalId = `${uid}-proposal`;

  return (
    <section aria-labelledby={headingId} className="glass mt-5 rounded-[1.75rem] p-5 sm:p-6">
      <h2 id={headingId} className="flex items-center gap-2 text-xl font-bold text-navy-950">
        <PeopleIcon className="size-6" />
        Split with words
      </h2>
      <p className="mt-1 text-navy-800">
        Describe a purchase and who shared it. You check the split before anything is saved.
      </p>

      <form onSubmit={(e) => void ask(e)} className="mt-4 flex flex-col gap-3 sm:flex-row">
        <div className="flex flex-1 flex-col gap-1.5">
          <label htmlFor={`${uid}-message`} className="font-semibold text-navy-950">
            What should we split?
          </label>
          <input
            ref={inputRef}
            id={`${uid}-message`}
            type="text"
            value={message}
            maxLength={MESSAGE_MAX}
            placeholder={EXAMPLE}
            disabled={disabled}
            autoComplete="off"
            onChange={(e) => setMessage(e.target.value)}
            className="min-h-11 w-full rounded-xl border-2 border-navy-900/30 bg-white px-3 text-navy-950 placeholder:text-navy-700"
          />
        </div>
        <button
          type="submit"
          disabled={disabled || asking || message.trim().length === 0}
          className="min-h-11 self-end rounded-full bg-navy-900 px-6 font-bold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.35),0_0.4rem_1rem_rgb(6_23_48/0.3)] hover:bg-navy-800 disabled:opacity-60"
        >
          {asking ? "Looking…" : "Find it"}
        </button>
      </form>

      <div aria-live="polite" className="mt-4">
        {asking ? <p className="text-navy-800">Looking for that purchase…</p> : null}
        {answer && !proposal ? (
          <p className="rounded-2xl bg-white/80 p-4 font-semibold text-navy-950">{answer.reply}</p>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="mt-3 font-semibold text-alert-700">
          {error}
        </p>
      ) : null}

      {proposal && answer ? (
        <div
          role="group"
          aria-labelledby={proposalId}
          className="mt-2 rounded-2xl bg-white/85 p-4 text-navy-950 sm:p-5"
        >
          <h3 id={proposalId} ref={proposalHeadingRef} tabIndex={-1} className="text-lg font-bold">
            Proposed split: {proposal.label}
          </h3>
          <p className="mt-1 text-navy-800">
            {formatCents(proposal.total_cents)} on {proposal.purchase_date}, split evenly.{" "}
            {answer.source === "model"
              ? "Found by Gemma; amounts computed by Clearday."
              : "Quick match while the model is busy; amounts computed by Clearday."}
          </p>
          <ul className="mt-3 divide-y divide-navy-900/10" aria-label="Shares">
            {proposal.participants.map((p) => (
              <li key={p.user_id} className="flex justify-between gap-4 py-2">
                <span className="font-semibold">{p.display_name}</span>
                <span className="font-bold tabular-nums">{formatCents(p.amount_cents)}</span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void confirm(proposal)}
              disabled={saving}
              className="inline-flex min-h-11 items-center gap-2 rounded-full bg-navy-900 px-5 font-bold text-white hover:bg-navy-800 disabled:opacity-60"
            >
              <CheckIcon className="size-5" />
              {saving ? "Saving…" : "Confirm split"}
            </button>
            <button
              type="button"
              onClick={dismiss}
              disabled={saving}
              className="inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-5 font-bold text-navy-900 ring-1 ring-navy-900/30 hover:bg-sky-100"
            >
              <CloseIcon className="size-5" />
              Not right
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
