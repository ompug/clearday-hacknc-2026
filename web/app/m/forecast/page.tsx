import type { Metadata } from "next";
import { MobileForecast } from "@/components/mobile/MobileForecast";
import { MobileShell } from "@/components/mobile/MobileShell";

export const metadata: Metadata = { title: "Money weather · Clearday" };

export default function MobileForecastPage() {
  return (
    <MobileShell title="Money weather">
      <MobileForecast />
    </MobileShell>
  );
}
