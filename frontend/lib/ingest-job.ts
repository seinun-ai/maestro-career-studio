import { apiFetch } from "@/lib/api";
import type { Job, JobCreate } from "@/lib/types";

export async function ingestJob(payload: JobCreate): Promise<Job> {
  return apiFetch<Job>("/api/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
