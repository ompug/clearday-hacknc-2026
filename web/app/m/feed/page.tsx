import type { Metadata } from "next";
import { MobileFeed } from "@/components/mobile/MobileFeed";
import { MobileShell } from "@/components/mobile/MobileShell";

export const metadata: Metadata = { title: "Household feed · Clearday" };

export default function MobileFeedPage() {
  return (
    <MobileShell title="Household feed">
      <MobileFeed />
    </MobileShell>
  );
}
