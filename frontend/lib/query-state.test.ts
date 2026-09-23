import assert from "node:assert/strict";
import { test } from "node:test";

import { unloadedLayer } from "./formatting.ts";
import { isLoadFailure, type LoadQuery } from "./query-state.ts";

const firstLoad: LoadQuery = {
  data: undefined,
  isError: false,
  isFetching: true,
  errorUpdateCount: 0,
};
const failed: LoadQuery = {
  data: undefined,
  isError: true,
  isFetching: false,
  errorUpdateCount: 1,
};
const retrying: LoadQuery = {
  data: undefined,
  isError: false,
  isFetching: true,
  errorUpdateCount: 1,
};
const heldRefetch: LoadQuery = {
  data: { ok: true },
  isError: false,
  isFetching: true,
  errorUpdateCount: 1,
};
const heldFailedRefetch: LoadQuery = {
  data: { ok: true },
  isError: true,
  isFetching: false,
  errorUpdateCount: 2,
};

test("a first load is not a load failure", () => {
  assert.equal(isLoadFailure(firstLoad), false);
});

test("a failed load is a load failure", () => {
  assert.equal(isLoadFailure(failed), true);
});

test("a retry of a failed load stays a load failure", () => {
  // react-query clears isError while a data-less refetch is in flight.
  assert.equal(isLoadFailure(retrying), true);
});

test("data already held is not a load failure while it refetches", () => {
  assert.equal(isLoadFailure(heldRefetch), false);
});

test("a failed background refetch over held data is still a load failure", () => {
  assert.equal(isLoadFailure(heldFailedRefetch), true);
});

test("unloadedLayer and isLoadFailure agree when the layer has no data", () => {
  // unloadedLayer is only asked with no data, and a lib file cannot value-import
  // another, so the two copies of the retry rule are pinned together here.
  for (const query of [firstLoad, failed, retrying, heldRefetch, heldFailedRefetch]) {
    const layer = unloadedLayer(
      { isError: query.isError, isFetching: query.isFetching, errorUpdateCount: query.errorUpdateCount, refetch: () => {} },
      "x",
    );
    assert.equal(layer.status === "error", isLoadFailure({ ...query, data: undefined }));
  }
});
