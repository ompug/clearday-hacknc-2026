import type { Metadata } from "next";
import { RecapScreen } from "@/components/more/RecapScreen";

export const metadata: Metadata = { title: "Weekly recap · Clearday" };

export default function RecapPage() {
  return <RecapScreen />;
}
