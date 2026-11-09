import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_SEQUENCES,
  interpolateTemplate,
} from "../../../src/features/outreach/outreachSequence.ts";

test("default sequences contain at least 2 predefined sequences", () => {
  assert.ok(DEFAULT_SEQUENCES.length >= 2);
  const engSeq = DEFAULT_SEQUENCES.find((s) => s.id === "seq-eng-outbound");
  assert.ok(engSeq);
  assert.equal(engSeq.steps.length, 3);
});

test("interpolateTemplate replaces placeholders correctly", () => {
  const template = "Hello {{firstName}}, saw your work at {{company}} in {{topSkill}} for {{searchQuery}}.";
  const rendered = interpolateTemplate(template, {
    firstName: "Lorenze",
    company: "Crewai",
    topSkill: "Python",
    searchQuery: "AI Engineer",
  });
  assert.equal(
    rendered,
    "Hello Lorenze, saw your work at Crewai in Python for AI Engineer."
  );
});

test("interpolateTemplate falls back gracefully if placeholders are missing", () => {
  const template = "Hello {{firstName}} at {{company}}.";
  const rendered = interpolateTemplate(template, {});
  assert.equal(rendered, "Hello there at your company.");
});
