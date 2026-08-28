"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ConfirmDialogProvider } from "@/components/confirm-dialog";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            // Keep unobserved data 30 minutes instead of the 5-minute default.
            //
            // gcTime is the EVICTION timer, not the freshness one: five minutes
            // after the last component watching a query unmounts, the entry is
            // deleted outright. Returning to that page then renders an empty
            // skeleton and refetches from nothing — which is why a section
            // visited a few minutes ago feels cold again.
            //
            // The 5-minute default assumes a multi-user app where data changes
            // behind you. This one is single-user and local: you are the only
            // writer, the API answers in well under 200ms, and the whole working
            // set is a few hundred rows, so holding it costs almost nothing.
            //
            // staleTime stays at 30s deliberately. Freshness and eviction are
            // separate concerns — cached data is still refetched in the
            // background on remount, so this trades memory for a warm return,
            // never staleness for it.
            gcTime: 30 * 60_000,
            refetchOnWindowFocus: false,
            // Never PAUSE a request for being "offline" — fail it instead.
            //
            // react-query's default `networkMode: "online"` parks a query in
            // `fetchStatus: "paused"` / `status: "pending"` when it believes
            // the browser is offline. It never becomes `error`, so `isError`
            // stays false and every surface renders its pending state — a
            // skeleton, or worse a confirmed-empty list — indefinitely.
            //
            // That default assumes a remote API. "Offline" is not a meaningful
            // state here: the API is FastAPI on this same machine, so
            // `navigator.onLine` says nothing about whether it is listening,
            // and a laptop with the wifi off can still use every page. The only
            // useful question is "did the request succeed", and `always` is the
            // mode that asks exactly it.
            //
            // Demonstrated, not theorised. With `navigator.onLine` forced
            // false and an `offline` event dispatched — exactly what pulling
            // the wifi does — two identical queries against `/api/version`:
            // `networkMode: "online"` parked at pending/paused and never ran;
            // `networkMode: "always"` succeeded. The API was listening the
            // whole time. So the default would freeze every page on skeletons
            // for a user working offline on a laptop, which this app otherwise
            // fully supports.
            //
            // It does NOT address react-query pausing RETRIES while the window
            // is unfocused — separate, deliberate upstream behaviour that
            // `always` does not bypass, and not a bug: with a focused window a
            // failed fetch surfaces the error state normally (verified against
            // a stopped backend in a real browser).
            //
            // Pinned by backend/tests/test_frontend_query_error_states.py.
            networkMode: "always",
          },
          mutations: {
            // Same reasoning: a paused mutation reports neither success nor
            // failure, so a Save button spins forever instead of toasting.
            networkMode: "always",
          },
        },
      }),
  );

  return (
    // The dark palette existed from the start — every token has a `.dark`
    // counterpart and the six chart steps were separately validated for the
    // dark surface — but nothing ever mounted a provider, so nothing set the
    // `.dark` class and no user could reach any of it. `sonner.tsx` was already
    // calling useTheme() into the void. attribute="class" matches the
    // `@custom-variant dark (&:is(.dark *))` in globals.css; defaultTheme
    // "system" means a fresh profile still follows the OS.
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <QueryClientProvider client={client}>
        <TooltipProvider delay={350}>
          <ConfirmDialogProvider>
            {children}
            <Toaster richColors closeButton position="bottom-right" offset={16} duration={3500} />
          </ConfirmDialogProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
