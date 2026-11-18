import { redirect } from "next/navigation";

// Old ticket links open the ticket on the main page.
export default async function TicketPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  redirect(`/?t=${encodeURIComponent(code)}`);
}
