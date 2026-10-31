// The answers for job forms refetch when you come back to the tab, even a moment after a read. pytest runs it:
// backend/tests/test_frontend_profile_tiles.py.
//
// The Companion's pause row learns answers into this profile in another window. Profile and Setup save the WHOLE
// profile, so an open page that never reads again sends its old copy on the next edit and erases what was learned.
import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";

import { load } from "../render-harness.mjs";

const require = createRequire(import.meta.url);
const { MutationObserver, QueryClient, QueryObserver, focusManager } = require("@tanstack/react-query");

const { autofillQuery } = load("components/profile/use-autofill-query.ts");
const { saveAnswersMutation } = load("components/profile/autofill-profile.tsx");

const SERVED = { key: "autofill_profile", value: { personal: { phone: "" } } };
const LEARNED = {
  key: "autofill_profile",
  value: {
    personal: { phone: "" },
    work_auth_by_country: { UK: { sponsorship_now: "Yes" } },
    custom: [{ question: "Preferred shift", answer: "Day" }],
  },
};

// The app's defaults (app/providers.tsx): a read is fresh for 30 s, and focus refetches nothing on its own.
const appClient = () =>
  new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: false } } });

/** Watch the query as a mounted page does, with a read just made, then leave the tab and come back. */
async function focusAfterAFreshRead(options) {
  const client = appClient();
  client.mount();
  client.setQueryData(options.queryKey, SERVED);
  let reads = 0;
  const observer = new QueryObserver(client, {
    ...options,
    queryFn: async () => {
      reads += 1;
      return LEARNED;
    },
  });
  const stop = observer.subscribe(() => {});
  focusManager.setFocused(false);
  focusManager.setFocused(true);
  await new Promise((resolve) => setTimeout(resolve, 0));
  const data = client.getQueryData(options.queryKey);
  stop();
  client.unmount();
  client.clear();
  focusManager.setFocused(undefined);
  return { reads, data };
}

test("coming back to the tab reads the answers again, though the last read is seconds old", async () => {
  const { reads, data } = await focusAfterAFreshRead(autofillQuery);
  assert.equal(reads, 1);
  assert.deepEqual(data, LEARNED);
});

test("the app's defaults alone would keep the old copy: the override is what reads again", async () => {
  const { queryKey, queryFn } = autofillQuery;
  const { reads, data } = await focusAfterAFreshRead({ queryKey, queryFn });
  assert.equal(reads, 0);
  assert.deepEqual(data, SERVED);
});

test("the key is the one every reader and writer of the answers uses", () => {
  assert.deepEqual(autofillQuery.queryKey, ["settings", "autofill"]);
});

/** A focus read starts, then a save lands before it returns: what the cache holds once both are done. */
async function readThenSave(options = {}) {
  const client = appClient();
  client.mount();
  client.setQueryData(autofillQuery.queryKey, SERVED);
  let release = () => {};
  const read = client.fetchQuery({
    ...autofillQuery,
    staleTime: 0,
    queryFn: () => new Promise((resolve) => (release = () => resolve(SERVED))),
  });
  const saved = { key: "autofill_profile", value: { personal: { phone: "+44 20 0000 0000" } } };
  const save = new MutationObserver(client, { ...saveAnswersMutation(client), ...options, mutationFn: async () => saved });
  await save.mutate(saved.value);
  release();
  await read.catch(() => {});
  const data = client.getQueryData(autofillQuery.queryKey);
  client.unmount();
  client.clear();
  return { data, saved };
}

test("a save cancels a read of the answers still on its way, so the copy from before it never lands after it", async () => {
  const { data, saved } = await readThenSave();
  assert.deepEqual(data, saved);
});

test("without the cancel, the read from before the save lands last and would be sent back", async () => {
  const { data } = await readThenSave({ onMutate: undefined });
  assert.deepEqual(data, SERVED);
});
