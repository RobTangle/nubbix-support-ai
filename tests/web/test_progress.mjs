import assert from "node:assert/strict";
import test from "node:test";
import {TicketProgress} from "../../src/nubbix_support_ai/web/static/progress.js";

const event = (name, stage = null, details = {}, attempt = null) => ({event: name, stage, details, attempt, elapsed_ms: 1200});

test("starts immediately with pending stages before the first server event", () => {
  const progress = new TicketProgress();
  progress.start();
  assert.equal(progress.status, "running");
  assert.equal(progress.activeStage, null);
  assert.deepEqual(progress.stages.map((stage) => stage.status), ["pending", "pending", "pending"]);
});

test("a valid safety schema still waits for the moderation decision", () => {
  const progress = new TicketProgress();
  progress.start();
  progress.append(event("llm.request.started", "input_moderation", {}, 1));
  progress.append(event("schema.validation.completed", "input_moderation", {}, 1));
  assert.equal(progress.stages[0].status, "active");
  progress.append(event("moderation.completed", "input_moderation", {decision: "allow"}));
  assert.equal(progress.stages[0].status, "completed");
  assert.equal(progress.stages[1].status, "pending");
});

test("generation is only complete after its schema is validated", () => {
  const progress = new TicketProgress();
  progress.start();
  progress.append(event("llm.request.started", "generation", {}, 1));
  progress.append(event("schema.validation.failed", "generation", {}, 1));
  assert.equal(progress.stages[1].status, "active");
  progress.append(event("schema.validation.completed", "generation", {}, 2));
  assert.equal(progress.stages[1].status, "completed");
  assert.equal(progress.stages[2].status, "pending");
});

test("retry stays within its stage and records the actual attempt", () => {
  const progress = new TicketProgress();
  progress.start();
  progress.append(event("llm.request.started", "generation", {}, 1));
  progress.append(event("retry.scheduled", "generation", {delay_seconds: 3, error_code: "rate_limited"}, 1));
  assert.equal(progress.activeStage, "generation");
  assert.equal(progress.stages[1].status, "retrying");
  assert.equal(progress.stages[2].status, "pending");
  progress.append(event("llm.request.started", "generation", {}, 2));
  assert.equal(progress.stages[1].attempt, 2);
  assert.equal(progress.stages[1].status, "active");
});

test("an early block never completes stages that did not run", () => {
  const progress = new TicketProgress();
  progress.start();
  progress.append(event("llm.request.started", "input_moderation", {}, 1));
  progress.append(event("moderation.completed", "input_moderation", {decision: "block"}));
  progress.finish("blocked");
  assert.deepEqual(progress.stages.map((stage) => stage.status), ["blocked", "skipped", "skipped"]);
});

test("the full flow waits for the final record before leaving the processing state", () => {
  const progress = new TicketProgress();
  progress.start();
  progress.append(event("moderation.completed", "input_moderation", {decision: "allow"}));
  progress.append(event("schema.validation.completed", "generation", {}, 1));
  progress.append(event("moderation.completed", "output_moderation", {decision: "allow"}));
  progress.append(event("run.completed", null, {status: "ok"}));
  assert.equal(progress.status, "running");
  progress.finish("ok");
  assert.equal(progress.status, "ok");
  assert.deepEqual(progress.stages.map((stage) => stage.status), ["completed", "completed", "completed"]);
});

test("cancellation and transport errors preserve finished stages without inventing success", () => {
  for (const status of ["cancelled", "error"]) {
    const progress = new TicketProgress();
    progress.start();
    progress.append(event("moderation.completed", "input_moderation", {decision: "allow"}));
    progress.append(event("llm.request.started", "generation", {}, 1));
    if (status === "cancelled") {
      progress.cancel();
      assert.equal(progress.status, "cancelling");
    }
    progress.finish(status);
    assert.equal(progress.status, status);
    assert.deepEqual(progress.stages.map((stage) => stage.status), ["completed", status, "skipped"]);
  }
});

test("a new submission clears previous attempts and recent activity", () => {
  const progress = new TicketProgress();
  progress.start();
  progress.append(event("llm.request.started", "generation", {}, 2));
  progress.finish("error");
  progress.start();
  assert.equal(progress.activeStage, null);
  assert.equal(progress.activities.length, 0);
  assert.deepEqual(progress.stages.map((stage) => stage.attempt), [0, 0, 0]);
  assert.deepEqual(progress.stages.map((stage) => stage.status), ["pending", "pending", "pending"]);
});

test("a terminal stage no longer describes its attempt as running or waiting", () => {
  for (const status of ["cancelled", "error"]) {
    const progress = new TicketProgress();
    progress.start();
    progress.append(event("llm.request.started", "generation", {}, 1));
    progress.finish(status);
    assert.doesNotMatch(progress.stages[1].note, /en curso|esperando|pausa/i);
  }
});

test("recent activity is bounded and late events cannot revive a terminal run", () => {
  const progress = new TicketProgress();
  progress.start();
  for (let index = 0; index < 9; index += 1) progress.append(event("llm.request.started", "generation", {}, 1));
  assert.equal(progress.activities.length, 3);
  progress.finish("error");
  const snapshot = JSON.stringify(progress);
  progress.append(event("llm.request.started", "output_moderation", {}, 1));
  assert.equal(JSON.stringify(progress), snapshot);
});
