"use client";

import { usePathname } from "next/navigation";
import { AeroPillLink } from "./aero";
import type { Me } from "@/lib/api";
import { DisplaySettings } from "./DisplaySettings";
import { ClearMark } from "./icons";

/** Secondary pages, in the order they were added. */
const MORE_LINKS = [
  { href: "/feed", label: "Household feed" },
  { href: "/future", label: "Future view" },
  { href: "/recap", label: "Weekly recap" },
  { href: "/analyst", label: "Analyst view" },
];

export function AppHeader({ me, onSignOut }: { me: Me | null; onSignOut: () => void }) {
  const pathname = usePathname();
  return (
    <header className="glass-navy relative z-30 md:sticky md:top-0 rounded-b-[1.25rem]">
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
            className="aero-btn aero-btn-secondary min-h-11 px-4"
          >
            Switch roommate
          </button>
        </div>
      </div>
      <nav aria-label="More from Clearday" className="mx-auto w-full max-w-6xl px-4 pb-3">
        <ul className="aero-tabs">
          {[
            { href: "/sky", label: "Bills" },
            { href: "/forecast", label: "Money weather" },
            ...MORE_LINKS,
          ].map((l) => (
            <li key={l.href}>
              <AeroPillLink href={l.href} active={pathname === l.href}>
                {l.label}
              </AeroPillLink>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
