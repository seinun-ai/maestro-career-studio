/** The slice of a react-query result a load-failure check reads. */
export type LoadQuery = {
  data: unknown;
  isError: boolean;
  isFetching: boolean;
  /** How many times the query has failed; a refetch does not reset it. */
  errorUpdateCount: number;
};

/**
 * Whether a surface shows its failed-load state (`LoadErrorState`). Not `isError` alone: react-query refetches
 * a query that holds no data from "pending" (error null), so the moment Try again was pressed the error branch
 * fell through to the skeleton or the empty state and unmounted the focused button. A query that has failed
 * before and is fetching again with still no data is a failure being retried, not a first load.
 */
export function isLoadFailure(query: LoadQuery): boolean {
  return query.isError || (query.data === undefined && query.isFetching && query.errorUpdateCount > 0);
}
