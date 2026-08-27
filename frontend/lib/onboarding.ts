/** Whether an async proposal may replace the editor value it was requested for. */
export function canApplyAsyncDraft(
  requestRevision: number,
  currentRevision: number,
): boolean {
  return requestRevision === currentRevision;
}
