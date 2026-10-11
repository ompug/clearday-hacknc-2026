"use client";

import { useEffect, useRef, useState } from "react";
import type { AnnouncementResponse } from "@/lib/api";
import { CloseIcon, PauseIcon, PlayIcon } from "../icons";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

/**
 * The household's spoken announcement. The transcript is always on screen (audio never stands alone).
 * Browsers may block autoplay, so the Play button is the reliable way to hear it. No motion here, so
 * reduced-motion needs nothing extra.
 */
export function VoiceAnnouncement({
  announcement,
  onDismiss,
}: {
  announcement: AnnouncementResponse;
  onDismiss: () => void;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const url = announcement.audio_url ? `${BASE_URL}${announcement.audio_url}` : null;

  useEffect(() => {
    // Best effort; a blocked autoplay just leaves the Play button.
    audioRef.current?.play().catch(() => undefined);
  }, [url]);

  function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void audio.play().catch(() => setPlaying(false));
    else audio.pause();
  }

  return (
    <section
      aria-labelledby="voice-heading"
      className="glass mt-4 flex flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl px-4 py-3"
    >
      <h2 id="voice-heading" className="sr-only">
        Clearday Home announcement
      </h2>
      {url ? (
        <>
          {/* The transcript below is the caption: it is always shown next to the player. */}
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <audio
            ref={audioRef}
            src={url}
            preload="auto"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
          />
          <button
            type="button"
            onClick={toggle}
            aria-label={playing ? "Pause announcement" : "Play announcement"}
            className="inline-flex min-h-11 items-center gap-2 rounded-full bg-navy-900 px-5 font-bold text-white hover:bg-navy-800"
          >
            {playing ? <PauseIcon className="size-5" /> : <PlayIcon className="size-5" />}
            {playing ? "Pause" : "Play announcement"}
          </button>
        </>
      ) : (
        <span className="rounded-full bg-white px-3 py-1 text-sm font-semibold text-navy-900">
          Text only (voice unavailable)
        </span>
      )}
      <p className="min-w-0 flex-1 basis-64 font-semibold text-navy-950">
        <span className="font-bold">Transcript: </span>
        {announcement.text}
      </p>
      <button
        type="button"
        onClick={onDismiss}
        className="inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-4 font-semibold text-navy-900 ring-2 ring-navy-900/25 hover:bg-sky-50"
      >
        <CloseIcon className="size-5" />
        Dismiss
      </button>
    </section>
  );
}
