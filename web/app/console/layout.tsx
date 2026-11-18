import type { Metadata } from "next";
import { ConsoleGate } from "@/components/console/ConsoleGate";

export const metadata: Metadata = { title: "Console · Groww Support Desk", robots: { index: false } };

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return <ConsoleGate>{children}</ConsoleGate>;
}
