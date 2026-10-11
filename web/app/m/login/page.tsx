import type { Metadata } from "next";
import { MobileLogin } from "@/components/mobile/MobileLogin";

export const metadata: Metadata = { title: "Sign in · Clearday" };

export default function MobileLoginPage() {
  return <MobileLogin />;
}
