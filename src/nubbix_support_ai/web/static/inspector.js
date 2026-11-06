import {categories, copyJSON, dateTime, element, jsonSection, metrics, money, statusBadge} from "./ui.js";

const stages = {input_moderation: "Revisión de entrada", generation: "Generación", output_moderation: "Revisión de salida"};
const eventLabels = {"request.received": "Ticket recibido", "llm.request.started": "Llamada iniciada", "schema.validation.started": "Validando contrato", "schema.validation.completed": "Contrato validado", "schema.validation.failed": "Formato inválido", "moderation.completed": "Decisión del control", "llm.request.failed": "Falló la llamada", "attempt.completed": "Intento terminado", "retry.scheduled": "Nuevo intento programado", "human_review.suggested": "Revisión humana sugerida", "run.completed": "Flujo terminado", "run.failed": "Flujo interrumpido", "evaluation.started": "Campaña iniciada", "evaluation.case.started": "Caso iniciado", "evaluation.case.completed": "Caso terminado", "evaluation.completed": "Campaña terminada"};

export function createTimeline(target, onCount = () => {}) {
  const groups = new Map();
  let count = 0;
  return {
    reset() {
      target.replaceChildren();
      groups.clear();
      count = 0;
      onCount(count);
    },
    append(event) {
      const key = `${event.request_id}:${event.stage || "flow"}:${event.attempt || ""}`;
      let group = groups.get(key);
      if (!group) {
        group = element("details", "timeline-group");
        group.open = true;
        const title = event.stage ? `${stages[event.stage] || event.stage} · ${event.attempt ? "intento " + event.attempt : "decisión del control"}` : event.event.startsWith("evaluation.") ? "Campaña de evaluación" : "Solicitud";
        group.append(element("summary", "", title));
        groups.set(key, group);
        target.append(group);
      }
      const row = element("div", "event-row" + (/failed|retry/.test(event.event) ? " event-error" : ""));
      const content = element("div");
      content.append(element("span", "event-name", eventLabels[event.event] || event.event));
      const details = Object.entries(event.details || {}).map(([key, value]) => `${key}: ${value === null ? "sin dato" : key.endsWith("cost_usd") ? money(value) : value}`).join(" · ");
      if (details) content.append(element("span", "event-details", details));
      row.append(element("span", "event-time", `${Number(event.elapsed_ms || 0).toFixed(0)} ms`), content);
      group.append(row);
      count += 1;
      onCount(count);
    },
  };
}

export function renderResponse(response, status) {
  document.getElementById("response-empty").hidden = true;
  document.getElementById("response-content").hidden = false;
  const badge = statusBadge(status);
  badge.id = "response-status";
  document.getElementById("response-status").replaceWith(badge);
  document.getElementById("category-label").textContent = categories[response.category] || response.category;
  document.getElementById("confidence-label").textContent = `${Math.round(response.confidence * 100)}% de confianza declarada`;
  document.getElementById("confidence-meter").value = response.confidence;
  document.getElementById("answer-text").textContent = response.answer;
  document.getElementById("action-list").replaceChildren(...response.actions.map((action) => element("li", "", action)));
  document.getElementById("action-list").hidden = response.actions.length === 0;
  document.getElementById("actions-empty").hidden = response.actions.length > 0;
  document.getElementById("actions-note").hidden = response.actions.length === 0;
  document.getElementById("public-json").textContent = JSON.stringify(response, null, 2);
}

export function renderInspection(run, target, includeOverview = false) {
  target.replaceChildren();
  const header = element("div", "inspector-header");
  const identity = element("div");
  identity.append(element("h3", "", includeOverview ? "Detalle de la ejecución" : "Ejecución registrada"), element("code", "run-identifier", run.request_id));
  const copy = element("button", "button secondary compact", "Copiar JSON");
  copy.type = "button";
  copy.addEventListener("click", () => copyJSON(run, copy));
  header.append(identity, copy);
  const metadata = element("div", "inspector-metadata");
  for (const value of [run.provider, run.model, run.prompt_version, dateTime(run.timestamp)]) metadata.append(element("span", "", value));
  metadata.append(statusBadge(run.status));
  target.append(header, metadata);
  if (includeOverview) {
    const grid = element("div", "metrics-grid");
    metrics(grid, run.metrics || {});
    target.append(grid);
    jsonSection(target, "Ticket recibido", run.ticket, true);
    if (run.response) jsonSection(target, "Respuesta pública", run.response, true);
    const timeline = element("div", "timeline inspection-section");
    const view = createTimeline(timeline);
    (run.events || []).forEach((event) => view.append(event));
    target.append(timeline);
  }
  for (const call of run.calls || []) {
    const details = element("details", "inspection-section");
    details.append(element("summary", "", `${stages[call.stage] || call.stage} · intento ${call.attempt} · ${call.status} · ${Number(call.duration_ms || 0).toFixed(0)} ms`));
    details.append(element("h4", "", "Prompt de sistema efectivo"), element("pre", "", call.request?.system || "Sin dato"));
    details.append(element("h4", "", "Mensajes enviados"), element("pre", "", JSON.stringify(call.request?.messages, null, 2)));
    details.append(element("h4", "", "Respuesta textual del proveedor"), element("pre", "", call.response_text ?? "Sin respuesta textual registrada"));
    if (call.validated !== undefined || call.validated_response !== undefined) {
      details.append(element("h4", "", "Objeto validado"), element("pre", "", JSON.stringify(call.validated ?? call.validated_response, null, 2)));
    }
    details.append(element("h4", "", "Consumo y parámetros"), element("pre", "", JSON.stringify({usage: call.usage, known_cost_usd: call.known_cost_usd, reserved_unknown_usd: call.reserved_unknown_usd, max_output_tokens: call.request?.max_output_tokens, error_code: call.error_code}, null, 2)));
    jsonSection(details, "Esquema solicitado", call.request?.schema);
    target.append(details);
  }
  if (run.response) jsonSection(target, "Resultado final validado", run.response);
  jsonSection(target, "Métricas completas", run.metrics || {});
  jsonSection(target, "Inspector completo (JSON)", run);
}
