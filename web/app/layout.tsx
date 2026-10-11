import type { Metadata, Viewport } from "next";
import { AeroBackdrop } from "@/components/aero";
import { PREFERENCES_STORAGE_KEY, TEXT_SIZES } from "@/lib/preference-options";
import { PreferencesProvider } from "@/lib/preferences";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clearday",
  description: "Shared bills for roommates, as bubbles you pop when they're paid.",
};

export const viewport: Viewport = {
  themeColor: "#0a2a4f",
  width: "device-width",
  initialScale: 1,
};

// Applies the saved text size and motion preference before first paint so the
// page doesn't jump. Mirrors the logic in PreferencesProvider.
const preferencesScript = `(() => {
  try {
    var sizes = ${JSON.stringify(Object.fromEntries(TEXT_SIZES.map((s) => [s.id, s.percent])))};
    var p = JSON.parse(localStorage.getItem(${JSON.stringify(PREFERENCES_STORAGE_KEY)}) || "{}");
    var root = document.documentElement;
    if (sizes[p.textSize]) root.style.fontSize = sizes[p.textSize] + "%";
    var reduce = typeof p.reduceMotion === "boolean"
      ? p.reduceMotion
      : window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    root.dataset.reduceMotion = reduce ? "true" : "false";
  } catch (e) {}
})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: preferencesScript }} />
      </head>
      <body className="antialiased">
        <AeroBackdrop />
        <a
          href="#main"
          className="sr-only z-50 rounded-full bg-white px-4 py-2 font-semibold text-navy-900 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
        >
          Skip to main content
        </a>
        <PreferencesProvider>{children}</PreferencesProvider>
      </body>
    </html>
  );
}
