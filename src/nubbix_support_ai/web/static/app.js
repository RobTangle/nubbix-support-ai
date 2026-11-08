import {getJSON, LabError, readRun, streamJSON} from "./api.js";
import {initializeEvaluations} from "./evaluations.js";
import {createTimeline, renderInspection, renderResponse} from "./inspector.js";
import {createResponseProgress} from "./progress.js";
import {configureProviderSelectors, copyJSON, dateTime, element, errorMessage, metrics, money, notice, statusBadge} from "./ui.js";

const viewText = {test: ["DEL TICKET A LA RESPUESTA", "Soporte que podés inspeccionar.", "Probá un caso y seguí cada decisión del flujo, de principio a fin."], evaluations: ["EVIDENCIA ANTES DE ELEGIR", "Medí el flujo. Revisá la calidad.", "Compará versiones con el mismo proveedor, conservá los casos y sumá tu revisión."], history: ["MEMORIA DEL LABORATORIO", "Cada ejecución tiene una historia.", "Filtrá tus corridas locales y volvé a los prompts, respuestas y decisiones originales."]};
let evaluationView = null;

function switchView(view, {refresh = true} = {}) {
  if (!viewText[view]) view = "test";
  for (const section of document.querySelectorAll(".view")) section.hidden = section.id !== `view-${view}`;
  for (const button of document.querySelectorAll("[data-view]")) {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  for (const [index, id] of ["view-eyebrow", "view-title", "view-description"].entries()) document.getElementById(id).textContent = viewText[view][index];
  history.replaceState(null, "", `#${view}`);
  if (refresh && view === "history") loadHistory();
  if (refresh && view === "evaluations") evaluationView?.loadReports();
}

async function openHistoryRun(runId, origin = null) {
  const originTop = origin?.getBoundingClientRect().top;
  switchView("history");
  const target = document.getElementById("history-detail");
  const inspector = element("div");
  inspector.append(element("p", "muted", "Cargando inspector…"));
  target.replaceChildren(inspector);
  target.hidden = false;
  if (origin) {
    const bar = element("div", "inspector-return");
    const back = element("button", "button secondary compact", "← Volver a la evaluación");
    back.type = "button";
    back.addEventListener("click", () => {
      switchView("evaluations", {refresh: false});
      if (origin.isConnected && !origin.closest("[hidden]")) {
        window.scrollTo(0, window.scrollY + origin.getBoundingClientRect().top - originTop);
        origin.focus({preventScroll: true});
      } else {
        const heading = document.getElementById("report-list-title");
        heading.focus({preventScroll: true});
        heading.scrollIntoView({block: "start"});
      }
    });
    bar.append(back);
    target.prepend(bar);
    target.scrollIntoView({block: "start"});
    back.focus({preventScroll: true});
  }
  try {
    const run = await readRun(runId);
    if (!inspector.isConnected) return;
    renderInspection(run, inspector, true);
    if (!target.closest("[hidden]")) target.scrollIntoView({block: "start"});
  } catch (error) {
    if (!inspector.isConnected) return;
    inspector.replaceChildren(element("p", "muted", errorMessage(error)));
    if (!target.closest("[hidden]")) notice(errorMessage(error), true);
  }
}

async function loadHistory() {
  const params = new URLSearchParams();
  for (const [id, key] of [["history-provider", "provider"], ["history-prompt", "prompt_version"], ["history-status", "status"]]) {
    const value = document.getElementById(id).value;
    if (value) params.set(key, value);
  }
  const target = document.getElementById("history-list");
  try {
    const result = await getJSON(`/api/lab/runs?${params}`);
    target.replaceChildren();
    for (const run of result.runs) {
      const button = element("button", "history-row");
      button.type = "button";
      const description = element("span");
      description.append(element("span", "row-title", run.ticket.length > 110 ? run.ticket.slice(0, 110) + "…" : run.ticket), element("span", "row-meta", `${dateTime(run.timestamp)} · ${run.provider} · ${run.model} · ${run.prompt_version}`));
      const right = element("span", "row-right");
      right.append(statusBadge(run.status), element("span", "row-cost", money(run.metrics?.estimated_cost_usd)));
      button.append(description, right);
      button.addEventListener("click", () => openHistoryRun(run.request_id));
      target.append(button);
    }
    if (!result.runs.length) target.append(element("p", "muted", "No hay ejecuciones para estos filtros. Probá otro filtro o analizá un primer ticket."));
  } catch (error) {
    target.replaceChildren(element("p", "muted", errorMessage(error)));
  }
}

function initializeTicket(catalog) {
  const provider = document.getElementById("test-provider");
  const model = document.getElementById("test-model");
  const prompt = document.getElementById("test-prompt");
  configureProviderSelectors(catalog, provider, model);
  prompt.replaceChildren(...catalog.prompts.map((item) => {
    const option = element("option", "", `${item.id} · ${item.label}${item.id === catalog.default_prompt ? " · default" : ""}`);
    option.value = item.id;
    return option;
  }));
  prompt.value = catalog.default_prompt;
  const ticket = document.getElementById("ticket");
  const counter = document.getElementById("ticket-count");
  ticket.addEventListener("input", () => { counter.textContent = `${[...ticket.value].length.toLocaleString("es-AR")} / 8.000`; });
  for (const button of document.querySelectorAll("[data-ticket]")) button.addEventListener("click", () => {
    ticket.value = button.dataset.ticket;
    ticket.dispatchEvent(new Event("input"));
    ticket.focus();
  });
  const start = document.getElementById("run-button");
  const cancel = document.getElementById("cancel-button");
  const state = document.getElementById("run-state");
  const timeline = createTimeline(document.getElementById("test-timeline"), (count) => { document.getElementById("event-count").textContent = `${count} EVENTOS`; });
  const inspector = document.getElementById("run-inspector");
  const progress = createResponseProgress(document.getElementById("response-progress"), () => cancel.click());
  let controller = null;
  let response = null;
  document.getElementById("copy-json").addEventListener("click", (event) => copyJSON(response, event.currentTarget));
  cancel.addEventListener("click", () => {
    if (!controller) return;
    progress.cancel();
    cancel.disabled = true;
    state.textContent = "Cancelando el trabajo pendiente…";
    document.getElementById("response-status").textContent = "CANCELANDO";
    controller.abort();
  });
  document.getElementById("ticket-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (controller) return;
    if (!ticket.value.trim()) {
      notice("Ingresá un mensaje para analizar.", true);
      ticket.focus();
      return;
    }
    if ([...ticket.value.trim()].length > 8000) {
      notice("El mensaje admite hasta 8.000 puntos Unicode.", true);
      ticket.focus();
      return;
    }
    const payload = {ticket: ticket.value, provider: provider.value, model: model.value, prompt_version: prompt.value};
    controller = new AbortController();
    start.disabled = true;
    cancel.disabled = false;
    response = null;
    timeline.reset();
    metrics(document.getElementById("run-metrics"));
    document.getElementById("run-identifier").textContent = "";
    document.getElementById("response-empty").hidden = true;
    document.getElementById("response-content").hidden = true;
    document.getElementById("response-status").textContent = "ANALIZANDO";
    document.getElementById("response-status").className = "small-tag status-running";
    progress.start();
    inspector.replaceChildren(element("p", "muted", "El inspector se guarda durante la ejecución. El resultado final estará disponible al terminar."));
    state.textContent = "Iniciando ejecución…";
    notice("");
    let runId = null;
    let cancelled = false;
    try {
      await streamJSON("/api/lab/runs/stream", payload, controller.signal, async (record) => {
        if (record.type === "accepted") state.textContent = "Ticket aceptado. Siguiendo las etapas en vivo…";
        if (record.type === "event") {
          progress.append(record.event);
          timeline.append(record.event);
          runId = record.event.request_id;
          document.getElementById("run-identifier").textContent = runId;
        }
        if (record.type === "error") throw new LabError(record.error.code, record.error.request_id);
        if (record.type === "result") {
          response = record.response;
          runId = record.run_id;
          progress.finish(record.status);
          renderResponse(record.response, record.status);
          metrics(document.getElementById("run-metrics"), record.metrics);
          state.textContent = "Ejecución terminada y registrada en el historial.";
        }
      });
    } catch (error) {
      cancelled = error.name === "AbortError";
      state.textContent = errorMessage(error);
      notice(errorMessage(error), error.name !== "AbortError");
      response = null;
      document.getElementById("response-content").hidden = true;
      progress.finish(cancelled ? "cancelled" : "error");
      const badge = statusBadge(cancelled ? "cancelled" : "error");
      badge.id = "response-status";
      document.getElementById("response-status").replaceWith(badge);
      if (error.requestId) runId = error.requestId;
    } finally {
      cancel.disabled = true;
      if (runId) {
        try {
          const run = await readRun(runId, cancelled);
          renderInspection(run, inspector);
          metrics(document.getElementById("run-metrics"), run.metrics || {});
          timeline.reset();
          (run.events || []).forEach((event) => timeline.append(event));
          if (run.status === "running") inspector.prepend(element("p", "field-note", "Este snapshot se tomó durante el cierre. Consultá Historial para ver el estado final."));
        } catch (error) {
          inspector.replaceChildren(element("p", "muted", errorMessage(error)));
        }
      } else {
        inspector.replaceChildren(element("p", "muted", "No se recibió un ID de ejecución. Si la conexión se interrumpió, verificá el historial antes de reintentar."));
      }
      controller = null;
      start.disabled = false;
    }
  });
}

async function initialize() {
  for (const button of document.querySelectorAll("[data-view]")) button.addEventListener("click", () => switchView(button.dataset.view));
  document.getElementById("history-filters").addEventListener("submit", (event) => {
    event.preventDefault();
    loadHistory();
  });
  metrics(document.getElementById("run-metrics"));
  try {
    const catalog = await getJSON("/api/lab/catalog");
    const available = catalog.providers.filter((item) => item.available);
    const configuration = document.getElementById("configuration-state");
    configuration.textContent = available.length ? `${available.length} proveedor${available.length === 1 ? "" : "es"} disponible${available.length === 1 ? "" : "s"}` : "Configurá una clave para ejecutar";
    configuration.classList.toggle("unavailable", !available.length);
    initializeTicket(catalog);
    evaluationView = initializeEvaluations(catalog, openHistoryRun);
    for (const provider of catalog.providers) {
      const option = element("option", "", provider.label);
      option.value = provider.id;
      document.getElementById("history-provider").append(option);
    }
    for (const prompt of catalog.prompts) {
      const option = element("option", "", `${prompt.id} · ${prompt.label}`);
      option.value = prompt.id;
      document.getElementById("history-prompt").append(option);
    }
    document.getElementById("history-location").textContent = `Hasta 100 ejecuciones recientes. Archivos locales en ${catalog.data_directory}. Cerrar el servidor interrumpe el trabajo pendiente; no se reanuda automáticamente.`;
    document.getElementById("ticket-budget").textContent = `Presupuesto estimado por ticket: ${money(catalog.ticket_budget_usd)} · tarifas verificadas ${catalog.tariff_checked_on}. Uso desconocido conserva su reserva.`;
    switchView(location.hash.slice(1) || "test");
  } catch (error) {
    document.getElementById("configuration-state").textContent = "No se pudo cargar el catálogo";
    document.getElementById("run-button").disabled = true;
    document.getElementById("eval-start").disabled = true;
    notice(errorMessage(error), true);
  }
}

initialize();
