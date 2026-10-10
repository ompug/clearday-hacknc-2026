"use client";

import type { Me } from "@/lib/api";
import { DisplaySettings } from "./DisplaySettings";
import { ClearMark } from "./icons";

export function AppHeader({ me, onSignOut }: { me: Me | null; onSignOut: () => void }) {
  return (
    <header className="glass-navy relative z-30 md:sticky md:top-0 rounded-b-[1.75rem]">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
        <div className="flex items-center gap-3">
          <ClearMark className="size-10 shrink-0" />
          <div>
            <p className="text-xl leading-tight font-bold tracking-tight">Clearday</p>
            {me ? <p className="text-sm leading-tight text-sky-100">{me.household.name}</p> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {me ? (
            <p className="px-2 font-medium">
              <span className="sr-only">Signed in as </span>
              {me.user.display_name}
            </p>
          ) : null}
          <DisplaySettings />
          <button
            type="button"
            onClick={onSignOut}
            className="inline-flex min-h-11 items-center rounded-full border border-white/40 px-4 font-semibold text-white hover:bg-white/15"
          >
            Switch roommate
          </button>
        </div>
      </div>
    </header>
  );
}
