import type { Metadata } from "next";
import { AnalystScreen } from "@/components/more/AnalystScreen";

export const metadata: Metadata = { title: "Analyst view · Clearday" };

export default function AnalystPage() {
  return <AnalystScreen />;
}
