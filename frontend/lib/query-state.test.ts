import assert from "node:assert/strict";
import { test } from "node:test";

import { unloadedLayer } from "./formatting.ts";
import { isLoadFailure, type LoadQuery } from "./query-state.ts";

const firstLoad: LoadQuery = {
  data: undefined,
  isError: false,
  fetchStatus: "fetching",
  errorUpdateCount: 0,
};
const failed: LoadQuery = {
  data: undefined,
  isError: true,
  fetchStatus: "idle",
  errorUpdateCount: 1,
};
const retrying: LoadQuery = {
  data: undefined,
  isError: false,
  fetchStatus: "fetching",
  errorUpdateCount: 1,
};
// A retry waiting for the tab to be visible again: `isFetching` is false here.
const retryPaused: LoadQuery = { ...retrying, fetchStatus: "paused" };
const firstLoadPaused: LoadQuery = { ...firstLoad, fetchStatus: "paused" };
const heldRefetch: LoadQuery = {
  data: { ok: true },
  isError: false,
  fetchStatus: "fetching",
  errorUpdateCount: 1,
};
const heldFailedRefetch: LoadQuery = {
  data: { ok: true },
  isError: true,
  fetchStatus: "idle",
  errorUpdateCount: 2,
};

const ALL = [firstLoad, failed, retrying, retryPaused, firstLoadPaused, heldRefetch, heldFailedRefetch];

test("a first load is not a load failure, fetching or paused", () => {
  assert.equal(isLoadFailure(firstLoad), false);
  assert.equal(isLoadFailure(firstLoadPaused), false);
});

test("a failed load is a load failure", () => {
  assert.equal(isLoadFailure(failed), true);
});

test("a retry of a failed load stays a load failure", () => {
  // react-query clears isError while a data-less refetch is in flight.
  assert.equal(isLoadFailure(retrying), true);
});

test("a retry paused while the tab is hidden stays a load failure", () => {
  // fetchStatus "paused" reads isFetching false; the empty state must not show.
  assert.equal(isLoadFailure(retryPaused), true);
});

test("data already held is not a load failure while it refetches", () => {
  assert.equal(isLoadFailure(heldRefetch), false);
});

test("a failed background refetch keeps the data it already holds on screen", () => {
  // Owner rule: never lose typed text. The loaded editor stays, not the error.
  assert.equal(isLoadFailure(heldFailedRefetch), false);
});

test("unloadedLayer and isLoadFailure agree when the layer has no data", () => {
  // unloadedLayer is only asked with no data, and a lib file cannot value-import
  // another, so the two copies of the retry rule are pinned together here.
  for (const query of ALL) {
    const layer = unloadedLayer(
      {
        isError: query.isError,
        isFetching: query.fetchStatus === "fetching",
        fetchStatus: query.fetchStatus,
        errorUpdateCount: query.errorUpdateCount,
        refetch: () => {},
      },
      "x",
    );
    assert.equal(layer.status === "error", isLoadFailure({ ...query, data: undefined }), JSON.stringify(query));
  }
});
