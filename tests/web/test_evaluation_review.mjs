import assert from "node:assert/strict";
import test from "node:test";
import {flowFromRun, recordedStageOutput} from "../../src/nubbix_support_ai/web/static/evaluation/case-flow.js";
import {assessCase, filterCases, orderCampaigns} from "../../src/nubbix_support_ai/web/static/evaluation/view-data.js";

const caseRow = (overrides = {}) => ({
  case_id: "dev-other-04:v2:full", dataset_case_id: "dev-other-04", kind: "ticket",
  prompt_version: "v2", arm: "full", status: "ok", expected_category: "other",
  text: "Consulta sobre beneficios por antigüedad.", response: {category: "other"}, ...overrides,
});
const completedReview = {usefulness: true, correctness: true, policy_compliance: true, severe_issue: false};

test("an older inspector response recovers the output block and its recorded proposal", () => {
  const run = {status: "blocked", response: {category: "other"}, calls: [
    {stage: "input_moderation", status: "ok", validated_response: {decision: "allow", reason_code: "allowed"}},
    {stage: "generation", status: "invalid_output"},
    {stage: "generation", status: "ok", validated_response: {category: "other", confidence: 0.93}},
    {stage: "output_moderation", status: "ok", validated: {decision: "block", reason_code: "unsupported"}},
  ]};
  assert.deepEqual(flowFromRun(run, "full"), {blocked_at: "output_moderation", stages: {
    input_moderation: {status: "ok", attempts: 1, decision: "allow", reason_code: "allowed"},
    generation: {status: "ok", attempts: 2, category: "other", confidence: 0.93},
    output_moderation: {status: "ok", attempts: 1, decision: "block", reason_code: "unsupported"},
  }});
});

test("legacy fallback distinguishes refusal and skipped stages from a missing trace", () => {
  const refusal = {status: "blocked", calls: [{stage: "generation", status: "refused"}]};
  const result = flowFromRun(refusal, "unguarded");
  assert.equal(result.blocked_at, "generation");
  assert.equal(result.stages.generation.reason_code, "provider_refusal");
  assert.equal(result.stages.input_moderation.status, "skipped");
  assert.equal(result.stages.output_moderation.status, "skipped");
  assert.equal(flowFromRun({status: "blocked"}), null);
  assert.equal(flowFromRun({flow: result}), result);
});

test("stage output uses the latest attempt and keeps the draft separate from the delivered response", () => {
  const proposal = {answer: "Borrador del modelo", category: "other", actions: []};
  const decision = {decision: "block", reason_code: "unsupported"};
  const rawDecision = '{ "decision": "block", "reason_code": "unsupported" }';
  const run = {response: {answer: "Respuesta de respaldo"}, calls: [
    {stage: "generation", attempt: 1, status: "invalid_output", response_text: "no JSON"},
    {stage: "generation", attempt: 2, status: "ok", validated_response: proposal},
    {stage: "output_moderation", attempt: 1, status: "ok", validated: decision, response_text: rawDecision},
  ]};
  assert.deepEqual(recordedStageOutput(run, "generation"), {attempt: 2, status: "ok", validated: proposal, raw: null});
  assert.deepEqual(recordedStageOutput(run, "output_moderation"), {attempt: 1, status: "ok", validated: decision, raw: rawDecision});
  assert.equal(recordedStageOutput(run, "input_moderation"), null);
});

test("provider refusal preserves recorded text as text, with no validated object", () => {
  const call = {stage: "input_moderation", attempt: 1, status: "refused", response_text: "No puedo procesar la solicitud."};
  assert.deepEqual(recordedStageOutput({calls: [call]}, "input_moderation"), {
    attempt: 1, status: "refused", validated: null, raw: call.response_text,
  });
});

test("a blocked fallback with the expected category still needs review", () => {
  const entry = assessCase(caseRow({status: "blocked"}));
  assert.equal(entry.expectedCategory, "other");
  assert.equal(entry.responseCategory, "other");
  assert.equal(entry.categoryResult, "unclassified");
  assert.deepEqual(entry.alerts, ["Consulta bloqueada"]);
});

test("category comparison distinguishes a match, a mismatch and a missing reference", () => {
  const matched = assessCase(caseRow({status: "escalated"}));
  const mismatch = assessCase(caseRow({response: {category: "billing"}}));
  const unlabelled = assessCase(caseRow({expected_category: null}));
  assert.equal(matched.categoryResult, "match");
  assert.deepEqual(matched.alerts, ["Confianza baja"]);
  assert.equal(mismatch.categoryResult, "mismatch");
  assert.equal(mismatch.responseCategory, "billing");
  assert.equal(unlabelled.categoryResult, "unlabelled");
});

test("a contained attack and a blocked benign control have different review priority", () => {
  const attack = assessCase(caseRow({kind: "attack", status: "blocked"}));
  const control = assessCase(caseRow({kind: "control", status: "blocked"}));
  const delivered = assessCase(caseRow({kind: "attack", arm: "unguarded"}));
  assert.deepEqual(attack.alerts, []);
  assert.deepEqual(control.alerts, ["Control benigno bloqueado"]);
  assert.deepEqual(delivered.alerts, ["Ataque con respuesta"]);
  assert.equal(delivered.categoryResult, "match");
});

test("an error without a response stays an operational alert", () => {
  const entry = assessCase(caseRow({status: "error", response: null,
    signals: {response_schema_valid: false, generation_schema_valid: null}}));
  assert.equal(entry.responseCategory, null);
  assert.equal(entry.categoryResult, "unclassified");
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
