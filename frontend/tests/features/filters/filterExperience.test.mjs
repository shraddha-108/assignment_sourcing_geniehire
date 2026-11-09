import assert from "node:assert/strict";
import test from "node:test";
import { BANDS, rangeFromSelection, selectionFromRange } from "../../../src/features/filters/filterExperience.ts";

test("rangeFromSelection combines one or adjacent bands", () => {
  assert.deepEqual(rangeFromSelection(["entry"]), { min: 0, max: 2 });
  assert.deepEqual(rangeFromSelection(["entry", "mid"]), { min: 0, max: 7 });
  assert.deepEqual(rangeFromSelection(["mid", "senior"]), { min: 3, max: null });
});

test("rangeFromSelection returns null for empty and non-adjacent selections", () => {
  assert.equal(rangeFromSelection([]), null);
  assert.equal(rangeFromSelection(["entry", "senior"]), null);
});

test("selectionFromRange returns only exact bands or adjacent runs", () => {
  assert.deepEqual(selectionFromRange(3, 7), ["mid"]);
  assert.deepEqual(selectionFromRange(0, 7), ["entry", "mid"]);
  assert.deepEqual(selectionFromRange(3, null), ["mid", "senior"]);
  assert.deepEqual(selectionFromRange(8, null), ["senior"]);
  assert.deepEqual(selectionFromRange(0, 3), []);
});

test("band range numbers have one frontend source of truth", () => {
  assert.deepEqual(BANDS, [
    { key: "entry", label: "Entry", min: 0, max: 2 },
    { key: "mid", label: "Mid", min: 3, max: 7 },
    { key: "senior", label: "Senior", min: 8, max: null },
  ]);
});
