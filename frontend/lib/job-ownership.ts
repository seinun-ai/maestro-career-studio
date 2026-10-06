import type { JobOwnership, SyncQueued } from "./types";

export function jobOwnershipView(ownership?: JobOwnership) {
  if (!ownership) return { mark: null, action: null, canWrite: false, canRequest: false,
    reason: "Check where this job is being worked on before making changes.", pending: false };
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
  if (ownership.handover === "offered") return ownership.owner === "laptop" ? "keep-here" : null;
  return !ownership.owned_here && ownership.owner === "bot" ? "work-here" : null;
}

function ownershipReason(ownership?: JobOwnership): string {
  if (ownership?.handover === "offered") {
    return "This job is on its way to your bot. Use Keep it here to keep working on it.";
  }
  if (ownership?.handover === "returning") {
    return "This job is going back to your laptop. Make the change there after the next sync.";
  }
  return ownership?.owner === "bot"
    ? "This job is with your bot. Ask for it back with Work on it here."
    : "This job is on your laptop. Work on it there.";
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
