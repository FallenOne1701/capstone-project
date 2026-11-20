import type { Metadata } from "next";
import { DeskTabs } from "@/components/desk/DeskTabs";
import { parseTab } from "@/lib/desk";

export const metadata: Metadata = {
  title: "Groww Support Desk",
  description: "Ask about HDFC mutual funds on Groww. Facts only, checked by AI agents, with the official source.",
};

export default async function Home({ searchParams }: { searchParams: Promise<{ t?: string | string[]; tab?: string | string[] }> }) {
  const { t, tab } = await searchParams;
  const code = Array.isArray(t) ? t[0] : t;
  return <DeskTabs initialTab={parseTab(tab)} initialCode={code ?? null} />;
}
