"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, USE_MOCKS, type DemoPersona } from "@/lib/api";
import { ClearMark } from "../icons";

/** Mobile persona picker: the same demo login as the desktop, big thumb targets. */
export function MobileLogin() {
  const router = useRouter();
  const [personas, setPersonas] = useState<DemoPersona[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  useEffect(() => {
    api
      .listDemoPersonas()
      .then(setPersonas)
      .catch(() =>
        setError(
          "Couldn't load the demo roommates. Persona login only works on the laptop itself.",
        ),
      );
  }, []);

  async function signIn(persona: DemoPersona) {
    setPending(persona.user_id);
    setError(null);
    try {
      await api.loginAsPersona(persona.user_id);
      router.push("/m/sky");
    } catch {
      setError(`Couldn't sign in as ${persona.display_name}. Try again.`);
      setPending(null);
    }
  }

  return (
    <main id="main" className="mx-auto flex min-h-dvh w-full max-w-[30rem] flex-col px-4 py-8">
      <div className="glass-navy flex items-center gap-3 rounded-[1.75rem] px-5 py-4">
        <ClearMark className="size-11 shrink-0" />
        <p className="text-2xl font-bold tracking-tight">Clearday</p>
      </div>
      <div className="glass mt-4 rounded-[1.75rem] p-5">
        <h1 className="text-3xl font-bold tracking-tight text-navy-950">
          Who&rsquo;s checking the sky?
        </h1>
        <p className="mt-2 text-lg text-navy-800">Pick a roommate in the household.</p>

        {error ? (
          <p
            role="alert"
            className="mt-4 rounded-xl bg-alert-50 px-4 py-3 font-medium text-alert-700"
          >
            {error}
          </p>
        ) : null}

        <ul className="mt-5 flex flex-col gap-3" aria-busy={personas === null}>
          {(personas ?? []).map((persona) => (
            <li key={persona.user_id}>
              <button
                type="button"
                onClick={() => void signIn(persona)}
                disabled={pending !== null}
                className="m-press flex min-h-20 w-full items-center gap-4 rounded-3xl border border-white bg-white/80 p-3 text-left shadow-md disabled:opacity-70"
              >
                <span
                  aria-hidden="true"
                  className="bubble grid size-14 shrink-0 place-items-center text-2xl font-bold"
                >
                  <span className="bubble-content">{persona.display_name.slice(0, 1)}</span>
                </span>
                <span className="min-w-0">
                  <span className="block text-xl font-bold text-navy-950">
                    {pending === persona.user_id
                      ? `Signing in as ${persona.display_name}…`
                      : persona.display_name}
                  </span>
                  <span className="block text-navy-800">{persona.tagline}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        {personas === null && !error ? (
          <p role="status" className="mt-4 text-navy-800">
            Loading roommates…
          </p>
        ) : null}
        {USE_MOCKS ? (
          <p className="mt-6 text-sm text-navy-800">
            Demo mode: sample data for a fictional household. No real money moves.
          </p>
        ) : null}
      </div>
    </main>
  );
}
