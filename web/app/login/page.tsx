"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ClearMark } from "@/components/icons";
import { api, USE_MOCKS, type DemoPersona } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [personas, setPersonas] = useState<DemoPersona[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  useEffect(() => {
    api
      .listDemoPersonas()
      .then(setPersonas)
      .catch(() => setError("Couldn't load the demo roommates. Try reloading."));
  }, []);

  async function signIn(persona: DemoPersona) {
    setPending(persona.user_id);
    setError(null);
    try {
      await api.loginAsPersona(persona.user_id);
      router.push("/sky");
    } catch {
      setError(`Couldn't sign in as ${persona.display_name}. Try again.`);
      setPending(null);
    }
  }

  return (
    <main
      id="main"
      className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col justify-center px-4 py-10"
    >
      <div className="glass aero-panel p-6 sm:p-10">
        <div className="flex items-center gap-3">
          <ClearMark className="size-12 shrink-0" />
          <p className="text-2xl font-bold tracking-tight text-navy-900">Clearday</p>
        </div>
        <h1 className="mt-6 text-3xl font-bold tracking-tight text-navy-950 sm:text-4xl">
          Who&rsquo;s checking the sky?
        </h1>
        <p className="mt-2 max-w-prose text-lg text-navy-800">
          Pick a roommate in Apartment 4B to see their bills float by.
        </p>

        {error ? (
          <p
            role="alert"
            className="mt-6 rounded-xl bg-alert-50 px-4 py-3 font-medium text-alert-700"
          >
            {error}
          </p>
        ) : null}

        <ul className="mt-8 grid gap-4 sm:grid-cols-3" aria-busy={personas === null}>
          {(personas ?? []).map((persona) => (
            <li key={persona.user_id}>
              <button
                type="button"
                onClick={() => void signIn(persona)}
                disabled={pending !== null}
                className="aero-tile group flex h-full w-full flex-row items-center gap-4 rounded-3xl p-4 text-left shadow-md transition hover:-translate-y-0.5 hover:shadow-lg disabled:opacity-70 sm:flex-col sm:text-center"
              >
                <span
                  aria-hidden="true"
                  className="bubble grid size-16 shrink-0 place-items-center text-2xl font-bold sm:size-20"
                >
                  <span className="bubble-content">{persona.display_name.slice(0, 1)}</span>
                </span>
                <span>
                  <span className="block text-xl font-bold text-navy-950">
                    {pending === persona.user_id
                      ? `Signing in as ${persona.display_name}…`
                      : persona.display_name}
                  </span>
                  <span className="mt-1 block text-navy-800">{persona.tagline}</span>
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
          <p className="mt-8 text-sm text-navy-800">
            Demo mode: sample data for a fictional household. No real money moves.
          </p>
        ) : null}
      </div>
    </main>
  );
}
