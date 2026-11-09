import assert from "node:assert/strict";
import test from "node:test";
import { clearSearch, hasAnyFilter, loadSearch, saveSearch } from "../../../src/features/search/searchSession.ts";

test("search session saves, restores, and clears query filters", () => {
  const entries = new Map();
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    value: {
      getItem: (key) => entries.get(key) ?? null,
      setItem: (key, value) => entries.set(key, value),
      removeItem: (key) => entries.delete(key),
    },
  });
  const saved = {
    query: "frontend engineer",
    filters: {
      roles: [],
      skills: ["React"],
      seniority: ["mid"],
      locations: [{ place_id: "place-1", label: "Seattle", city: "Seattle", state: "Washington", country: "USA" }],
      companies: [],
      domains: [],
      minExperience: 3,
      maxExperience: 7,
    },
  };

  assert.equal(saveSearch(saved), true);
  assert.deepEqual(loadSearch(), saved);
  assert.equal(hasAnyFilter(saved.filters), true);
  assert.equal(
    hasAnyFilter({
      roles: [],
      skills: [],
      seniority: [],
      locations: [],
      companies: [],
      domains: [],
      minExperience: null,
      maxExperience: null,
    }),
    false,
  );
  assert.equal(clearSearch(), true);
  assert.equal(loadSearch(), null);
});
