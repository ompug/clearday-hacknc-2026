"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type ReactNode } from "react";
import { api, type Me } from "@/lib/api";
import { AppHeader } from "../AppHeader";
import { ArrowLeftIcon } from "../icons";

/**
 * Shared frame for the secondary pages (analyst, recap, future, feed): signs the viewer in or sends them
 * to the login, shows the header and a way back, and gives the page one labelled h1.
 */
export function PageShell({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: string;
  children: (me: Me) => ReactNode;
}) {
  const router = useRouter();
  const titleId = useId();
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((session) => {
        if (cancelled) return;
        if (!session) router.replace("/login");
        else setMe(session);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function signOut() {
    await api.logout();
    router.push("/login");
  }

  return (
    <>
      <AppHeader me={me} onSignOut={() => void signOut()} />
      <main id="main" className="mx-auto w-full max-w-6xl px-4 pt-6 pb-16">
        <Link
          href="/sky"
          className="glass inline-flex min-h-11 items-center gap-2 rounded-full px-4 font-semibold text-navy-900"
        >
          <ArrowLeftIcon className="size-5" />
          Back to your bills
        </Link>
        <section aria-labelledby={titleId} className="glass mt-4 rounded-[1.75rem] p-5 sm:p-6">
          <h1 id={titleId} className="text-2xl font-bold text-navy-950 sm:text-3xl">
            {title}
          </h1>
          {intro ? <p className="mt-1 max-w-prose text-navy-800">{intro}</p> : null}
        </section>
        {failed ? (
          <p role="alert" className="glass mt-4 rounded-3xl p-6 text-lg font-semibold">
            Couldn&rsquo;t load this page. Check your connection and reload.
          </p>
        ) : me ? (
          children(me)
        ) : (
          <p role="status" className="mt-4 font-semibold">
            Loading…
          </p>
        )}
      </main>
    </>
  );
}
