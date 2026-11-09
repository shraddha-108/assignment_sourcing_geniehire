import test from "node:test";
import assert from "node:assert/strict";
import { getCandidateDisplayMatchStatus } from "../../../src/features/candidates/candidateWorkflow.ts";

test("keeps explicit match statuses", () => {
  assert.equal(getCandidateDisplayMatchStatus("MATCH", []), "MATCH");
  assert.equal(getCandidateDisplayMatchStatus("PARTIAL_MATCH", []), "PARTIAL_MATCH");
});

test("infers a full match only when every requirement is fully met", () => {
  assert.equal(
    getCandidateDisplayMatchStatus(undefined, [
      { matched: true, status: "MATCH" },
      { matched: true, status: "MATCH" },
    ]),
    "MATCH",
  );
  assert.equal(
    getCandidateDisplayMatchStatus(undefined, [
      { matched: true, status: "MATCH" },
      { matched: false, status: "NO_MATCH" },
    ]),
    "PARTIAL_MATCH",
  );
});

test("uses a cautious partial label for unknown or no-match results", () => {
  assert.equal(getCandidateDisplayMatchStatus(undefined, []), "PARTIAL_MATCH");
  assert.equal(
    getCandidateDisplayMatchStatus("NO_MATCH", [{ matched: true, status: "MATCH" }]),
    "PARTIAL_MATCH",
  );
});

test("does not display a full match when a requirement is only partial", () => {
  assert.equal(
    getCandidateDisplayMatchStatus("MATCH", [
      { matched: false, status: "PARTIAL_MATCH" },
    ]),
    "PARTIAL_MATCH",
  );
});
