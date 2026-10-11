"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, type Me } from "@/lib/api";
import { BubblesIcon, ClearMark, CloudSunIcon, PeopleIcon, PlusIcon } from "../icons";

interface MobileSession {
  me: Me;
  announce: (text: string) => void;
}

const SessionContext = createContext<MobileSession | null>(null);

export function useMobileSession(): MobileSession {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useMobileSession outside MobileShell");
  return value;
}

const TABS = [
  { href: "/m/sky", label: "Sky", Icon: BubblesIcon },
  { href: "/m/split", label: "Split", Icon: PlusIcon },
  { href: "/m/forecast", label: "Forecast", Icon: CloudSunIcon },
  { href: "/m/feed", label: "Feed", Icon: PeopleIcon },
] as const;

/**
 * Phone frame for the signed-in mobile screens: a glass title bar on top, the
 * screen in the middle and a glossy Aero tab bar in thumb reach at the bottom.
 * Sends signed-out visitors to the mobile persona picker.
 */
export function MobileShell({ title, children }: { title: string; children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((session) => {
        if (cancelled) return;
        if (!session) router.replace("/m/login");
        else setMe(session);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timer);
  }, [toast]);

  const announce = useCallback((text: string) => setToast(text), []);

  async function signOut() {
    await api.logout();
    router.push("/m/login");
  }

  return (
    <div className="m-shell mx-auto flex min-h-dvh w-full max-w-[30rem] flex-col">
      <header className="m-topbar glass-navy sticky top-0 z-30 flex items-center gap-3 px-4 pt-[max(0.5rem,env(safe-area-inset-top))] pb-2">
        <ClearMark className="size-9 shrink-0" />
        <div className="min-w-0 flex-1">
          <h1 className="text-lg leading-tight font-bold break-words">{title}</h1>
          <p className="text-sm break-words text-sky-100">
            {me ? `${me.user.display_name} · ${me.household.name}` : "Clearday"}
          </p>
        </div>
        {me ? (
          <button
            type="button"
            onClick={() => void signOut()}
            className="m-press min-h-11 shrink-0 rounded-full bg-white/15 px-3 font-semibold text-white ring-1 ring-white/40"
          >
            Switch<span className="sr-only"> roommate</span>
          </button>
        ) : null}
      </header>

      <main id="main" className="flex-1 px-4 pt-4 pb-32">
        {failed ? (
          <p role="alert" className="glass rounded-3xl p-5 font-semibold">
            Couldn&rsquo;t reach Clearday. Check your connection and reload.
          </p>
        ) : me ? (
          <SessionContext.Provider value={{ me, announce }}>{children}</SessionContext.Provider>
        ) : (
          <p role="status" className="glass rounded-full px-5 py-3 font-semibold">
            Opening Clearday…
          </p>
        )}
      </main>

      <div
        role="status"
        aria-live="polite"
        className={`fixed inset-x-0 bottom-28 z-40 mx-auto w-fit max-w-[calc(100vw-2rem)] transition-opacity ${
          toast ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        {toast ? (
          <p className="glass rounded-3xl px-5 py-3 text-center font-bold text-navy-950">{toast}</p>
        ) : null}
      </div>

      <nav
        aria-label="Main"
        className="m-tabbar fixed inset-x-0 bottom-0 z-30 mx-auto max-w-[30rem] px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
      >
        <ul className="m-tabbar-glass grid grid-cols-4 gap-1 rounded-[1.75rem] p-1.5">
          {TABS.map(({ href, label, Icon }) => {
            const current = pathname === href;
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={current ? "page" : undefined}
                  className={`m-press m-tab flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-[1.35rem] px-1 text-sm font-bold ${
                    current ? "m-tab-current" : "text-navy-900"
                  }`}
                >
                  <Icon aria-hidden="true" className="size-6" />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
