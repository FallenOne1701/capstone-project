import { redirect } from "next/navigation";

// The desk is one page now; old /ask links land on it.
export default function AskPage() {
  redirect("/");
}
