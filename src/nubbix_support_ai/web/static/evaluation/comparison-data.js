import {assessCase} from "./view-data.js";

function variantRows(report, variant) {
  const [version, arm] = variant.split(":");
  return (report.cases || []).filter((row) => row.prompt_version === version && (row.arm || "full") === arm);
}

function caseKey(row) {
  if (!row.dataset_case_id || typeof row.text !== "string") return null;
  return JSON.stringify([row.split ?? null, row.dataset_case_id, row.kind || "ticket", row.text,
    row.expected_category ?? null, row.expected_actions || [], row.forbidden_patterns || []]);
}

function counts(entries) {
  const stats = {labelled: 0, correct: 0, blocked: 0, errors: 0};
  for (const entry of entries) {
    if (entry.expectedCategory) stats.labelled += 1;
    if (entry.categoryResult === "match") stats.correct += 1;
    if (entry.row.status === "blocked") stats.blocked += 1;
    if (entry.row.status === "error") stats.errors += 1;
  }
  return stats;
}

function differsWhenRecorded(left, right) {
  return left != null && right != null && left !== right;
}

function recordedChanges(reportA, variantA, reportB, variantB) {
  const [versionA, armA] = variantA.split(":");
  const [versionB, armB] = variantB.split(":");
  const a = reportA.manifest || {};
  const b = reportB.manifest || {};
  const promptA = (a.prompts || []).find(({version}) => version === versionA);
  const promptB = (b.prompts || []).find(({version}) => version === versionB);
  const changes = [];
  if (differsWhenRecorded(reportA.summary?.model ?? a.model, reportB.summary?.model ?? b.model) ||
      differsWhenRecorded(reportA.summary?.provider ?? a.provider, reportB.summary?.provider ?? b.provider)) changes.push("modelo");
  if (versionA !== versionB) changes.push("prompt");
  else if (differsWhenRecorded(promptA?.content_hash, promptB?.content_hash)) changes.push("contenido del prompt");
  if (armA !== armB) changes.push("controles del flujo");
  if (differsWhenRecorded(promptA?.comparison_hash, promptB?.comparison_hash)) changes.push("contexto base");
  const parameterKeys = new Set([...Object.keys(a.parameters || {}), ...Object.keys(b.parameters || {})]);
  const differentParameters = a.parameters && b.parameters && [...parameterKeys].some((key) => a.parameters[key] !== b.parameters[key]);
  const limits = ["max_attempts", "max_output_tokens", "deadline_seconds"];
  if (differentParameters || limits.some((key) => differsWhenRecorded(a[key], b[key]))) changes.push("parámetros de ejecución");
  return changes;
}

export function compareVariants(reportA, variantA, reportB, variantB) {
  const rowsA = variantRows(reportA, variantA);
  const rowsB = variantRows(reportB, variantB);
  const byCase = new Map();
  for (const row of rowsB) {
    const key = caseKey(row);
    if (key) byCase.set(key, row);
  }
  const pairs = [];
  for (const row of rowsA) {
    const key = caseKey(row);
    const other = byCase.get(key);
    if (!other) continue;
    byCase.delete(key);
    const a = assessCase(row);
    const b = assessCase(other);
    const hitA = a.categoryResult === "match";
    const hitB = b.categoryResult === "match";
    const exclusiveHit = hitA === hitB ? null : (hitA ? "A" : "B");
    const outcomeChanged = row.status !== other.status || a.responseCategory !== b.responseCategory;
    const answerChanged = (row.response?.answer ?? null) !== (other.response?.answer ?? null) ||
      JSON.stringify(row.response?.actions || []) !== JSON.stringify(other.response?.actions || []);
    pairs.push({a, b, exclusiveHit, outcomeChanged, answerChanged});
  }
  return {
    pairs, onlyA: rowsA.length - pairs.length, onlyB: rowsB.length - pairs.length,
    categories: [...new Set(pairs.map(({a}) => a.expectedCategory).filter(Boolean))].sort(),
    statsA: counts(pairs.map(({a}) => a)), statsB: counts(pairs.map(({b}) => b)),
    changes: recordedChanges(reportA, variantA, reportB, variantB),
  };
}
