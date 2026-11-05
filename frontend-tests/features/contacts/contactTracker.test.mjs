import test from "node:test";
import assert from "node:assert/strict";
import {
  CONTACT_STATUSES,
  loadContacts,
  saveContacts,
} from "../../../src/features/contacts/contactTracker.ts";

function installStorage(storage) {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { localStorage: storage },
  });
}

test("persists contact records and their pipeline status", () => {
  const values = new Map();
  installStorage({
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  });
  const record = {
    candidate: { id: 12, name: "Asha" },
    status: "Contacted",
    addedAt: "2026-11-05T00:00:00.000Z",
    updatedAt: "2026-11-05T00:00:00.000Z",
    contactedAt: "2026-11-05T00:00:00.000Z",
    sourceQuery: "React developer",
  };

  assert.deepEqual(saveContacts([record]), { value: true, error: null });
  assert.deepEqual(loadContacts(), { value: [record], error: null });
  assert.deepEqual(CONTACT_STATUSES, [
    "To contact",
    "Contacted",
    "Replied",
    "Interviewing",
    "Hired",
    "Not interested",
  ]);
});

test("reports contact storage failures instead of silently losing changes", () => {
  installStorage({
    getItem: () => { throw new Error("blocked"); },
    setItem: () => { throw new Error("blocked"); },
  });

  assert.match(loadContacts().error, /could not be loaded/);
  assert.match(saveContacts([]).error, /could not be saved/);
});
