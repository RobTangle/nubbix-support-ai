import assert from "node:assert/strict";
import test from "node:test";
import {assessCase, filterCases, orderCampaigns} from "../../src/nubbix_support_ai/web/static/evaluation/view-data.js";

const caseRow = (overrides = {}) => ({
  case_id: "dev-other-04:v2:full", dataset_case_id: "dev-other-04", kind: "ticket",
  prompt_version: "v2", arm: "full", status: "ok", expected_category: "other",
  text: "Consulta sobre beneficios por antigüedad.", response: {category: "other"}, ...overrides,
});
const completedReview = {usefulness: true, correctness: true, policy_compliance: true, severe_issue: false};

test("a blocked fallback with the expected category still needs review", () => {
  const entry = assessCase(caseRow({status: "blocked"}));
  assert.equal(entry.expected, "Otras consultas");
  assert.equal(entry.observed, "Bloqueado por controles");
  assert.deepEqual(entry.alerts, ["Consulta bloqueada"]);
});

test("a contained attack and a blocked benign control have different review priority", () => {
  const attack = assessCase(caseRow({kind: "attack", status: "blocked"}));
  const control = assessCase(caseRow({kind: "control", status: "blocked"}));
  const delivered = assessCase(caseRow({kind: "attack", arm: "unguarded"}));
  assert.deepEqual(attack.alerts, []);
  assert.deepEqual(control.alerts, ["Control benigno bloqueado"]);
  assert.deepEqual(delivered.alerts, ["Ataque con respuesta"]);
  assert.equal(delivered.observed, "Respuesta entregada");
});

test("an error without a response stays an operational alert", () => {
  const entry = assessCase(caseRow({status: "error", response: null,
    signals: {response_schema_valid: false, generation_schema_valid: null}}));
  assert.deepEqual(entry.alerts, ["Error operativo"]);
});

test("review completion follows applicable fields and keeps human findings visible", () => {
  const row = caseRow({kind: "control"});
  assert.equal(assessCase(row, completedReview).reviewStatus, "partial");
  const complete = assessCase(row, {...completedReview, false_block: true});
  assert.equal(complete.reviewStatus, "complete");
  assert.deepEqual(complete.alerts, ["Hallazgo humano"]);
});

test("priority combines variant and accent insensitive search with pending alerts", () => {
  const pending = assessCase(caseRow({status: "blocked"}));
  const reviewed = assessCase(caseRow({prompt_version: "v1", status: "blocked"}), completedReview);
  const mismatch = assessCase(caseRow({response: {category: "billing"}}));
  const entries = [pending, reviewed, mismatch, assessCase(caseRow())];
  const filters = {mode: "priority", variant: "v2:full", query: "antiguedad"};
  const view = filterCases(entries, filters);
  assert.deepEqual(view.rows, [pending, mismatch]);
  assert.equal(view.counts.all, 3);
  assert.deepEqual(mismatch.alerts, ["Categoría distinta"]);
  assert.deepEqual(filterCases(entries, {...filters, alert: "Consulta bloqueada"}).rows, [pending]);
  assert.deepEqual(filterCases(entries, {...filters, mode: "all", alert: "Categoría distinta"}).rows, [mismatch]);
  assert.deepEqual(filterCases(entries, {...filters, mode: "alerts", variant: ""}).rows,
    [pending, reviewed, mismatch]);
});

test("ordering by accuracy keeps missing measurements below real zeros", () => {
  const reports = [
    {run_id: "none", classification: {accuracy: null}},
    {run_id: "zero", classification: {accuracy: 0}},
    {run_id: "some", classification: {accuracy: 0.8}},
  ];
  assert.deepEqual(orderCampaigns(reports, "accuracy-desc").map(({run_id}) => run_id), ["some", "zero", "none"]);
  assert.deepEqual(orderCampaigns(reports, "accuracy-asc").map(({run_id}) => run_id), ["zero", "some", "none"]);
  assert.equal(reports[0].run_id, "none");
});
