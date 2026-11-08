import assert from "node:assert/strict";
import test from "node:test";
import {compareVariants} from "../../src/nubbix_support_ai/web/static/evaluation/comparison-data.js";

function row(id, version, overrides = {}) {
  return {
    dataset_case_id: id, case_id: `${id}:${version}:full`, split: "dev", kind: "ticket",
    prompt_version: version, arm: "full", text: `Ticket ${id}`, expected_category: "other",
    status: "ok", response: {category: "other", answer: "Propuesta", actions: []}, ...overrides,
  };
}

test("partial campaigns are scored on the same unchanged cases", () => {
  const a = {cases: [row("shared", "v1"), row("old", "v1"), row("changed", "v1"), row("label", "v1")]};
  const b = {cases: [row("shared", "v2", {status: "blocked"}), row("new", "v2"),
    row("changed", "v2", {text: "Texto nuevo"}), row("label", "v2", {expected_category: "account"}),
    row("shared", "v2", {arm: "unguarded"})]};
  const result = compareVariants(a, "v1:full", b, "v2:full");
  assert.deepEqual(result.pairs.map((pair) => pair.a.row.dataset_case_id), ["shared"]);
  assert.equal(result.onlyA, 3);
  assert.equal(result.onlyB, 3);
  assert.deepEqual(result.statsA, {labelled: 1, correct: 1, blocked: 0, errors: 0});
  assert.deepEqual(result.statsB, {labelled: 1, correct: 0, blocked: 1, errors: 0});
  assert.equal(result.pairs[0].exclusiveHit, "A");
  assert.equal(result.pairs[0].outcomeChanged, true);
});

test("prompt variants in one report separate changes of outcome from changes in wording", () => {
  const report = {cases: [row("wording", "v1"), row("wording", "v2", {response: {category: "other", answer: "Otra propuesta"}}),
    row("missing", "v1", {expected_category: null}), row("missing", "v2", {expected_category: null, status: "error", response: null}),
    row("fixed", "v1", {status: "blocked"}), row("fixed", "v2")]};
  const {pairs, statsB, categories, changes} = compareVariants(report, "v1:full", report, "v2:full");
  assert.deepEqual(pairs.map(({outcomeChanged, answerChanged, exclusiveHit}) => [outcomeChanged, answerChanged, exclusiveHit]),
    [[false, true, null], [true, true, null], [true, false, "B"]]);
  assert.deepEqual(statsB, {labelled: 2, correct: 2, blocked: 0, errors: 1});
  assert.deepEqual(categories, ["other"]);
  assert.deepEqual(changes, ["prompt"]);
});

test("same case IDs in different splits do not provide a comparison", () => {
  const a = {cases: [row("duplicate", "v1")]};
  const b = {cases: [row("duplicate", "v1", {split: "test"})]};
  const result = compareVariants(a, "v1:full", b, "v1:full");
  assert.equal(result.pairs.length, 0);
  assert.equal(result.onlyA, 1);
  assert.equal(result.onlyB, 1);
  assert.equal(result.statsA.labelled, 0);
});

test("an attack with a matching category is a security outcome, not a classification hit", () => {
  const attack = {kind: "attack", expected_category: "technical"};
  const a = {cases: [row("attack", "v2", {...attack, status: "blocked"}), row("control", "v2")]};
  const b = {cases: [row("attack", "v3", {...attack, response: {category: "technical"}}), row("control", "v3")]};
  const result = compareVariants(a, "v2:full", b, "v3:full");
  assert.deepEqual(result.statsA, {labelled: 1, correct: 1, blocked: 1, errors: 0});
  assert.deepEqual(result.statsB, {labelled: 1, correct: 1, blocked: 0, errors: 0});
  assert.equal(result.pairs[0].exclusiveHit, null);
  assert.equal(result.pairs[0].outcomeChanged, true);
  assert.deepEqual(result.categories, ["other"]);
});

test("the same prompt name can hide content and configuration differences", () => {
  const a = {cases: [], summary: {provider: "openai", model: "one"},
    manifest: {max_attempts: 2, prompts: [{version: "v1", content_hash: "first", comparison_hash: "old"}]}};
  const b = {cases: [], summary: {provider: "google", model: "two"},
    manifest: {max_attempts: 3, prompts: [{version: "v1", content_hash: "second", comparison_hash: "new"}]}};
  const result = compareVariants(a, "v1:full", b, "v1:unguarded");
  assert.deepEqual(result.changes, ["modelo", "contenido del prompt", "controles del flujo", "contexto base", "parámetros de ejecución"]);
});
