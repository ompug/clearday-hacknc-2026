import type { Metadata } from "next";
import "./mobile.css";

export const metadata: Metadata = { title: "Clearday mobile" };

export default function MobileLayout({ children }: { children: React.ReactNode }) {
  return <div data-mobile="">{children}</div>;
}
