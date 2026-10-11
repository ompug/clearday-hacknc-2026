"use client";

import { useEffect, useId, useRef, useState } from "react";
import { TEXT_SIZES, usePreferences } from "@/lib/preferences";
import { SettingsIcon } from "./icons";

/** Disclosure with the reduced-motion toggle and the text-size control. */
export function DisplaySettings() {
  const { motionReduced, reduceMotion, setReduceMotion, textSize, setTextSize } = usePreferences();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    function onPointer(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="aero-btn aero-btn-secondary min-h-11 px-4"
      >
        <SettingsIcon className="size-5" />
        Display
      </button>

      <div
        id={panelId}
        hidden={!open}
        className="glass absolute right-0 z-40 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-3xl p-5 text-navy-950"
      >
        <h2 className="text-lg font-bold">Display</h2>

        <div className="mt-4 flex items-start justify-between gap-4">
          <div>
            <p id={`${panelId}-motion`} className="font-semibold">
              Still bubbles
            </p>
            <p id={`${panelId}-motion-desc`} className="text-sm text-navy-800">
              {reduceMotion === null
                ? `Following your device setting (${motionReduced ? "reduced" : "full"} motion).`
                : "Stops floating and popping animations."}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={motionReduced}
            aria-labelledby={`${panelId}-motion`}
            aria-describedby={`${panelId}-motion-desc`}
            onClick={() => setReduceMotion(!motionReduced)}
            className={`relative mt-1 inline-flex h-8 w-14 shrink-0 items-center rounded-full border-2 border-navy-900 transition-colors ${
              motionReduced ? "bg-navy-900" : "bg-white"
            }`}
          >
            <span
              aria-hidden="true"
              className={`inline-block size-5 rounded-full transition-transform ${
                motionReduced ? "translate-x-7 bg-white" : "translate-x-1 bg-navy-900"
              }`}
            />
            <span className="sr-only">{motionReduced ? "On" : "Off"}</span>
          </button>
        </div>

        <fieldset className="mt-5">
          <legend className="font-semibold">Text size</legend>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {TEXT_SIZES.map((size) => (
              <label
                key={size.id}
                className="flex min-h-11 cursor-pointer items-center gap-2 rounded-2xl border-2 border-navy-900/20 bg-white px-3 has-checked:border-navy-900 has-checked:bg-sky-100 has-focus-visible:outline-3 has-focus-visible:outline-navy-900"
              >
                <input
                  type="radio"
                  name={`${panelId}-text-size`}
                  value={size.id}
                  checked={textSize === size.id}
                  onChange={() => setTextSize(size.id)}
                  className="size-4 accent-navy-900"
                />
                <span>{size.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>
    </div>
  );
}
