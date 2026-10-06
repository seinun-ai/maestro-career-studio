import type { JobOwnership, SyncQueued } from "./types";

/** No ownership on a row means sync is off (or an older server): owned here, unmarked, nothing locked. */
export function jobOwnershipView(ownership?: JobOwnership) {
  if (!ownership) return { mark: null, action: null, canWrite: true, canRequest: true,
    reason: null, pending: false };
  const canWrite = ownership.owned_here;
  const owner = ownership.owner;
  const moving = ["offered", "returning"].includes(ownership.handover ?? "");
  return { mark: owner ? ownershipMark(ownership) : null, action: ownershipAction(ownership),
    canWrite, canRequest: canWrite || !moving,
    reason: canWrite ? null : ownershipReason(ownership),
    pending: ownership.pending_requests > 0 };
}

function ownershipMark(ownership?: JobOwnership): string {
  if (ownership?.handover === "offered") return "Going to your bot";
  return ownership?.owner === "bot" ? "With your bot" : "On your laptop";
}

function ownershipAction(ownership?: JobOwnership): "keep-here" | "work-here" | null {
  if (!ownership || ownership.handover === "returning") return null;
  if (ownership.handover === "offered") return ownership.can_keep_here ? "keep-here" : null;
  return !ownership.owned_here && ownership.owner === "bot" ? "work-here" : null;
}

function ownershipReason(ownership?: JobOwnership): string {
  if (ownership?.handover === "offered" && ownership.can_keep_here) {
    return "This job is on its way to your bot. Use Keep it here to keep working on it.";
  }
  if (ownership?.handover === "returning") {
    return "This job is going back to your laptop. Make the change there after the next sync.";
  }
  return ownership?.owner === "bot"
    ? "This job is with your bot; ask for it back with Work on it here."
    : "This job is on your laptop; work on it there.";
}

// The server refuses a write to a job on the other copy with one of four fixed sentences, each
// opening with where the job is.
const OWNERSHIP_REFUSAL =
  /^This job is (with your bot|on your laptop|on its way to your bot|going back to your laptop)\b/;

/** True when a refused write's message is the server's "this job is on the other copy" sentence. */
export function isOwnershipRefusal(message: string | null | undefined): boolean {
  return !!message && OWNERSHIP_REFUSAL.test(message);
}

export function isSyncQueued(value: unknown): value is SyncQueued {
  return value !== null && typeof value === "object" && "queued" in value && value.queued === true;
}

export function syncActionMessage(value: unknown, savedMessage: string): string {
  return isSyncQueued(value) ? "Sent at the next sync" : savedMessage;
}

export function ownershipControlProps(locked: boolean, attribute: "disabled" | "readOnly" = "disabled"):
  { disabled?: boolean; readOnly?: boolean } {
  return locked ? { [attribute]: true } : {};
}
