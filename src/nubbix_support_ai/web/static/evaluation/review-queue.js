import {getJSON} from "../api.js";
import {reviewCriteria} from "../evaluation-help.js";
import {element, errorMessage, jsonSection, statusBadge} from "../ui.js";
import {actionList, caseKinds, returnedCategory} from "./case-content.js";
import {assessCase, filterCases, reviewFields, variantLabel} from "./view-data.js";

const views = {priority: "Alertas pendientes", alerts: "Con alertas", pending: "Revisión pendiente", all: "Todos"};
const reviewLabels = {pending: "Sin revisar", partial: "Revisión parcial", complete: "Revisado"};

function updateCaseSummary(entry) {
  const {row, summary, node, expectedCategory} = entry;
  node.classList.toggle("has-alert", entry.alerts.length > 0);
  const identity = element("span", "case-identity");
  identity.append(element("strong", "case-id", row.dataset_case_id || row.case_id),
    element("span", "case-variant", variantLabel(entry.variant)),
    element("span", `case-review-status review-${entry.reviewStatus}`, reviewLabels[entry.reviewStatus]));
  if (caseKinds[row.kind]) identity.append(element("span", "case-kind", caseKinds[row.kind]));
  const outcomes = element("span", "case-outcomes");
  const expected = element("span", "case-outcome");
  expected.append(element("span", "case-outcome-label", "Categoría esperada"),
    element(expectedCategory ? "code" : "span", "case-category-value", expectedCategory || "Sin etiqueta"));
  outcomes.append(expected, returnedCategory(entry));
  summary.replaceChildren(identity, element("span", "case-preview", row.text), outcomes);
  if (entry.alerts.length) {
    const flags = element("span", "case-flags");
    for (const alert of entry.alerts) flags.append(element("span", "case-flag", alert));
    summary.append(flags);
  }
}

function reviewForm(entry, onSubmit) {
  const {row, review: saved} = entry;
  const form = element("form", "review-form inspection-section");
  form.append(element("h3", "", "Revisión humana"), element("p", "field-note", "Evaluá la respuesta entregada y apoyate en el inspector. En los criterios de problemas, Sí marca un hallazgo."));
  const grid = element("div", "review-grid");
  const inputs = new Map();
  for (const key of reviewFields(row.kind)) {
    const definition = reviewCriteria[key];
    const field = element("div", "review-field");
    const select = element("select");
    select.id = `review-${row.case_id}-${key}`;
    select.name = key;
    const label = element("label", "", definition.label);
    label.htmlFor = select.id;
    const help = element("p", "review-field-help", definition.help);
    help.id = `${select.id}-help`;
    select.setAttribute("aria-describedby", help.id);
    for (const [value, title] of [["", "Pendiente"], ["true", "Sí"], ["false", "No"]]) {
      const option = element("option", "", title);
      option.value = value;
      select.append(option);
    }
    select.value = saved[key] == null ? "" : String(saved[key]);
    field.append(label, select, help);
    grid.append(field);
    inputs.set(key, select);
  }
  const notesLabel = element("label", "review-notes", "Notas de la revisión");
  const notes = element("textarea");
  notes.rows = 2;
  notes.maxLength = 8000;
  notes.value = saved.notes || "";
  notes.placeholder = "Observación · evidencia en la respuesta o traza · cambio que proponés probar";
  notesLabel.append(notes);
  const submit = element("button", "button secondary compact", "Guardar revisión");
  submit.type = "submit";
  const state = element("p", "execution-status");
  state.setAttribute("role", "status");
  form.append(grid, notesLabel, element("p", "field-note", "Guardar actualiza la rúbrica y la cobertura humana del reporte."), submit, state);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const review = {case_id: row.case_id, notes: notes.value};
    for (const [key, input] of inputs) review[key] = input.value === "" ? null : input.value === "true";
    onSubmit(entry, review, submit, state);
  });
  return form;
}

function caseBody(entry, onOpenRun, onSubmit) {
  const {row} = entry;
  const body = element("div", "case-body");
  const metadata = element("div", "inspector-metadata");
  metadata.append(statusBadge(row.status));
  body.append(metadata, element("h3", "", "Consulta"), element("p", "case-ticket", row.text));
  body.append(element("h3", "", "Respuesta entregada"), element("p", "case-answer", row.response?.answer ?? "Sin respuesta entregada."));
  if (row.error_code) body.append(element("p", "field-note", `Error operativo: ${row.error_code}`));
  const actions = element("div", "case-evidence");
  actions.append(actionList("Acciones esperadas", row.expected_actions, "Sin acciones de referencia."),
    actionList("Acciones observadas", row.response?.actions, "Sin acciones sugeridas."));
  body.append(actions);
  if (row.request_id) {
    const inspector = element("button", "text-button", "Abrir inspector de esta ejecución ↗");
    inspector.type = "button";
    inspector.addEventListener("click", () => onOpenRun(row.request_id));
    body.append(inspector);
  }
  jsonSection(body, "Respuesta, consumo y señales del caso", row);
  body.append(reviewForm(entry, onSubmit));
  return body;
}

export function createReviewQueue(report, onOpenRun, onSaved) {
  const reviews = new Map((report.reviews || []).map((review) => [review.case_id, review]));
  const entries = (report.cases || []).map((row) => assessCase(row, reviews.get(row.case_id)));
  const section = element("section", "review-queue");
  section.setAttribute("aria-labelledby", "evaluation-cases-title");
  const heading = element("h2", "", "Casos de la campaña");
  heading.id = "evaluation-cases-title";
  heading.tabIndex = -1;
  const back = element("button", "text-button case-back", "Volver a campañas ↑");
  back.type = "button";
  back.addEventListener("click", () => {
    const campaignHeading = document.getElementById("report-list-title");
    campaignHeading.focus({preventScroll: true});
    campaignHeading.scrollIntoView({block: "start"});
  });
  const toolbarHeader = element("div", "review-toolbar-header");
  toolbarHeader.append(heading, back);
  const shortcut = element("button", "button primary compact review-shortcut");
  shortcut.type = "button";
  shortcut.hidden = entries.length === 0;
  shortcut.addEventListener("click", () => {
    heading.focus({preventScroll: true});
    section.scrollIntoView({block: "start"});
  });
  const toolbar = element("div", "card review-toolbar");
  const filters = element("div", "case-filters");
  const searchLabel = element("label", "", "Buscar caso o texto del ticket");
  const search = element("input");
  search.type = "search";
  search.placeholder = "Ej. dev-other-04 o antigüedad";
  searchLabel.append(search);
  const variantLabelNode = element("label", "", "Variante");
  const variant = element("select");
  const all = element("option", "", "Todas las variantes");
  all.value = "";
  variant.append(all);
  for (const name of [...new Set(entries.map((entry) => entry.variant))].sort()) {
    const option = element("option", "", variantLabel(name));
    option.value = name;
    variant.append(option);
  }
  variantLabelNode.append(variant);
  variantLabelNode.hidden = variant.options.length < 3;
  const alertLabel = element("label", "", "Motivo de alerta");
  const alert = element("select");
  alert.id = "evaluation-alert-reason";
  alertLabel.htmlFor = alert.id;
  alertLabel.append(alert);
  updateAlertOptions();
  filters.append(searchLabel, variantLabelNode, alertLabel);
  const tabs = element("div", "case-views");
  tabs.setAttribute("role", "group");
  tabs.setAttribute("aria-label", "Mostrar casos");
  const buttons = new Map();
  let mode = entries.some((entry) => entry.alerts.length && entry.reviewStatus !== "complete") ? "priority" : "all";
  for (const key of Object.keys(views)) {
    const button = element("button", "case-view");
    button.type = "button";
    button.addEventListener("click", () => {
      mode = key;
      refresh();
    });
    buttons.set(key, button);
    tabs.append(button);
  }
  const count = element("p", "case-count");
  count.setAttribute("role", "status");
  toolbar.append(toolbarHeader, element("p", "field-note", "El color indica si la categoría coincide. Usá las alertas para localizar bloqueos, errores y otros casos que requieren revisión."),
    filters, tabs, count);
  const empty = element("p", "case-empty");
  const list = element("div", "case-list");
  section.append(toolbar, empty, list);
  let saving = false;
  for (const entry of entries) {
    const node = element("details", "card case-row");
    node.dataset.caseId = entry.row.case_id;
    const summary = element("summary", "case-summary");
    Object.assign(entry, {node, summary});
    updateCaseSummary(entry);
    node.append(summary);
    node.addEventListener("toggle", () => {
      if (node.open && node.childElementCount === 1) node.append(caseBody(entry, onOpenRun, save));
    });
    list.append(node);
  }
  search.addEventListener("input", () => refresh());
  variant.addEventListener("change", () => refresh());
  alert.addEventListener("change", () => refresh());
  refresh();
  return {section, shortcut};

  function updateAlertOptions() {
    const selected = alert.value;
    const reasons = new Set(entries.flatMap((entry) => entry.alerts));
    if (selected) reasons.add(selected);
    const allReasons = element("option", "", "Todos los motivos");
    allReasons.value = "";
    alert.replaceChildren(allReasons, ...[...reasons].sort((a, b) => a.localeCompare(b, "es")).map((reason) => element("option", "", reason)));
    alert.value = selected;
    alertLabel.hidden = !reasons.size;
  }

  function refresh(message = "") {
    const {rows, counts} = filterCases(entries, {mode, query: search.value, variant: variant.value, alert: alert.value});
    const visible = new Set(rows);
    for (const entry of entries) entry.node.hidden = !visible.has(entry);
    for (const [key, button] of buttons) {
      button.textContent = `${views[key]} (${counts[key]})`;
      button.setAttribute("aria-pressed", String(key === mode));
    }
    count.textContent = `${message}Mostrando ${rows.length} de ${entries.length} ejecuciones.`;
    const priority = entries.filter((entry) => entry.alerts.length && entry.reviewStatus !== "complete").length;
    shortcut.textContent = priority ? `Ver casos · ${priority} alertas pendientes ↓` : "Ver casos de la campaña ↓";
    empty.hidden = rows.length > 0;
    empty.textContent = entries.length ? "No hay casos para estos filtros. Probá con Todos o ajustá la búsqueda." :
      "La campaña no completó casos. El resumen conserva su estado y presupuesto.";
    return rows;
  }

  async function save(entry, review, submit, state) {
    if (saving) {
      state.textContent = "Esperá a que termine el guardado en curso.";
      return;
    }
    saving = true;
    submit.setAttribute("aria-disabled", "true");
    state.textContent = "Guardando…";
    try {
      const path = `/api/lab/evaluations/${encodeURIComponent(report.run_id)}/reviews`;
      const updated = await getJSON(path, {method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(review)});
      if (!section.isConnected) return;
      const hadFocus = entry.node.contains(document.activeElement);
      Object.assign(entry, assessCase(entry.row, updated.reviews.find((item) => item.case_id === review.case_id)));
      updateCaseSummary(entry);
      updateAlertOptions();
      state.textContent = "Revisión guardada.";
      const visible = refresh("Revisión guardada. ");
      if (entry.node.hidden && hadFocus) (visible[0]?.summary || buttons.get(mode)).focus();
      onSaved(updated);
    } catch (error) {
      state.textContent = errorMessage(error);
    } finally {
      saving = false;
      submit.removeAttribute("aria-disabled");
    }
  }
}
