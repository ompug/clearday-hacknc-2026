"use client";

import { MotionConfig, useReducedMotion } from "framer-motion";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  PREFERENCES_STORAGE_KEY,
  TEXT_SIZES,
  THEME_OPTIONS,
  type TextSizeId,
  type ThemeModeId,
} from "./preference-options";

export { TEXT_SIZES, THEME_OPTIONS, type TextSizeId, type ThemeModeId } from "./preference-options";

export type ViewMode = "list" | "sky";

interface StoredPreferences {
  /** null = follow the operating system's prefers-reduced-motion. */
  reduceMotion: boolean | null;
  textSize: TextSizeId;
  theme: ThemeModeId;
  /** List is the default so screen-reader users land on it. */
  view: ViewMode;
}

const DEFAULTS: StoredPreferences = { reduceMotion: null, textSize: "default", theme: "none", view: "list" };
// The inline script in app/layout.tsx applies these before paint.
const STORAGE_KEY = PREFERENCES_STORAGE_KEY;

interface PreferencesValue extends StoredPreferences {
  /** Effective value: explicit choice, else the OS setting. */
  motionReduced: boolean;
  effectiveTheme: "light" | "dark";
  setReduceMotion(value: boolean): void;
  setTextSize(value: TextSizeId): void;
  setTheme(value: ThemeModeId): void;
  setView(value: ViewMode): void;
}

const PreferencesContext = createContext<PreferencesValue | null>(null);

function load(): StoredPreferences {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<StoredPreferences>;
    return {
      reduceMotion: typeof parsed.reduceMotion === "boolean" ? parsed.reduceMotion : null,
      textSize: TEXT_SIZES.some((s) => s.id === parsed.textSize)
        ? (parsed.textSize as TextSizeId)
        : DEFAULTS.textSize,
      theme: THEME_OPTIONS.some((t) => t.id === parsed.theme)
        ? (parsed.theme as ThemeModeId)
        : DEFAULTS.theme,
      view: parsed.view === "sky" ? "sky" : "list",
    };
  } catch {
    return DEFAULTS;
  }
}

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const [prefs, setPrefs] = useState<StoredPreferences>(DEFAULTS);
  const [loaded, setLoaded] = useState(false);
  const osReduced = useReducedMotion() ?? false;
  const [osDark, setOsDark] = useState(false);

  useEffect(() => {
    // Read storage after hydration so server and client markup match.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from localStorage
    setPrefs(load());
    setLoaded(true);
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setOsDark(mediaQuery.matches);
    update();
    mediaQuery.addEventListener("change", update);
    return () => mediaQuery.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!loaded) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Storage blocked: preferences last for this page only.
    }
  }, [prefs, loaded]);

  const motionReduced = prefs.reduceMotion ?? osReduced;
  const effectiveTheme = prefs.theme === "none" ? (osDark ? "dark" : "light") : prefs.theme;

  useEffect(() => {
    const root = document.documentElement;
    const size = TEXT_SIZES.find((s) => s.id === prefs.textSize) ?? TEXT_SIZES[0];
    root.style.fontSize = `${size.percent}%`;
    root.dataset.reduceMotion = motionReduced ? "true" : "false";
    root.dataset.theme = effectiveTheme;
    root.style.colorScheme = effectiveTheme;
  }, [prefs.textSize, motionReduced, effectiveTheme]);

  const setReduceMotion = useCallback(
    (value: boolean) => setPrefs((p) => ({ ...p, reduceMotion: value })),
    [],
  );
  const setTextSize = useCallback(
    (value: TextSizeId) => setPrefs((p) => ({ ...p, textSize: value })),
    [],
  );
  const setTheme = useCallback((value: ThemeModeId) => setPrefs((p) => ({ ...p, theme: value })), []);
  const setView = useCallback((value: ViewMode) => setPrefs((p) => ({ ...p, view: value })), []);

  const value = useMemo<PreferencesValue>(
    () => ({ ...prefs, motionReduced, effectiveTheme, setReduceMotion, setTextSize, setTheme, setView }),
    [prefs, motionReduced, effectiveTheme, setReduceMotion, setTextSize, setTheme, setView],
  );

  return (
    <PreferencesContext.Provider value={value}>
      <MotionConfig reducedMotion={motionReduced ? "always" : "never"}>{children}</MotionConfig>
    </PreferencesContext.Provider>
  );
}

export function usePreferences(): PreferencesValue {
  const value = useContext(PreferencesContext);
  if (!value) throw new Error("usePreferences must be used inside PreferencesProvider");
  return value;
}
