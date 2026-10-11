"use client";

import { useEffect, useId, useRef, useState } from "react";
import {
  ApiError,
  api,
  type Cents,
  type CreateExpenseResult,
  type HouseholdMember,
  type SplitMethod,
} from "@/lib/api";
import { addDays, todayIso } from "@/lib/dates";
import { formatCents } from "@/lib/money";
import { CheckIcon, CloseIcon, FlagIcon } from "../icons";
import { centsToInput, parseDollarsToCents, previewEvenSplit, previewItemizedSplit } from "./cents";
import { ItemizedPanel, newItem, type DraftItem } from "./ItemizedPanel";

const LABEL_MAX = 80;

/** The dialog's own method list: itemized is built here and submitted as `custom` amounts. */
type UiMethod = SplitMethod | "itemized";

interface Draft {
  label: string;
  total: string;
  dueDate: string;
  method: UiMethod;
  participants: string[];
  custom: Record<string, string>;
  items: DraftItem[];
  tax: string;
  tip: string;
}

function freshDraft(members: HouseholdMember[]): Draft {
  return {
    label: "",
    total: "",
    dueDate: addDays(todayIso(), 7),
    method: "even",
    participants: members.map((m) => m.user_id),
    custom: {},
    items: [],
    tax: "",
    tip: "",
  };
}

/**
 * "New shared expense": the signed-in user paid for something and splits it with roommates,
 * evenly or with custom amounts. Shows every share before submitting and checks that custom
 * amounts add up to the total, to the cent. The server recomputes and stores the real shares.
 */
export function NewExpenseDialog({
  open,
  meId,
  onClose,
  onCreated,
}: {
  open: boolean;
  meId: string | null;
  onClose: () => void;
  onCreated: (result: CreateExpenseResult, names: string[]) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const labelRef = useRef<HTMLInputElement>(null);
  const uid = useId();
  const [members, setMembers] = useState<HouseholdMember[]>([]);
  const [draft, setDraft] = useState<Draft>(() => freshDraft([]));
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [scan, setScan] = useState<{ merchant: string; date: string | null } | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      /* eslint-disable react-hooks/set-state-in-effect -- reset the form each time it opens */
      setIdempotencyKey(crypto.randomUUID());
      setShowErrors(false);
      setSubmitting(false);
      setServerError(null);
      setDraft(freshDraft(members));
      setScan(null);
      /* eslint-enable react-hooks/set-state-in-effect */
      if (!dialog.open) dialog.showModal();
      // Start on the first field rather than the Close button.
      requestAnimationFrame(() => labelRef.current?.focus());
      if (members.length === 0) {
        api
          .listHouseholdMembers()
          .then((r) => {
            setMembers(r.members);
            setDraft((d) =>
              d.participants.length ? d : { ...d, participants: r.members.map((m) => m.user_id) },
            );
          })
          .catch(() => setServerError("Couldn't load your household. Close and try again."));
      }
    } else if (dialog.open) {
      dialog.close();
    }
    // members is read once per open; refetching on its change would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const itemized = draft.method === "itemized";
  const chosenIds = draft.participants;
  const itemCents = draft.items.map((i) => parseDollarsToCents(i.amount));
  const taxCents = draft.tax.trim() === "" ? 0 : parseDollarsToCents(draft.tax);
  const tipCents = draft.tip.trim() === "" ? 0 : parseDollarsToCents(draft.tip);
  const itemizedTotal =
    itemCents.every((c) => c !== null) && taxCents !== null && tipCents !== null
      ? itemCents.reduce<number>((sum, c) => sum + (c ?? 0), 0) + taxCents + tipCents
      : null;
  const totalCents = itemized ? itemizedTotal : parseDollarsToCents(draft.total);
  const chosen = members.filter((m) => draft.participants.includes(m.user_id));
  const others = chosen.filter((m) => m.user_id !== meId);

  const shares = (() => {
    const map = new Map<string, Cents | null>();
    if (draft.method === "itemized") {
      const lines = draft.items.map((i, n) => ({
        amount_cents: itemCents[n] ?? 0,
        user_ids: i.assignees,
      }));
      const split = previewItemizedSplit(lines, taxCents ?? 0, tipCents ?? 0, chosenIds);
      for (const id of chosenIds) map.set(id, itemizedTotal === null ? null : split.get(id)!);
    } else if (draft.method === "even") {
      const even = previewEvenSplit(totalCents ?? 0, draft.participants);
      for (const id of draft.participants) map.set(id, totalCents === null ? null : even.get(id)!);
    } else {
      for (const id of draft.participants) map.set(id, parseDollarsToCents(draft.custom[id] ?? ""));
    }
    return map;
  })();

  const customValues = [...shares.values()];
  const itemErrors = draft.items.map((i, n) =>
    i.label.trim() === ""
      ? "Name this item."
      : itemCents[n] === null || itemCents[n] === 0
        ? "Enter its price, like 4.50."
        : !i.assignees.some((a) => draft.participants.includes(a))
          ? "Tick at least one person who shared it."
          : null,
  );
  const customComplete = customValues.every((v) => v !== null);
  const assigned = customValues.reduce<number>((sum, v) => sum + (v ?? 0), 0);
  const remaining = (totalCents ?? 0) - assigned;

  const errors = {
    label:
      draft.label.trim().length === 0 ? "Give it a name, like Groceries or Pizza night." : null,
    total:
      totalCents === null || totalCents <= 0
        ? "Enter the total you paid, like 42.50."
        : totalCents > 1_000_000_00
          ? "That's more than this app handles."
          : null,
    participants: others.length === 0 ? "Pick at least one roommate to split with." : null,
    items: !itemized
      ? null
      : draft.items.length === 0
        ? "Add at least one item, or scan a receipt."
        : itemErrors.some((e) => e !== null) || taxCents === null || tipCents === null
          ? "Fix the highlighted items, tax or tip."
          : null,
    custom:
      draft.method !== "custom" || totalCents === null
        ? null
        : !customComplete
          ? "Enter an amount for everyone in the split (0 is fine)."
          : remaining !== 0
            ? remaining > 0
              ? `${formatCents(remaining)} still to assign.`
              : `${formatCents(-remaining)} over the total.`
            : null,
  };
  const valid = Object.values(errors).every((e) => e === null);

  function update(patch: Partial<Draft>) {
    setDraft((d) => ({ ...d, ...patch }));
  }

  function toggleParticipant(id: string, checked: boolean) {
    setDraft((d) => ({
      ...d,
      participants: checked
        ? members.map((m) => m.user_id).filter((m) => m === id || d.participants.includes(m))
        : d.participants.filter((p) => p !== id),
    }));
  }

  function chooseMethod(method: UiMethod) {
    setDraft((d) => {
      if (method === "itemized" && d.items.length === 0) {
        return { ...d, method, items: [newItem(d.participants)] };
      }
      if (method === "custom" && totalCents !== null) {
        // Start custom from the even split so the sum already matches.
        const even = previewEvenSplit(totalCents, d.participants);
        const custom: Record<string, string> = {};
        for (const id of d.participants) custom[id] = d.custom[id] ?? centsToInput(even.get(id)!);
        return { ...d, method, custom };
      }
      return { ...d, method };
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (submitting) return;
    if (!valid || totalCents === null) {
      setShowErrors(true);
      // Move focus to the first problem so keyboard and screen-reader users land on it.
      requestAnimationFrame(() =>
        dialogRef.current?.querySelector<HTMLElement>("[aria-invalid='true']")?.focus(),
      );
      return;
    }
    setSubmitting(true);
    setServerError(null);
    try {
      const result = await api.createExpense({
        idempotency_key: idempotencyKey,
        label: draft.label.trim(),
        total_cents: totalCents,
        split_method: draft.method === "itemized" ? "custom" : draft.method,
        participants: draft.participants.map((user_id) =>
          draft.method !== "even"
            ? { user_id, amount_cents: shares.get(user_id) ?? 0 }
            : { user_id },
        ),
        due_date: draft.dueDate || null,
      });
      if (itemized && scan) {
        // Remember the confirmed items for price comparisons; never blocks or fails the save.
        const kept = draft.items.flatMap((i, n) => {
          const cents = itemCents[n];
          return i.label.trim() && cents ? [{ label: i.label.trim(), amount_cents: cents }] : [];
        });
        if (kept.length > 0) {
          void api
            .rememberPrices({ merchant: scan.merchant, date: scan.date ?? todayIso(), items: kept })
            .catch(() => undefined);
        }
      }
      onCreated(
        result,
        others.map((m) => m.display_name),
      );
    } catch (err) {
      setSubmitting(false);
      setServerError(
        err instanceof ApiError && err.status === 422
          ? "Something in the split doesn't add up. Check the amounts and try again."
          : "Couldn't save the expense. Nothing was added. Try again.",
      );
    }
  }

  const titleId = `${uid}-title`;
  const err = (key: keyof typeof errors) => (showErrors ? errors[key] : null);
  const fieldClass =
    "min-h-11 w-full rounded-xl border-2 bg-white px-3 font-normal text-navy-950 aria-[invalid=true]:border-alert-700";

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onClose={onClose}
      className="glass fixed inset-0 m-auto h-fit max-h-[calc(100dvh-2rem)] w-[min(36rem,calc(100vw-2rem))] max-w-none overflow-y-auto aero-panel p-0 text-navy-950 backdrop:bg-navy-950/60 backdrop:backdrop-blur-sm"
    >
      {open ? (
        <form
          noValidate
          onSubmit={(e) => void submit(e)}
          className="flex flex-col gap-5 p-6 sm:p-8"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 id={titleId} className="text-2xl font-bold">
                New shared expense
              </h2>
              <p className="mt-1 text-navy-800">
                You paid. Your roommates each get a bubble for their share.
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

          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${uid}-label`} className="font-semibold">
              What was it for?
            </label>
            <input
              ref={labelRef}
              id={`${uid}-label`}
              type="text"
              autoComplete="off"
              maxLength={LABEL_MAX}
              value={draft.label}
              onChange={(e) => update({ label: e.target.value })}
              aria-invalid={err("label") ? true : undefined}
              aria-describedby={err("label") ? `${uid}-label-err` : undefined}
              className={`${fieldClass} border-navy-900/30`}
            />
            <FieldError id={`${uid}-label-err`} message={err("label")} />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <label htmlFor={`${uid}-total`} className="font-semibold">
                {itemized ? "Total (items + tax + tip)" : "Total you paid"}
              </label>
              <div className="relative">
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-y-0 left-3 grid place-items-center font-semibold text-navy-800"
                >
                  $
                </span>
                <input
                  id={`${uid}-total`}
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder="0.00"
                  value={
                    itemized ? (totalCents === null ? "" : centsToInput(totalCents)) : draft.total
                  }
                  readOnly={itemized}
                  onChange={(e) => update({ total: e.target.value })}
                  aria-invalid={err("total") ? true : undefined}
                  aria-describedby={err("total") ? `${uid}-total-err` : undefined}
                  className={`${fieldClass} border-navy-900/30 pl-7 tabular-nums placeholder:text-navy-600`}
                />
              </div>
              <FieldError id={`${uid}-total-err`} message={err("total")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={`${uid}-due`} className="font-semibold">
                Roommates pay by
              </label>
              <input
                id={`${uid}-due`}
                type="date"
                min={todayIso()}
                value={draft.dueDate}
                onChange={(e) => update({ dueDate: e.target.value })}
                className={`${fieldClass} border-navy-900/30`}
              />
            </div>
          </div>

          <fieldset
            aria-describedby={err("participants") ? `${uid}-people-err` : undefined}
            className="flex flex-col gap-2"
          >
            <legend className="font-semibold">Who&rsquo;s in?</legend>
            <div className="mt-1 flex flex-wrap gap-2">
              {members.map((m) => {
                const checked = draft.participants.includes(m.user_id);
                const isMe = m.user_id === meId;
                return (
                  <label
                    key={m.user_id}
                    className="flex min-h-11 cursor-pointer items-center gap-2 rounded-full border-2 border-navy-900/20 bg-white px-4 font-semibold has-checked:border-navy-900 has-checked:bg-sky-100 has-focus-visible:outline-3 has-focus-visible:outline-navy-900"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => toggleParticipant(m.user_id, e.target.checked)}
                      aria-invalid={err("participants") && !isMe ? true : undefined}
                      className="size-4 accent-navy-900"
                    />
                    {isMe ? `You (${m.display_name})` : m.display_name}
                  </label>
                );
              })}
              {members.length === 0 ? (
                <p role="status" className="text-navy-800">
                  Loading roommates…
                </p>
              ) : null}
            </div>
            <FieldError id={`${uid}-people-err`} message={err("participants")} />
          </fieldset>

          <fieldset className="flex flex-col gap-3">
            <legend className="font-semibold">How to split it</legend>
            <div className="mt-1 grid gap-2 sm:grid-cols-3">
              {(
                [
                  ["even", "Evenly"],
                  ["custom", "Custom amounts"],
                  ["itemized", "By item"],
                ] as const
              ).map(([id, text]) => (
                <label
                  key={id}
                  className="flex min-h-11 cursor-pointer items-center gap-2 rounded-2xl border-2 border-navy-900/20 bg-white px-3 font-semibold has-checked:border-navy-900 has-checked:bg-sky-100 has-focus-visible:outline-3 has-focus-visible:outline-navy-900"
                >
                  <input
                    type="radio"
                    name={`${uid}-method`}
                    value={id}
                    checked={draft.method === id}
                    onChange={() => chooseMethod(id)}
                    className="size-4 accent-navy-900"
                  />
                  {text}
                </label>
              ))}
            </div>

            {itemized ? (
              <>
                <ItemizedPanel
                  people={chosen}
                  meId={meId}
                  items={draft.items}
                  tax={draft.tax}
                  tip={draft.tip}
                  itemErrors={itemErrors.map((e) => (showErrors ? e : null))}
                  onItems={(items) => update({ items })}
                  onTax={(tax) => update({ tax })}
                  onTip={(tip) => update({ tip })}
                  onScanned={setScan}
                  onMerchant={(merchant) =>
                    setDraft((d) =>
                      d.label.trim() ? d : { ...d, label: merchant.slice(0, LABEL_MAX) },
                    )
                  }
                  fieldClass={fieldClass}
                />
                <FieldError id={`${uid}-items-err`} message={err("items")} />
              </>
            ) : null}

            <ul aria-label="Shares" className="flex flex-col gap-2">
              {chosen.map((m) => {
                const isMe = m.user_id === meId;
                const share = shares.get(m.user_id) ?? null;
                const name = isMe ? `You (${m.display_name})` : m.display_name;
                return (
                  <li
                    key={m.user_id}
                    className="aero-tile flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-2xl px-4 py-2"
                  >
                    <span className="min-w-0">
                      <span className="block font-semibold">{name}</span>
                      <span className="block text-sm text-navy-800">
                        {isMe ? "Already paid (you paid the store)" : "Gets a bubble to pop"}
                      </span>
                    </span>
                    {draft.method !== "custom" ? (
                      <span className="font-bold tabular-nums">
                        {share === null ? "—" : formatCents(share)}
                      </span>
                    ) : (
                      <span className="relative w-32">
                        <span
                          aria-hidden="true"
                          className="pointer-events-none absolute inset-y-0 left-3 grid place-items-center font-semibold text-navy-800"
                        >
                          $
                        </span>
                        <input
                          type="text"
                          inputMode="decimal"
                          autoComplete="off"
                          aria-label={`${name} share in dollars`}
                          value={draft.custom[m.user_id] ?? ""}
                          onChange={(e) =>
                            update({ custom: { ...draft.custom, [m.user_id]: e.target.value } })
                          }
                          aria-invalid={
                            showErrors && errors.custom && share === null ? true : undefined
                          }
                          className={`${fieldClass} border-navy-900/30 pl-7 text-right tabular-nums`}
                        />
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>

            {itemized && totalCents !== null && totalCents > 0 ? (
              <SumCheck
                ok
                text={`Shares add up to ${formatCents(totalCents)}, tax and tip included.`}
              />
            ) : null}

            {draft.method === "custom" && totalCents !== null && totalCents > 0 ? (
              <SumCheck
                ok={errors.custom === null}
                text={
                  errors.custom === null
                    ? `Adds up to ${formatCents(totalCents)}.`
                    : `${errors.custom} Shares total ${formatCents(assigned)} of ${formatCents(totalCents)}.`
                }
              />
            ) : null}
          </fieldset>

          {serverError ? (
            <p role="alert" className="rounded-xl bg-alert-50 px-4 py-3 font-medium text-alert-700">
              {serverError}
            </p>
          ) : null}

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={onClose}
              className="min-h-12 aero-btn aero-btn-secondary px-6"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              aria-disabled={!valid || undefined}
              className="aero-btn min-h-12 rounded-full px-6"
            >
              {submitting
                ? "Saving…"
                : others.length > 0
                  ? `Split with ${others.length} ${others.length === 1 ? "roommate" : "roommates"}`
                  : "Split it"}
            </button>
          </div>
        </form>
      ) : null}
    </dialog>
  );
}

function FieldError({ id, message }: { id: string; message: string | null }) {
  if (!message) return null;
  return (
    <p id={id} className="flex items-center gap-1.5 text-sm font-semibold text-alert-700">
      <FlagIcon className="size-4 shrink-0" />
      {message}
    </p>
  );
}

/** Live "does it add up" line: icon plus text, announced politely as amounts change. */
function SumCheck({ ok, text }: { ok: boolean; text: string }) {
  return (
    <p
      role="status"
      aria-live="polite"
      className={`flex items-center gap-2 rounded-xl px-4 py-2.5 font-semibold ${
        ok ? "bg-sky-100 text-navy-900" : "bg-alert-50 text-alert-700"
      }`}
    >
      {ok ? <CheckIcon className="size-5 shrink-0" /> : <FlagIcon className="size-5 shrink-0" />}
      {text}
    </p>
  );
}
