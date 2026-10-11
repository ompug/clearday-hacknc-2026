import type { Metadata } from "next";
import { ForecastScreen } from "@/components/forecast/ForecastScreen";

export const metadata: Metadata = { title: "Money weather · Clearday" };

export default function ForecastPage() {
  return <ForecastScreen />;
}
