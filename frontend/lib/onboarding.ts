/** Whether an async proposal may replace the editor value it was requested for. */
export function canApplyAsyncDraft(
  requestRevision: number,
  currentRevision: number,
): boolean {
  return requestRevision === currentRevision;
}

/** The queue is the latest requested value, or empty when it matches in-flight. */
export function nextQueuedSave(
  submittedValue: string | null,
  requestedValue: string,
): string | null {
  return requestedValue === submittedValue ? null : requestedValue;
}
