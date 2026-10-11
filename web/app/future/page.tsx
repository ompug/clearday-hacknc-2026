import type { Metadata } from "next";
import { FutureScreen } from "@/components/more/FutureScreen";

export const metadata: Metadata = { title: "Future view · Clearday" };

export default function FuturePage() {
  return <FutureScreen />;
}
