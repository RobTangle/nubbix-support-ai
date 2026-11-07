import {readRun} from "../api.js";
import {element, jsonSection} from "../ui.js";
import {actionList, caseStages} from "./case-content.js";

const stageStates = {
  not_run: "No se ejecutó", skipped: "Omitida por la ablación", refused: "Rechazo del proveedor",
  invalid_output: "Salida inválida", error: "Error de llamada", cancelled: "Cancelada", running: "En curso",
};
const moderationEffects = {
  input_moderation: {allow: "El moderador permitió que el ticket pasara al modelo principal.", block: "El moderador bloqueó el ticket antes de la generación."},
  output_moderation: {allow: "El moderador permitió entregar la propuesta.", block: "El moderador bloqueó la propuesta del modelo."},
};
let nextPanelId = 0;

function validatedOutput(call) {
  return call.status === "ok" ? call.validated_response ?? call.validated ?? null : null;
}

export function recordedStageOutput(run, stage) {
  const call = (run.calls || []).findLast((item) => item?.stage === stage);
  if (!call) return null;
  return {attempt: call.attempt, status: call.status, validated: validatedOutput(call), raw: call.response_text ?? null};
}

export function flowFromRun(run, arm) {
  if (run.flow?.stages) return run.flow;
  if (!Array.isArray(run.calls)) return null;
  const unguarded = (arm || run.evaluation_arm) === "unguarded";
  const stages = {};
  const blockers = [];
  for (const stage of Object.keys(caseStages)) {
    const attempts = run.calls.filter((call) => call?.stage === stage);
    const last = attempts.at(-1);
    if (!last) {
      stages[stage] = {status: unguarded && stage !== "generation" ? "skipped" : "not_run", attempts: 0};
      continue;
    }
    const status = last.status || "unknown";
    const result = {status, attempts: attempts.length};
    const validated = validatedOutput(last);
    if (validated) {
      const keys = stage === "generation" ? ["category", "confidence"] : ["decision", "reason_code"];
      for (const key of keys) if (Object.hasOwn(validated, key)) result[key] = validated[key];
    }
    if (status === "refused") result.reason_code = "provider_refusal";
    if (last.error_code) result.error_code = last.error_code;
    if (status === "refused" || result.decision === "block" || result.decision === "review") blockers.push(stage);
    stages[stage] = result;
  }
  const blocked_at = run.status === "blocked" && blockers.length === 1 ? blockers[0] : null;
  return {stages, blocked_at};
}

function stageCard(stage, result, stoppedHere) {
  const card = element("div", stoppedHere ? "case-stage stage-stopped" : "case-stage");
  card.append(element("h4", "", caseStages[stage][0]));
  if (result.decision) {
    const badge = element("code", `case-stage-state decision-${result.decision}`, result.decision);
    card.append(badge);
  } else {
    const label = stage === "generation" && result.status === "ok" ? "Propuesta generada" : stageStates[result.status] || "Sin decisión registrada";
    card.append(element("span", "case-stage-state", label));
  }
  if (result.reason_code || result.error_code) {
    const reason = element("p", "case-stage-note");
    reason.append("Motivo · ", element("code", "", result.reason_code || result.error_code));
    card.append(reason);
  }
  if (stage === "generation" && result.category) {
    const info = element("p", "case-stage-note");
    info.append("Categoría · ", element("code", "", result.category));
    if (Number.isFinite(result.confidence)) info.append(` · ${Math.round(result.confidence * 100)}% de confianza`);
    card.append(info);
  }
  if (stoppedHere) card.append(element("p", "case-stage-stop", "El flujo se detuvo acá."));
  if (result.attempts > 1) card.append(element("p", "case-stage-note", `${result.attempts} intentos · último resultado`));
  return card;
}

function outputBody(stage, record, rejected) {
  const body = element("div");
  if (!record) {
    body.append(element("p", "field-note", "Esta etapa no tiene una llamada registrada."));
    return body;
  }
  const {validated, raw} = record;
  if (record.attempt > 1) body.append(element("p", "field-note", `Intento ${record.attempt} · último registrado`));
  if (validated && stage === "generation") {
    const label = rejected ? "Borrador descartado en moderación de salida" : "Propuesta original del modelo";
    body.append(element("span", rejected ? "case-kind case-draft-label" : "case-kind", label),
      element("p", "case-answer", validated.answer),
      actionList("Acciones propuestas por el modelo", validated.actions, "Sin acciones sugeridas."));
    jsonSection(body, "Ver JSON validado", validated);
  } else if (validated) {
    const effect = validated.decision === "review" ? "El moderador pidió revisión y el flujo se detuvo." :
      moderationEffects[stage]?.[validated.decision];
    if (effect) body.append(element("p", "case-stage-effect", effect));
    const code = element("pre", "", JSON.stringify(validated, null, 2));
    code.tabIndex = 0;
    body.append(code);
  } else {
    body.append(element("p", "case-stage-effect", stageStates[record.status] || "Sin objeto validado"));
  }
  if (raw) jsonSection(body, "Ver salida textual del proveedor", raw, !validated);
  else body.append(element("p", "field-note", "Sin salida textual registrada."));
  return body;
}

function createOutputPanel(loadRun, flow) {
  const panel = element("section", "case-stage-output");
  panel.id = `case-stage-output-${++nextPanelId}`;
  panel.hidden = true;
  const title = element("h4");
  title.id = `${panel.id}-title`;
  title.tabIndex = -1;
  panel.setAttribute("aria-labelledby", title.id);
  const close = element("button", "text-button", "Cerrar salida");
  close.type = "button";
  const heading = element("div", "case-stage-output-heading");
  heading.append(title, close);
  const content = element("div");
  panel.append(heading, content);
  let activeButton;
  close.addEventListener("click", () => {
    panel.hidden = true;
    content.replaceChildren();
    activeButton?.setAttribute("aria-expanded", "false");
    activeButton?.focus();
    activeButton = undefined;
  });
  return {panel, open};

  async function open(stage, button) {
    activeButton?.setAttribute("aria-expanded", "false");
    activeButton = button;
    button.setAttribute("aria-expanded", "true");
    title.textContent = `Salida · ${caseStages[stage][0]}`;
    const loading = element("p", "field-note", "Leyendo la salida registrada…");
    loading.setAttribute("role", "status");
    content.replaceChildren(loading);
    panel.hidden = false;
    title.focus({preventScroll: true});
    panel.scrollIntoView({block: "nearest"});
    try {
      const record = recordedStageOutput(await loadRun(), stage);
      if (content.firstChild === loading) content.replaceChildren(outputBody(stage, record, flow.blocked_at === "output_moderation"));
    } catch {
      if (content.firstChild === loading) loading.textContent = "No se pudo leer la salida registrada.";
    }
  }
}

export function createCaseFlow(row, {collapsible = false, onResolved = () => {}} = {}) {
  const section = element(collapsible ? "details" : "section", "case-flow");
  section.append(element(collapsible ? "summary" : "h3", "", "Qué devolvió cada etapa"));
  const content = element("div");
  section.append(content);
  let pendingRun;
  const loadRun = () => pendingRun ??= readRun(row.request_id).catch((error) => {
    pendingRun = undefined;
    throw error;
  });
  if (collapsible) {
    section.addEventListener("toggle", () => {
      if (section.open && !content.childElementCount) void populate();
    });
  } else {
    void populate();
  }
  return section;

  async function populate() {
    let flow = row.flow;
    if (!flow?.stages && flow !== null && row.request_id) {
      content.replaceChildren(element("p", "field-note", "Leyendo la traza registrada…"));
      try {
        flow = flowFromRun(await loadRun(), row.arm);
      } catch (error) {
        if (error.code !== "run_not_found") {
          const retry = element("button", "text-button", "Reintentar lectura de la traza");
          retry.type = "button";
          retry.addEventListener("click", () => void populate());
          content.replaceChildren(element("p", "field-note", "No se pudo leer la traza de esta ejecución."), retry);
          return;
        }
        flow = null;
      }
      row.flow = flow;
      onResolved();
    }
    if (!flow?.stages) {
      content.replaceChildren(element("p", "field-note", "No hay una traza local disponible para esta ejecución."));
      return;
    }
    const grid = element("div", "case-stage-grid");
    const {panel, open} = createOutputPanel(loadRun, flow);
    for (const [stage, [, location]] of Object.entries(caseStages)) {
      const result = flow.stages[stage] || {};
      const card = stageCard(stage, result, flow.blocked_at === stage);
      if (row.request_id && result.attempts > 0) {
        const button = element("button", "text-button case-stage-toggle", "Ver salida");
        button.type = "button";
        button.setAttribute("aria-label", stage === "generation" ? "Ver salida del modelo principal" : `Ver salida de ${location}`);
        button.setAttribute("aria-controls", panel.id);
        button.setAttribute("aria-expanded", "false");
        button.addEventListener("click", () => void open(stage, button));
        card.append(button);
      }
      grid.append(card);
    }
    content.replaceChildren(grid, panel);
  }
}
