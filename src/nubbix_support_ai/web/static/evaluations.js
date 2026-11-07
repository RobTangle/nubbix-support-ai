import {getJSON, LabError, streamJSON} from "./api.js";
import {createTimeline} from "./inspector.js";
import {classificationCoverageNote, createEvaluatorGuide, createMetricsGuide, evaluationMetrics} from "./evaluation-help.js";
import {createCampaignCard} from "./evaluation/campaign-cards.js";
import {createReviewQueue} from "./evaluation/review-queue.js";
import {orderCampaigns, percentage, variantLabel} from "./evaluation/view-data.js";
import {configureProviderSelectors, copyJSON, dateTime, element, errorMessage, jsonSection, money, notice, statusBadge, statuses} from "./ui.js";

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
    const nameCell = element("th", "", variantLabel(name));
    nameCell.scope = "row";
    row.append(nameCell);
    for (const value of [percentage(variant.classification?.accuracy), percentage(variant.classification?.macro_f1), percentage(variant.json_validity?.generation_valid_rate), `${variant.errors || 0} / ${variant.blocked || 0}`, percentage(variant.human_review?.coverage)]) row.append(element("td", "", value));
    body.append(row);
  }
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

function reportSummary(report, shortcut) {
  const summary = report.summary || {};
  const card = element("section", "card report-summary");
  const header = element("div", "inspector-header");
  const identity = element("div");
  identity.append(element("p", "eyebrow", "DETALLE DE CAMPAÑA"), element("h2", "", `${summary.provider || "Proveedor"} · ${summary.model || "Modelo"}`), element("code", "run-identifier", report.run_id));
  const copy = element("button", "button secondary compact", "Copiar JSON");
  copy.type = "button";
  copy.addEventListener("click", () => copyJSON(report, copy));
  header.append(identity, copy);
  const meta = element("div", "report-meta");
  meta.append(statusBadge(summary.status), element("p", "field-note", `${dateTime(summary.created_at)} · ${summary.completed || 0} de ${summary.planned || 0} ejecuciones registradas`));
  meta.append(shortcut);
  card.append(header, meta);
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
  return card;
}

function renderReport(report, target, onOpenRun, onReviewSaved) {
  const overview = element("div");
  const queue = createReviewQueue(report, onOpenRun, (updated) => {
    overview.replaceChildren(reportSummary(updated, queue.shortcut));
    onReviewSaved();
  });
  overview.append(reportSummary(report, queue.shortcut));
  target.replaceChildren(overview, queue.section);
  target.hidden = false;
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

  const reportList = document.getElementById("report-list");
  const reportOrder = document.getElementById("report-order");
  let reports = [];
  let selectedRun = null;
  let listRequest = 0;
  let detailRequest = 0;

  function renderCampaigns() {
    const ordered = orderCampaigns(reports, reportOrder.value);
    const cards = ordered.map((report) => createCampaignCard(report, report.run_id === selectedRun, openReport));
    if (!cards.length) cards.push(element("p", "muted", "Todavía no hay campañas. Al ejecutar una, sus resultados aparecen acá."));
    reportList.replaceChildren(...cards);
  }

  async function loadReports() {
    const request = ++listRequest;
    try {
      const result = await getJSON("/api/lab/evaluations");
      if (request !== listRequest) return;
      reports = result.evaluations;
      renderCampaigns();
    } catch (error) {
      if (request === listRequest) reportList.replaceChildren(element("p", "muted", errorMessage(error)));
    }
  }

  async function openReport(runId) {
    const request = ++detailRequest;
    try {
      const report = await getJSON("/api/lab/evaluations/" + encodeURIComponent(runId));
      if (request !== detailRequest) return;
      selectedRun = runId;
      renderReport(report, detail, onOpenRun, loadReports);
      renderCampaigns();
      const heading = detail.querySelector("h2");
      heading.tabIndex = -1;
      heading.focus({preventScroll: true});
      detail.scrollIntoView({block: "start"});
    } catch (error) {
      if (request === detailRequest) notice(errorMessage(error), true);
    }
  }

  reportOrder.addEventListener("change", renderCampaigns);
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
