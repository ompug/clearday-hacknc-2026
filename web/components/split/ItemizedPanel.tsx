"use client";

import { useId, useRef, useState } from "react";
import { ApiError, api, type HouseholdMember, type ReceiptReadResult } from "@/lib/api";
import { CheckIcon, CloseIcon, FlagIcon, PlusIcon } from "../icons";
import { centsToInput } from "./cents";

export interface DraftItem {
  key: string;
  label: string;
  amount: string;
  assignees: string[];
}

const MAX_BYTES = 5 * 1024 * 1024;
const TYPES = ["image/png", "image/jpeg", "image/webp"];
const ITEM_MAX = 40;

export function newItem(assignees: string[]): DraftItem {
  return { key: crypto.randomUUID(), label: "", amount: "", assignees };
}

export function itemsFromReceipt(result: ReceiptReadResult, assignees: string[]): DraftItem[] {
  return result.items.map((i) => ({
    key: crypto.randomUUID(),
    label: i.label,
    amount: centsToInput(i.amount_cents),
    assignees,
  }));
}

function scanFailure(error: unknown): string {
  const status = error instanceof ApiError ? error.status : 0;
  if (status === 503)
    return "The receipt reader isn't available right now. Enter the items by hand below.";
  if (status === 422)
    return "Couldn't read that receipt, or its items didn't add up. Enter the items by hand below.";
  if (status === 413)
    return "That photo is over 5 MB. Try a smaller one, or enter the items by hand.";
  if (status === 415) return "Use a PNG, JPEG or WebP photo, or enter the items by hand.";
  return "Couldn't reach the receipt reader. Enter the items by hand below.";
}

/**
 * Itemized split inside the New expense dialog: scan a receipt (the server reads it with the
 * model and deletes the image) or type items by hand, then tick who shared each item. Tax and tip
 * are spread by each person's item subtotal. Both paths end in the same editable list, so the
 * manual form is always the fallback.
 */
export function ItemizedPanel({
  people,
  meId,
  items,
  tax,
  tip,
  itemErrors,
  onItems,
  onTax,
  onTip,
  onMerchant,
  fieldClass,
}: {
  people: HouseholdMember[];
  meId: string | null;
  items: DraftItem[];
  tax: string;
  tip: string;
  itemErrors: (string | null)[];
  onItems: (items: DraftItem[]) => void;
  onTax: (value: string) => void;
  onTip: (value: string) => void;
  onMerchant: (merchant: string) => void;
  fieldClass: string;
}) {
  const uid = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const [reading, setReading] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const everyone = people.map((p) => p.user_id);

  async function scan(file: File | undefined) {
    if (!file || reading) return;
    if (!TYPES.includes(file.type))
      return setNote({ ok: false, text: scanFailure(new ApiError(415, "")) });
    if (file.size > MAX_BYTES)
      return setNote({ ok: false, text: scanFailure(new ApiError(413, "")) });
    setReading(true);
    setNote(null);
    try {
      const result = await api.readReceipt(file);
      onItems(itemsFromReceipt(result, everyone));
      onTax(centsToInput(result.tax_cents));
      onTip(centsToInput(result.tip_cents));
      onMerchant(result.merchant);
      setNote({
        ok: true,
        text: `Read ${result.items.length} items from the receipt. Check them against the paper, then tick who shared each one.`,
      });
    } catch (error) {
      setNote({ ok: false, text: scanFailure(error) });
    } finally {
      setReading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function patch(key: string, change: Partial<DraftItem>) {
    onItems(items.map((i) => (i.key === key ? { ...i, ...change } : i)));
  }

  function toggle(item: DraftItem, id: string, checked: boolean) {
    patch(item.key, {
      assignees: checked ? [...item.assignees, id] : item.assignees.filter((a) => a !== id),
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 rounded-2xl border border-white bg-white/85 p-4 shadow-sm">
        <label htmlFor={`${uid}-scan`} className="font-semibold">
          Scan a receipt (optional)
        </label>
        <input
          ref={fileRef}
          id={`${uid}-scan`}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          disabled={reading}
          onChange={(e) => void scan(e.target.files?.[0])}
          className="min-h-11 w-full rounded-xl border-2 border-navy-900/30 bg-white p-2 text-navy-950 file:mr-3 file:min-h-9 file:rounded-full file:border-0 file:bg-navy-900 file:px-4 file:font-semibold file:text-white"
        />
        <p className="text-sm text-navy-800">
          The photo is read once and deleted right away. You can fix every item before saving.
        </p>
        <p role="status" aria-live="polite" className={note || reading ? "" : "sr-only"}>
          {reading ? (
            <span className="font-semibold text-navy-900">Reading your receipt…</span>
          ) : note ? (
            <span
              className={`flex items-start gap-2 rounded-xl px-3 py-2 font-semibold ${
                note.ok ? "bg-sky-100 text-navy-900" : "bg-alert-50 text-alert-700"
              }`}
            >
              {note.ok ? (
                <CheckIcon className="mt-0.5 size-5 shrink-0" />
              ) : (
                <FlagIcon className="mt-0.5 size-5 shrink-0" />
              )}
              {note.text}
            </span>
          ) : null}
        </p>
      </div>

      <ul aria-label="Items" className="flex flex-col gap-3">
        {items.map((item, index) => {
          const error = itemErrors[index];
          return (
            <li
              key={item.key}
              className="flex flex-col gap-2 rounded-2xl border border-white bg-white/85 p-3 shadow-sm"
            >
              <div className="flex items-start gap-2">
                <input
                  type="text"
                  autoComplete="off"
                  maxLength={ITEM_MAX}
                  aria-label={`Item ${index + 1} name`}
                  placeholder="Item"
                  value={item.label}
                  onChange={(e) => patch(item.key, { label: e.target.value })}
                  aria-invalid={error ? true : undefined}
                  className={`${fieldClass} border-navy-900/30 placeholder:text-navy-600`}
                />
                <span className="relative w-28 shrink-0">
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
                    aria-label={`Item ${index + 1} price in dollars`}
                    placeholder="0.00"
                    value={item.amount}
                    onChange={(e) => patch(item.key, { amount: e.target.value })}
                    aria-invalid={error ? true : undefined}
                    className={`${fieldClass} border-navy-900/30 pl-7 text-right tabular-nums placeholder:text-navy-600`}
                  />
                </span>
                <button
                  type="button"
                  onClick={() => onItems(items.filter((i) => i.key !== item.key))}
                  className="grid size-11 shrink-0 place-items-center rounded-full bg-white text-navy-900 ring-1 ring-navy-900/20 hover:bg-sky-100"
                >
                  <CloseIcon className="size-5" />
                  <span className="sr-only">Remove item {index + 1}</span>
                </button>
              </div>
              <fieldset className="flex flex-wrap gap-2">
                <legend className="sr-only">Who shared item {index + 1}</legend>
                {people.map((m) => (
                  <label
                    key={m.user_id}
                    className="flex min-h-9 cursor-pointer items-center gap-1.5 rounded-full border-2 border-navy-900/20 bg-white px-3 text-sm font-semibold has-checked:border-navy-900 has-checked:bg-sky-100 has-focus-visible:outline-3 has-focus-visible:outline-navy-900"
                  >
                    <input
                      type="checkbox"
                      checked={item.assignees.includes(m.user_id)}
                      onChange={(e) => toggle(item, m.user_id, e.target.checked)}
                      className="size-4 accent-navy-900"
                    />
                    {m.user_id === meId ? "You" : m.display_name}
                  </label>
                ))}
              </fieldset>
              {error ? (
                <p className="flex items-center gap-1.5 text-sm font-semibold text-alert-700">
                  <FlagIcon className="size-4 shrink-0" />
                  {error}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>

      <button
        type="button"
        onClick={() => onItems([...items, newItem(everyone)])}
        className="flex min-h-11 items-center justify-center gap-2 self-start rounded-full bg-white px-5 font-semibold text-navy-900 ring-2 ring-navy-900/25 hover:bg-sky-50"
      >
        <PlusIcon className="size-5" />
        Add an item
      </button>

      <div className="grid gap-4 sm:grid-cols-2">
        {(
          [
            ["Tax", tax, onTax],
            ["Tip", tip, onTip],
          ] as const
        ).map(([name, value, set]) => (
          <div key={name} className="flex flex-col gap-1.5">
            <label htmlFor={`${uid}-${name}`} className="font-semibold">
              {name}
            </label>
            <div className="relative">
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-y-0 left-3 grid place-items-center font-semibold text-navy-800"
              >
                $
              </span>
              <input
                id={`${uid}-${name}`}
                type="text"
                inputMode="decimal"
                autoComplete="off"
                placeholder="0.00"
                value={value}
                onChange={(e) => set(e.target.value)}
                className={`${fieldClass} border-navy-900/30 pl-7 tabular-nums placeholder:text-navy-600`}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="text-sm text-navy-800">Tax and tip are spread by what each person ordered.</p>
    </div>
  );
}
