/** Plain constants shared by the server layout's pre-paint script and PreferencesProvider. */

/** Root font-size scales. All layout is in rem, so this scales the whole UI. */
export const TEXT_SIZES = [
  { id: "default", label: "Default", percent: 100 },
  { id: "large", label: "Large", percent: 118.75 },
  { id: "larger", label: "Larger", percent: 137.5 },
  { id: "largest", label: "Largest", percent: 162.5 },
] as const;

export type TextSizeId = (typeof TEXT_SIZES)[number]["id"];

export const PREFERENCES_STORAGE_KEY = "clearday.preferences";
