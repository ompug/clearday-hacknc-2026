import type { Metadata } from "next";
import { SkyScreen } from "@/components/sky/SkyScreen";

export const metadata: Metadata = { title: "Your sky · Clearday" };

export default function SkyPage() {
  return <SkyScreen />;
}
