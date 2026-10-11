"use client";

import { useEffect, useRef, useState } from "react";
import { api, type RecapResponse } from "@/lib/api";
import { PauseIcon, PlayIcon } from "../icons";
import { PageShell } from "./PageShell";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const HOST = { A: "Host one", B: "Host two" } as const;

/** The week's recap: transcript always on screen, audio optional. Household counts only, no amounts. */
function Recap() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [recap, setRecap] = useState<RecapResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    api
      .getRecap()
      .then(setRecap)
      .catch(() => setFailed(true));
  }, []);

  if (failed)
    return (
      <p role="alert" className="glass mt-4 rounded-3xl p-6 font-semibold">
        Couldn&rsquo;t load the recap.
      </p>
    );
  if (!recap) return <p role="status">Loading the recap…</p>;
  const url = recap.audio_url ? `${BASE_URL}${recap.audio_url}` : null;

  function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void audio.play().catch(() => setPlaying(false));
    else audio.pause();
  }

  return (
    <section aria-labelledby="recap-h" className="glass mt-4 aero-panel p-5 sm:p-6">
      <h2 id="recap-h" className="text-xl font-bold text-navy-950">
        Week of {recap.week_start}
      </h2>
      {url ? (
        <>
          {/* The transcript below is the caption: it is always shown next to the player. */}
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <audio
            ref={audioRef}
            src={url}
            preload="none"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
          />
          <button
            type="button"
            onClick={toggle}
            className="aero-btn mt-3 min-h-11 gap-2 rounded-full px-5"
          >
            {playing ? <PauseIcon className="size-5" /> : <PlayIcon className="size-5" />}
            {playing ? "Pause recap" : "Play recap"}
          </button>
        </>
      ) : (
        <p className="mt-2 text-sm font-semibold text-navy-800">
          Audio isn&rsquo;t available right now. Here is the transcript.
        </p>
      )}
      <h3 className="mt-4 font-bold text-navy-950">Transcript</h3>
      <ol aria-label="Transcript" className="mt-2 flex flex-col gap-2">
        {recap.lines.map((line, i) => (
          <li key={i} className="aero-tile rounded-2xl px-4 py-3">
            <span className="font-bold text-navy-950">{HOST[line.speaker]}: </span>
            <span className="text-navy-900">{line.text}</span>
          </li>
        ))}
      </ol>
      <p className="mt-3 max-w-prose text-sm text-navy-800">
        Built from your household&rsquo;s counts only: no amounts, names or outside news.
      </p>
    </section>
  );
}

export function RecapScreen() {
  return (
    <PageShell title="Weekly recap" intro="Sixty seconds on how your household did this week.">
      {() => <Recap />}
    </PageShell>
  );
}
