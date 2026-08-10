import { Suspense } from "react";

import { ChatPage } from "@/components/chat/chat-page";

export const metadata = { title: "Chat — Maestro CS" };

// useSearchParams() requires a Suspense boundary for the static prerender in
// `next build` (Next.js 16 CSR bailout).
export default function Page() {
  return (
    <Suspense fallback={null}>
      <ChatPage />
    </Suspense>
  );
}
