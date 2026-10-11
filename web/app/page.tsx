"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";

/**
 * Sends the visitor to their sky if signed in, otherwise to the persona picker.
 * Phone-width viewports go to the mobile app at /m.
 */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((me) => {
        if (cancelled) return;
        const base = window.matchMedia("(max-width: 640px)").matches ? "/m" : "";
        router.replace(`${base}${me ? "/sky" : "/login"}`);
      })
      .catch(() => {
        if (!cancelled) router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <main id="main" className="grid min-h-dvh place-items-center p-4">
      <p className="glass rounded-full px-5 py-2 font-medium" role="status">
        Opening Clearday…
      </p>
    </main>
  );
}
