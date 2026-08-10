import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { AppSidebar } from "@/components/app-sidebar";
import {
  SidebarGutter,
  SidebarRevealTrigger,
} from "@/components/sidebar-reveal-trigger";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Maestro CS",
  description: "Tailor resumes to job descriptions",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: next-themes writes the resolved theme onto
    // <html> in a pre-paint script, so the server markup and the first client
    // render legitimately differ on this one element. Without it React logs a
    // hydration mismatch on every page load.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full font-sans">
        {/* First tab stop on every page. The sidebar is ~10 links repeated on
            every route, so a keyboard user without this pays for it on every
            navigation. Targets the id SidebarGutter puts on the main area. */}
        <a
          href="#main-content"
          className="bg-background focus-visible:ring-ring/50 sr-only rounded-md border px-3 py-2 text-sm font-medium shadow-sm focus-visible:fixed focus-visible:top-3 focus-visible:left-3 focus-visible:z-[60] focus-visible:not-sr-only focus-visible:ring-3"
        >
          Skip to content
        </a>
        <Providers>
          <SidebarProvider>
            <AppSidebar />
            <SidebarInset className="relative">
              <SidebarRevealTrigger />
              <SidebarGutter>{children}</SidebarGutter>
            </SidebarInset>
          </SidebarProvider>
        </Providers>
      </body>
    </html>
  );
}
