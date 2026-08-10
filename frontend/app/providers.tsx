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
