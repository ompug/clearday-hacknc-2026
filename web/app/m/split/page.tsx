import type { Metadata } from "next";
import { MobileSplit } from "@/components/mobile/MobileSplit";
import { MobileShell } from "@/components/mobile/MobileShell";

export const metadata: Metadata = { title: "Split a bill · Clearday" };

export default function MobileSplitPage() {
  return (
    <MobileShell title="Split a bill">
      <MobileSplit />
    </MobileShell>
  );
}
