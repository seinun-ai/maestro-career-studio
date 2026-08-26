"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { VersionInfo } from "@/lib/types";

export function useVersion() {
  return useQuery({
    queryKey: ["version"],
    queryFn: () => apiFetch<VersionInfo>("/api/version"),
    // The running version cannot change without a page reload.
    staleTime: Infinity,
  });
}
