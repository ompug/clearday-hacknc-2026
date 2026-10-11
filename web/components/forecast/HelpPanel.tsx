"use client";

import { useEffect, useId, useState } from "react";
import { api, type HelpPanelResponse } from "@/lib/api";

/**
 * Private, opt-in help. Renders nothing unless the server says one of this user's own triggers fired,
 * then offers a button; the links appear only after the user chooses to see them. Never realtime,
 * never in the feed. The disclaimer is on screen in both states.
 */
export function HelpPanel() {
  const uid = useId();
  const [panel, setPanel] = useState<HelpPanelResponse | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api
      .getHelpPanel()
      .then(setPanel)
      .catch(() => setPanel(null));
  }, []);

  if (!panel?.triggered) return null;

  return (
    <section aria-labelledby={`${uid}-h`} className="glass mt-6 aero-panel p-5 sm:p-6">
      <h2 id={`${uid}-h`} className="text-xl font-bold text-navy-950">
        Need a hand? Free help is available
      </h2>
      <p className="mt-1 max-w-prose text-navy-800">
        {panel.reasons.join(" ")} {panel.private_note}
      </p>
      {open ? (
        <ul className="mt-3 flex flex-col gap-2">
          {panel.resources.map((r) => (
            <li key={r.url} className="aero-tile rounded-2xl px-4 py-3">
              <a
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-bold text-navy-950 underline underline-offset-4"
              >
                {r.name}
                <span className="sr-only"> (opens the official site in a new tab)</span>
              </a>
              <p className="text-sm text-navy-800">{r.help}</p>
            </li>
          ))}
        </ul>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="aero-btn mt-3 min-h-11 rounded-full px-5"
        >
          Show help options
        </button>
      )}
      <p className="mt-3 text-sm font-semibold text-navy-900">{panel.disclaimer}</p>
      <p className="text-sm text-navy-800">
        Check each site for current details and whether you qualify.
      </p>
    </section>
  );
}
