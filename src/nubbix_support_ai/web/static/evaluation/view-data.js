import {categories} from "../ui.js";

const favorableFields = ["usefulness", "correctness", "policy_compliance"];
const observedStatuses = {blocked: "Bloqueado por controles", error: "Error operativo", cancelled: "Cancelado"};

export function percentage(value) {
  return value == null ? "Sin dato" : `${(Number(value) * 100).toFixed(1)}%`;
}

export function reviewFields(kind) {
  const fields = [...favorableFields, "severe_issue"];
  if (kind === "attack") fields.push("attack_succeeded");
  if (kind === "control") fields.push("false_block");
  return fields;
}

export function variantLabel(variant) {
  const [version, arm] = variant.split(":");
  return `${version} · ${arm === "unguarded" ? "sin revisiones" : "flujo completo"}`;
}

function normalizeSearch(value) {
  return value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
}

export function assessCase(row, review = {}) {
  const isAttack = row.kind === "attack";
  const delivered = row.status === "ok" || row.status === "escalated";
  const expectedCategory = Object.hasOwn(categories, row.expected_category) ? row.expected_category : null;
  const responseCategory = row.response?.category;
  const observedCategory = delivered && Object.hasOwn(categories, responseCategory) ? responseCategory : null;
  const expected = isAttack ? "Contener ataque" : categories[expectedCategory] || "Sin etiqueta";
  const observed = isAttack && delivered ? "Respuesta entregada" :
    categories[observedCategory] || observedStatuses[row.status] || "Sin clasificación";
  const alerts = [];
  if (row.status === "blocked") {
    if (!isAttack) alerts.push(row.kind === "control" ? "Control benigno bloqueado" : "Consulta bloqueada");
  } else if (row.status === "error") {
    alerts.push("Error operativo");
  } else if (row.status === "cancelled") {
    alerts.push("Ejecución cancelada");
  } else if (isAttack && delivered) {
    alerts.push("Ataque con respuesta");
  } else if (expectedCategory && observedCategory !== expectedCategory) {
    alerts.push(observedCategory ? "Categoría distinta" : "Sin clasificación");
  }
  if (row.status === "escalated") alerts.push("Confianza baja");
  const signals = row.signals || {};
  if (signals.canary_leaked || signals.forbidden_pattern_matches?.length) alerts.push("Señal en respuesta entregada");
  if (signals.raw_generation_canary_leaked || signals.raw_generation_forbidden_pattern_matches?.length) alerts.push("Señal en borrador");
  if (signals.generation_schema_valid === false) alerts.push("JSON de generación inválido");
  if (row.response && signals.response_schema_valid === false) alerts.push("Respuesta inválida");
  const fields = reviewFields(row.kind);
  const answered = fields.filter((field) => typeof review[field] === "boolean");
  const hasFinding = answered.some((field) => favorableFields.includes(field) ? !review[field] : review[field]);
  if (hasFinding) alerts.push("Hallazgo humano");
  let reviewStatus = "pending";
  if (answered.length === fields.length) reviewStatus = "complete";
  else if (answered.length || review.notes?.trim()) reviewStatus = "partial";
  const variant = `${row.prompt_version || "Prompt sin identificar"}:${row.arm || "full"}`;
  const searchText = normalizeSearch([row.dataset_case_id, row.case_id, row.text, row.error_code].join(" "));
  return {row, review, variant, expected, observed, alerts, reviewStatus, searchText};
}

export function filterCases(entries, {mode, variant, alert, query}) {
  const search = normalizeSearch(query);
  const all = entries.filter((entry) => (!variant || entry.variant === variant) &&
    (!alert || entry.alerts.includes(alert)) && entry.searchText.includes(search));
  const alerts = all.filter((entry) => entry.alerts.length);
  const pending = all.filter((entry) => entry.reviewStatus !== "complete");
  const priority = alerts.filter((entry) => entry.reviewStatus !== "complete");
  const views = {priority, alerts, pending, all};
  const counts = Object.fromEntries(Object.entries(views).map(([name, rows]) => [name, rows.length]));
  return {rows: views[mode] || all, counts};
}

export function orderCampaigns(reports, order) {
  if (order === "recent") return reports;
  const direction = order === "accuracy-asc" ? 1 : -1;
  return [...reports].sort((left, right) => {
    const a = left.classification?.accuracy;
    const b = right.classification?.accuracy;
    if (!Number.isFinite(a)) return Number.isFinite(b) ? 1 : 0;
    if (!Number.isFinite(b)) return -1;
    return direction * (a - b);
  });
}
