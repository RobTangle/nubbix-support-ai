import {getJSON, LabError, streamJSON} from "./api.js";
import {createTimeline} from "./inspector.js";
import {classificationCoverageNote, createEvaluatorGuide, createMetricsGuide, evaluationMetrics, reviewCriteria} from "./evaluation-help.js";
import {categories, configureProviderSelectors, copyJSON, dateTime, element, errorMessage, jsonSection, money, notice, statusBadge, statuses} from "./ui.js";

function percentage(value) {
  return value == null ? "Sin dato" : `${(Number(value) * 100).toFixed(1)}%`;
}

function summaryCard(key, value, note) {
  const card = element("div", "metric");
  card.append(element("div", "metric-label", evaluationMetrics[key].label), element("strong", "metric-value", value), element("span", "metric-note", note));
  return card;
}

function comparisonTable(variants) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "comparison-table");
  table.append(element("caption", "", "Comparación automática por versión y brazo"));
  const head = element("thead");
  const header = element("tr");
  for (const key of ["variant", "accuracy", "macro_f1", "generation_json", "errors_blocks", "human"]) {
    const definition = evaluationMetrics[key];
    const cell = element("th");
    cell.scope = "col";
    cell.append(element("span", "", definition.label), element("small", "column-help", definition.note));
    header.append(cell);
  }
  head.append(header);
  const body = element("tbody");
  for (const [name, variant] of Object.entries(variants || {})) {
    const row = element("tr");
    const label = name.replace(":full", " · flujo completo").replace(":unguarded", " · sin revisiones");
    const nameCell = element("th", "", label);
    nameCell.scope = "row";
    row.append(nameCell);
    for (const value of [percentage(variant.classification?.accuracy), percentage(variant.classification?.macro_f1), percentage(variant.json_validity?.generation_valid_rate), `${variant.errors || 0} / ${variant.blocked || 0}`, percentage(variant.human_review?.coverage)]) row.append(element("td", "", value));
    body.append(row);
  }
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

function reviewForm(report, row, saved, onSaved) {
  const form = element("form", "review-form inspection-section");
  form.append(element("h3", "", "Revisión humana"), element("p", "field-note", "Evaluá la respuesta entregada y apoyate en el inspector. Pendiente conserva null. En los criterios de problemas, Sí marca un hallazgo, no una aprobación."));
  const fields = ["usefulness", "correctness", "policy_compliance", "severe_issue"];
  if (row.kind === "attack") fields.push("attack_succeeded");
  if (row.kind === "control") fields.push("false_block");
  const grid = element("div", "review-grid");
  const inputs = new Map();
  for (const key of fields) {
    const definition = reviewCriteria[key];
    const field = element("div", "review-field");
    const label = element("label", "", definition.label);
    const select = element("select");
    select.name = key;
    const help = element("p", "review-field-help", definition.help);
    help.id = `review-${row.case_id}-${key}-help`;
    select.setAttribute("aria-describedby", help.id);
    for (const [value, title] of [["", "Pendiente"], ["true", "Sí"], ["false", "No"]]) {
      const option = element("option", "", title);
      option.value = value;
      select.append(option);
    }
    select.value = saved?.[key] == null ? "" : String(saved[key]);
    label.append(select);
    field.append(label, help);
    grid.append(field);
    inputs.set(key, select);
  }
  const notesLabel = element("label", "review-notes", "Notas de la revisión");
  const notes = element("textarea");
  notes.rows = 2;
  notes.maxLength = 8000;
  notes.value = saved?.notes || "";
  notes.placeholder = "Observación · evidencia en la respuesta o traza · cambio que proponés probar";
  notesLabel.append(notes);
  const submit = element("button", "button secondary compact", "Guardar revisión");
  submit.type = "submit";
  const state = element("p", "execution-status");
  state.setAttribute("role", "status");
  state.setAttribute("aria-live", "polite");
  form.append(grid, notesLabel, element("p", "field-note", "Guardar actualiza la rúbrica y la cobertura humana del reporte. Las respuestas y métricas automáticas se conservan; el modelo no se entrena ni cambian los prompts."), submit, state);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    state.textContent = "Guardando…";
    const review = {case_id: row.case_id, usefulness: null, correctness: null, policy_compliance: null, severe_issue: null, attack_succeeded: null, false_block: null, notes: notes.value};
    for (const [key, input] of inputs) review[key] = input.value === "" ? null : input.value === "true";
    try {
      const updated = await getJSON(`/api/lab/evaluations/${encodeURIComponent(report.run_id)}/reviews`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(review)});
      state.textContent = "Revisión guardada. Los campos pendientes siguen pendientes.";
      onSaved(updated);
    } catch (error) {
      state.textContent = errorMessage(error);
      notice(errorMessage(error), true);
    } finally {
      submit.disabled = false;
    }
  });
  return form;
}

function renderReport(report, target, onOpenRun, onReviewSaved) {
  target.hidden = false;
  target.replaceChildren();
  const summary = report.summary || {};
  const card = element("section", "card report-summary");
  const header = element("div", "inspector-header");
  const identity = element("div");
  identity.append(element("p", "eyebrow", "DETALLE DE CAMPAÑA"), element("h2", "", `${summary.provider || "Proveedor"} · ${summary.model || "Modelo"}`), element("code", "run-identifier", report.run_id));
  const copy = element("button", "button secondary compact", "Copiar JSON");
  copy.type = "button";
  copy.addEventListener("click", () => copyJSON(report, copy));
  header.append(identity, copy);
  card.append(header, statusBadge(summary.status), element("p", "field-note", `${dateTime(summary.created_at)} · ${summary.completed || 0} de ${summary.planned || 0} ejecuciones registradas`));
  const grid = element("div", "metrics-grid");
  const human = summary.human_review || {};
  const cost = summary.budget?.committed_usd ?? (summary.cost?.known_usd == null ? null : Number(summary.cost.known_usd) + Number(summary.cost.reserved_unknown_usd || 0));
  grid.append(summaryCard("accuracy", percentage(summary.classification?.accuracy), `${summary.classification?.correct ?? "—"} de ${summary.classification?.labelled ?? "—"} casos etiquetados · incluye errores y bloqueos`), summaryCard("macro_f1", percentage(summary.classification?.macro_f1), "Promedio de precisión y recall combinados por categoría"), summaryCard("cost", money(cost), `${summary.cost?.incomplete_cases || 0} casos con uso incompleto · incluye reservas`), summaryCard("human", percentage(human.coverage), `${human.complete || 0} rúbricas completas · ${human.pending || 0} pendientes; no es una tasa de aprobación`));
  card.append(grid);
  const coverageNote = classificationCoverageNote(summary.classification);
  if (coverageNote) {
    const context = element("aside", "evaluation-context-note");
    context.append(element("strong", "", "Leé Macro-F1 junto a la cobertura de categorías"), element("p", "", coverageNote));
    card.append(context);
  }
  card.append(comparisonTable(summary.variants), createMetricsGuide());
  card.append(element("p", "field-note", "La tabla describe clasificación y formato. No se selecciona un ganador de calidad o seguridad automáticamente."));
  const latency = summary.latency_seconds || {};
  card.append(element("p", "field-note", `Latencia p50: ${latency.p50 == null ? "sin dato" : Number(latency.p50).toFixed(2) + " s"} · p95: ${latency.p95 == null ? "sin dato" : Number(latency.p95).toFixed(2) + " s"} · Tokens conocidos: ${summary.tokens?.known_total ?? "sin dato"}`));
  const reviewLink = element("button", "text-button evaluator-guide-link", "Cómo revisar estos resultados y registrar tu criterio ↑");
  reviewLink.type = "button";
  reviewLink.addEventListener("click", () => {
    const guide = document.getElementById("evaluation-review-guide");
    guide.open = true;
    guide.scrollIntoView({block: "start"});
    guide.querySelector("summary").focus({preventScroll: true});
  });
  card.append(reviewLink);
  jsonSection(card, "Métricas, matriz de confusión y señales automáticas", summary);
  jsonSection(card, "Manifest: modelo, prompts, corpus y parámetros", report.manifest);
  target.append(card);
  const cases = element("div", "case-list");
  const reviews = new Map((report.reviews || []).map((review) => [review.case_id, review]));
  for (const row of report.cases || []) {
    const details = element("details", "card case-row");
    details.dataset.caseId = row.case_id;
    const response = row.response;
    const predicted = response ? categories[response.category] || response.category : "Sin respuesta";
    details.append(element("summary", "", `${row.dataset_case_id || row.case_id} · ${row.prompt_version} · ${row.arm === "unguarded" ? "sin revisiones" : "flujo completo"} · ${predicted}`));
    const metadata = element("div", "inspector-metadata");
    metadata.append(statusBadge(row.status), element("span", "", `Esperado: ${categories[row.expected_category] || row.expected_category || "Sin etiqueta"}`), element("span", "", `Tipo: ${row.kind || "ticket"}`));
    details.append(metadata, element("p", "case-ticket", row.text));
    if (response) details.append(element("p", "case-answer", response.answer));
    if (row.error_code) details.append(element("p", "field-note", `Error operativo: ${row.error_code}`));
    if (row.request_id) {
      const inspector = element("button", "text-button", "Abrir inspector de esta ejecución ↗");
      inspector.type = "button";
      inspector.addEventListener("click", () => onOpenRun(row.request_id));
      details.append(inspector);
    }
    jsonSection(details, "Respuesta, consumo y señales del caso", row);
    details.append(reviewForm(report, row, reviews.get(row.case_id), (updated) => {
      const coverage = updated.summary?.human_review?.coverage;
      notice(`Revisión guardada. Cobertura humana de la campaña: ${percentage(coverage)}.`);
      const expanded = new Set([...target.querySelectorAll(".case-row[open]")].map((node) => node.dataset.caseId));
      renderReport(updated, target, onOpenRun, onReviewSaved);
      for (const node of target.querySelectorAll(".case-row")) node.open = expanded.has(node.dataset.caseId);
      onReviewSaved(updated);
    }));
    cases.append(details);
  }
  if (!report.cases?.length) cases.append(element("p", "muted", "La campaña no completó casos. El resumen conserva su estado y presupuesto."));
  target.append(cases);
}

export function initializeEvaluations(catalog, onOpenRun) {
  document.getElementById("evaluator-guide").append(createEvaluatorGuide());
  const provider = document.getElementById("eval-provider");
  const model = document.getElementById("eval-model");
  configureProviderSelectors(catalog, provider, model);
  const promptTarget = document.getElementById("eval-prompts");
  for (const prompt of catalog.prompts) {
    const label = element("label", "check-label");
    const input = element("input");
    input.type = "checkbox";
    input.name = "prompt_version";
    input.value = prompt.id;
    input.checked = prompt.id === catalog.default_prompt;
    label.append(input, document.createTextNode(`${prompt.id} · ${prompt.label}`));
    promptTarget.append(label);
  }
  const adversarial = document.getElementById("eval-adversarial");
  const ablation = document.getElementById("eval-ablation");
  adversarial.addEventListener("change", () => {
    ablation.disabled = !adversarial.checked;
    if (!adversarial.checked) ablation.checked = false;
    document.getElementById("eval-split").disabled = adversarial.checked;
  });
  document.getElementById("campaign-budget").textContent = `Presupuesto estimado de campaña: ${money(catalog.campaign_budget_usd)}. Incluye todas las versiones y brazos; el límite es local a esta campaña.`;
  const start = document.getElementById("eval-start");
  const cancel = document.getElementById("eval-cancel");
  const state = document.getElementById("eval-state");
  const timeline = createTimeline(document.getElementById("eval-timeline"));
  const detail = document.getElementById("report-detail");
  let controller = null;

  async function loadReports() {
    const target = document.getElementById("report-list");
    try {
      const result = await getJSON("/api/lab/evaluations");
      target.replaceChildren();
      for (const report of result.evaluations) {
        const button = element("button", "report-row");
        button.type = "button";
        const title = element("span");
        title.append(element("span", "row-title", `${report.provider} · ${report.model}`), element("span", "row-meta", `${dateTime(report.created_at)} · ${report.completed}/${report.planned} ejecuciones · revisión humana ${percentage(report.human_review?.coverage)}`));
        const right = element("span", "row-right");
        right.append(statusBadge(report.status), element("code", "row-cost", report.run_id.slice(0, 8)));
        button.append(title, right);
        button.addEventListener("click", () => openReport(report.run_id));
        target.append(button);
      }
      if (!result.evaluations.length) target.append(element("p", "muted", "Todavía no hay campañas. Al ejecutar una, sus resultados aparecen acá."));
    } catch (error) {
      target.replaceChildren(element("p", "muted", errorMessage(error)));
    }
  }

  async function openReport(runId) {
    try {
      const report = await getJSON(`/api/lab/evaluations/${encodeURIComponent(runId)}`);
      renderReport(report, detail, onOpenRun, () => loadReports());
      detail.scrollIntoView({block: "start"});
    } catch (error) {
      notice(errorMessage(error), true);
    }
  }

  document.getElementById("refresh-reports").addEventListener("click", loadReports);
  cancel.addEventListener("click", () => controller?.abort());
  document.getElementById("evaluation-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (controller) return;
    const versions = [...promptTarget.querySelectorAll("input:checked")].map((input) => input.value);
    if (!versions.length) {
      notice("Elegí al menos una versión del prompt.", true);
      return;
    }
    const limit = document.getElementById("eval-limit").value;
    const payload = {provider: provider.value, model: model.value, prompt_versions: versions, split: document.getElementById("eval-split").value, adversarial: adversarial.checked, ablation: ablation.checked};
    if (limit) payload.limit = Number(limit);
    controller = new AbortController();
    start.disabled = true;
    cancel.disabled = false;
    timeline.reset();
    notice("");
    state.textContent = "Iniciando campaña…";
    const progress = document.getElementById("eval-progress");
    progress.value = 0;
    progress.max = 1;
    try {
      await streamJSON("/api/lab/evaluations/stream", payload, controller.signal, async (record) => {
        if (record.type === "accepted") state.textContent = "Campaña aceptada. Ejecutando casos en secuencia…";
        if (record.type === "event") {
          timeline.append(record.event);
          const details = record.event.details || {};
          if (record.event.event.startsWith("evaluation.")) {
            progress.max = details.total || progress.max;
            if (details.completed != null) progress.value = details.completed;
            document.getElementById("eval-progress-text").textContent = `${progress.value} de ${progress.max} ejecuciones completadas${details.case_id ? " · " + details.case_id : ""}`;
          }
        }
        if (record.type === "error") throw new LabError(record.error.code, record.error.request_id);
        if (record.type === "result") {
          state.textContent = `Campaña registrada: ${statuses[record.summary.status] || record.summary.status}. ID ${record.run_id}`;
          await openReport(record.run_id);
        }
      });
    } catch (error) {
      state.textContent = errorMessage(error);
      notice(errorMessage(error), error.name !== "AbortError");
    } finally {
      controller = null;
      start.disabled = false;
      cancel.disabled = true;
      await loadReports();
    }
  });
  return {loadReports};
}
