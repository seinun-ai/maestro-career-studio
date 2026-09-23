/** The slice of a react-query result a load-failure check reads. */
export type LoadQuery = {
  data: unknown;
  isError: boolean;
  /** "paused" is a fetch too: a retry waits there while the tab is hidden. */
  fetchStatus: "fetching" | "paused" | "idle";
  /** How many times the query has failed; a refetch does not reset it. */
  errorUpdateCount: number;
};

/**
 * Whether a surface shows its failed-load state (`LoadErrorState`) instead of its content.
 *
 * Only a query with NO data is a load failure. A background refetch that fails over data already on
 * screen leaves that data showing: swapping a loaded editor for the error lost the text typed since
 * its last save (owner rule: never lose typed text).
 *
 * Not `isError` alone: react-query refetches a query that holds no data from "pending" (error null),
 * so the moment Try again was pressed the error branch fell through to the skeleton or the empty
 * state and unmounted the focused button. A query that has failed before and is fetching again with
 * still no data is a failure being retried, not a first load, and so is one whose retry is paused
 * (`fetchStatus: "paused"`, `isFetching` false) while the tab is hidden.
 */
export function isLoadFailure(query: LoadQuery): boolean {
  return (
    query.data === undefined &&
    (query.isError || (query.fetchStatus !== "idle" && query.errorUpdateCount > 0))
  );
}
