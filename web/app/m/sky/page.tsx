import type { Metadata } from "next";
import { MobileSky } from "@/components/mobile/MobileSky";
import { MobileShell } from "@/components/mobile/MobileShell";

export const metadata: Metadata = { title: "Your sky · Clearday" };

export default function MobileSkyPage() {
  return (
    <MobileShell title="Your sky">
      <MobileSky />
    </MobileShell>
  );
}
