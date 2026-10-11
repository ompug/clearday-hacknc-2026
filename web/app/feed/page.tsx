import type { Metadata } from "next";
import { FeedScreen } from "@/components/more/FeedScreen";

export const metadata: Metadata = { title: "Household feed · Clearday" };

export default function FeedPage() {
  return <FeedScreen />;
}
