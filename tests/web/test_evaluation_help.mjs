import assert from "node:assert/strict";
import test from "node:test";
import {classificationCoverageNote} from "../../src/nubbix_support_ai/web/static/evaluation-help.js";

test("explains low macro-F1 when a limited corpus omits categories", () => {
  const classification = {labelled: 30, accuracy: 29 / 30, macro_f1: 0.494, per_category: {billing: {support: 20}, technical: {support: 10}, account: {support: 0}, other: {support: 0}}};
  const before = structuredClone(classification);
  const note = classificationCoverageNote(classification);
  assert.match(note, /Cuenta/);
  assert.match(note, /Otras consultas/);
  assert.match(note, /cuatro categorías/);
  assert.match(note, /cero/);
  assert.deepEqual(classification, before);
});

test("a weak F1 alone does not imply that categories are missing", () => {
  const classification = {labelled: 40, macro_f1: 0.3, per_category: {billing: {support: 10}, technical: {support: 10}, account: {support: 10}, other: {support: 10}}};
  assert.equal(classificationCoverageNote(classification), null);
});

test("an empty or unavailable classification does not invent missing categories", () => {
  for (const classification of [undefined, {}, {labelled: 0}, {labelled: 10, per_category: {billing: {support: 10}}}]) assert.equal(classificationCoverageNote(classification), null);
});

test("a missing category is identified even when the other categories score well", () => {
  const classification = {labelled: 30, accuracy: 1, per_category: {billing: {support: 10}, technical: {support: 10}, account: {support: 10}, other: {support: 0}}};
  const note = classificationCoverageNote(classification);
  assert.match(note, /Otras consultas/);
  assert.doesNotMatch(note, /Facturación|Soporte técnico|Cuenta/);
});
