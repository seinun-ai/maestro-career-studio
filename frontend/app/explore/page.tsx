import { redirect } from "next/navigation";

// Explore became Analytics (2026-07-17); keep old deep links working.
export default function ExplorePage() {
  redirect("/analytics");
}
