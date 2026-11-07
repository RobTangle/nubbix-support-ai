import {readRun} from "../api.js";
import {element} from "../ui.js";

const stages = {
  input_moderation: ["Moderación de entrada", "la moderación de entrada"],
  generation: ["Modelo principal", "el modelo principal"],
  output_moderation: ["Moderación de salida", "la moderación de salida"],
};
const stageStates = {
  not_run: "No se ejecutó", skipped: "Omitida por la ablación", refused: "Rechazo del proveedor",
  invalid_output: "Salida inválida", error: "Error de llamada", cancelled: "Cancelada", running: "En curso",
};

export function blockOrigin(row) {
  const stage = row.flow?.blocked_at;
  const result = row.flow?.stages?.[stage];
  if (!result || !Object.hasOwn(stages, stage)) return "Etapa del bloqueo no registrada";
  const location = stages[stage][1];
  let description = `Bloqueo en ${location}`;
  if (result.status === "refused") description = `Rechazo del proveedor en ${location}`;
  else if (result.decision === "review") description = `Revisión solicitada por ${location}`;
  return result.reason_code ? `${description} · ${result.reason_code}` : description;
}

function stageCard(stage, result, stoppedHere) {
  const card = element("div", stoppedHere ? "case-stage stage-stopped" : "case-stage");
  card.append(element("h4", "", stages[stage][0]));
  if (result.decision) {
    const badge = element("code", `case-stage-state decision-${result.decision}`, result.decision);
    card.append(badge);
  } else {
    const label = stage === "generation" && result.status === "ok" ? "Propuesta válida" : stageStates[result.status] || "Sin decisión registrada";
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

function originalProposal(loadRun, rejected) {
  const details = element("details", "case-proposal inspection-section");
  const label = rejected ? "Ver propuesta rechazada por el control de salida" : "Ver propuesta original del modelo";
  details.append(element("summary", "", label));
  details.addEventListener("toggle", async () => {
    if (!details.open || details.childElementCount > 1) return;
    const content = element("div");
    content.append(element("p", "field-note", "Leyendo la propuesta registrada…"));
    details.append(content);
    try {
      const run = await loadRun();
      const last = (run.calls || []).findLast((call) => call.stage === "generation");
      const proposal = last?.status === "ok" ? last.validated_response ?? last.validated : null;
      content.replaceChildren(proposal ? element("pre", "", JSON.stringify(proposal, null, 2)) :
        element("p", "field-note", "La traza no contiene una propuesta validada."));
    } catch {
      content.replaceChildren(element("p", "field-note", "No se pudo leer la propuesta registrada."));
    }
  });
  return details;
}

export function createCaseFlow(row, {collapsible = false} = {}) {
  const section = element(collapsible ? "details" : "section", "case-flow");
  section.append(element(collapsible ? "summary" : "h3", "", "Qué devolvió cada etapa"));
  const content = element("div");
  section.append(content);
  let pendingRun;
  const loadRun = () => pendingRun ??= readRun(row.request_id);
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
    if (!flow && row.request_id) {
      content.append(element("p", "field-note", "Leyendo la traza registrada…"));
      try {
        flow = (await loadRun()).flow;
      } catch {
        flow = null;
      }
    }
    if (!flow?.stages) {
      content.replaceChildren(element("p", "field-note", "No hay una traza local disponible para esta ejecución."));
      return;
    }
    const grid = element("div", "case-stage-grid");
    for (const stage of Object.keys(stages)) {
      grid.append(stageCard(stage, flow.stages[stage] || {}, flow.blocked_at === stage));
    }
    content.replaceChildren(grid);
    if (flow.stages.generation?.status === "ok" && row.request_id) {
      content.append(originalProposal(loadRun, flow.blocked_at === "output_moderation"));
    }
  }
}
