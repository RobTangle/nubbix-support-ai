import {getJSON} from "../api.js";
import {dateTime, element, errorMessage, statuses} from "../ui.js";
import {actionList, caseKinds, caseOutcome, responseHeading} from "./case-content.js";
import {createCaseFlow} from "./case-flow.js";
import {compareVariants} from "./comparison-data.js";
import {percentage, variantLabel} from "./view-data.js";

const sides = ["A", "B"];
const filters = [
  ["outcomes", "Cambios de categoría o estado", (pair) => pair.outcomeChanged],
  ["only-a", "Acierta solo A", (pair) => pair.exclusiveHit === "A"],
  ["only-b", "Acierta solo B", (pair) => pair.exclusiveHit === "B"],
  ["answers", "Cambios de texto o acciones", (pair) => pair.answerChanged],
  ["all", "Todos los tickets", () => true],
];

function option(label, value) {
  const node = element("option", "", label);
  node.value = value;
  return node;
}

function metricsTable({statsA, statsB, pairs}) {
  const table = element("table", "comparison-table paired-metrics");
  const header = table.createTHead().insertRow();
  for (const label of ["En común", "Opción A", "Opción B"]) {
    const cell = element("th", "", label);
    cell.scope = "col";
    header.append(cell);
  }
  const accuracy = (stats) => stats.labelled ? `${percentage(stats.correct / stats.labelled)} · ${stats.correct}/${stats.labelled}` : "Sin dato";
  const exclusive = (side) => pairs.filter(({exclusiveHit}) => exclusiveHit === side).length;
  const body = table.createTBody();
  for (const [label, a, b] of [
    ["Exactitud", accuracy(statsA), accuracy(statsB)],
    ["Acierta solo esta opción", exclusive("A"), exclusive("B")],
    ["Bloqueos", statsA.blocked, statsB.blocked],
    ["Errores", statsA.errors, statsB.errors],
  ]) {
    const row = body.insertRow();
    const name = element("th", "", label);
    name.scope = "row";
    row.append(name, element("td", "", a), element("td", "", b));
  }
  return table;
}

function comparisonCase(pair, onOpenRun) {
  const {a, b, exclusiveHit} = pair;
  const item = element("details", "card case-row paired-case");
  const heading = element("summary", "case-summary");
  const identity = element("span", "case-identity");
  const expectedLabel = a.row.kind === "attack" ? "Intención de referencia" : "Categoría esperada";
  identity.append(element("strong", "case-id", a.row.dataset_case_id),
    element("span", "case-variant", expectedLabel), element("code", "", a.expectedCategory || "Sin etiqueta"));
  if (caseKinds[a.row.kind]) identity.append(element("span", "case-kind", caseKinds[a.row.kind]));
  if (exclusiveHit) identity.append(element("span", "case-kind", `Acierta solo ${exclusiveHit}`));
  const outcomes = element("span", "case-outcomes");
  const entries = [a, b];
  const renderOutcomes = () => outcomes.replaceChildren(...entries.map((entry, index) => {
    const status = entry.row.status === "escalated" ? "Confianza baja" : statuses[entry.row.status] || "Sin estado";
    const outcomeLabel = entry.row.kind === "attack" ? "Resultado de seguridad" : status;
    return caseOutcome(entry, `${sides[index]} · ${outcomeLabel}`);
  }));
  renderOutcomes();
  heading.append(identity, element("span", "case-preview", a.row.text), outcomes);
  item.append(heading);
  item.addEventListener("toggle", () => {
    if (!item.open || item.childElementCount > 1) return;
    const body = element("div", "case-body");
    body.append(element("h3", "", "Consulta"), element("p", "case-ticket", a.row.text));
    const answers = element("div", "case-evidence");
    for (const [index, {row}] of entries.entries()) {
      const side = sides[index];
      const answer = element("div", "paired-answer");
      answer.append(responseHeading(row, `Respuesta ${side}`), element("p", "case-answer", row.response?.answer ?? "Sin respuesta entregada."));
      if (row.error_code) answer.append(element("p", "field-note", `Código de error · ${row.error_code}`));
      answer.append(actionList("Acciones sugeridas", row.response?.actions, "Sin acciones sugeridas."));
      answer.append(createCaseFlow(row, {collapsible: true, onResolved: renderOutcomes}));
      if (row.request_id) {
        const inspector = element("button", "text-button paired-inspector", `Abrir inspector ${side} ↗`);
        inspector.type = "button";
        inspector.addEventListener("click", () => onOpenRun(row.request_id, inspector));
        answer.append(inspector);
      }
      answers.append(answer);
    }
    body.append(answers);
    item.append(body);
  });
  return item;
}

function renderComparison(output, result, onOpenRun) {
  const {pairs, onlyA, onlyB, categories, changes, statsA, statsB} = result;
  const overview = element("div", "paired-overview");
  const overviewHeading = element("div", "paired-overview-heading");
  overviewHeading.append(element("h3", "", `${pairs.length} ${pairs.length === 1 ? "ticket" : "tickets"} en común`));
  overview.append(overviewHeading);
  if (onlyA || onlyB) overview.append(element("p", "field-note", `Solo A · ${onlyA} | Solo B · ${onlyB}. Las métricas se calculan con los tickets en común.`));
  if (categories.length) overview.append(element("p", "field-note", `Categorías cubiertas · ${categories.join(" · ")}`));
  if (changes.length) overview.append(element("p", "field-note", `Condiciones que cambian · ${changes.join(" · ")}`));
  output.replaceChildren(overview);
  if (!pairs.length) {
    overview.append(element("p", "case-empty", "Elegí variantes con tickets del mismo corpus, texto y referencia para obtener una comparación."));
    return;
  }
  const delta = statsB.correct - statsA.correct;
  if (statsA.labelled) {
    const difference = delta ? `Opción ${delta > 0 ? "B" : "A"} acertó ${Math.abs(delta)} más · ${(Math.abs(delta) * 100 / statsA.labelled).toFixed(1)} puntos porcentuales de diferencia` : "Igual exactitud en los tickets en común";
    overview.append(element("p", "paired-difference", difference));
  }
  const table = element("div", "table-scroll paired-table-scroll");
  table.append(metricsTable(result));
  const bar = element("div", "paired-case-toolbar");
  const identity = element("div");
  const casesHeading = element("h3", "", "Comparación por ticket");
  casesHeading.tabIndex = -1;
  identity.append(casesHeading, element("p", "field-note", "Abrí un ticket para leer las dos respuestas y sus acciones."));
  const jump = element("button", "text-button paired-jump", "Ver tickets en común ↓");
  jump.type = "button";
  jump.addEventListener("click", () => {
    casesHeading.focus({preventScroll: true});
    bar.scrollIntoView({block: "start"});
  });
  overviewHeading.append(jump);
  const label = element("label", "", "Mostrar tickets");
  label.htmlFor = "paired-case-filter";
  const select = element("select");
  select.id = label.htmlFor;
  const items = pairs.map((pair) => ({pair, node: comparisonCase(pair, onOpenRun)}));
  const groups = new Map();
  for (const [key, title, predicate] of filters) {
    const visible = new Set(items.filter(({pair}) => predicate(pair)));
    groups.set(key, visible);
    select.append(option(`${title} (${visible.size})`, key));
  }
  select.value = groups.get("outcomes").size ? "outcomes" : (groups.get("answers").size ? "answers" : "all");
  label.append(select);
  bar.append(identity, label);
  const list = element("div", "case-list");
  list.append(...items.map(({node}) => node));
  const empty = element("p", "case-empty", "No hay tickets en este filtro.");
  const refresh = () => {
    const visible = groups.get(select.value);
    for (const item of items) item.node.hidden = !visible.has(item);
    empty.hidden = visible.size > 0;
  };
  select.addEventListener("change", refresh);
  refresh();
  output.append(table, bar, empty, list);
}

export function createComparisonPanel(section, onOpenRun) {
  const heading = section.querySelector("h2");
  const output = section.querySelector("#comparison-output");
  const state = section.querySelector("#comparison-state");
  const submit = section.querySelector("#comparison-submit");
  const selectors = ["a", "b"].map((side) => ({
    campaign: section.querySelector(`#comparison-${side}-campaign`),
    variant: section.querySelector(`#comparison-${side}-variant`),
    meta: section.querySelector(`#comparison-${side}-meta`),
  }));
  let campaigns = new Map();
  let pending = null;
  let trigger = null;
  for (const [index, side] of selectors.entries()) {
    side.campaign.addEventListener("change", () => {
      const other = selectors[1 - index];
      if (side.campaign.value === other.campaign.value) {
        const different = campaigns.get(side.campaign.value)?.variantNames.find((name) => name !== other.variant.value);
        setVariant(side, different);
      } else {
        setVariant(side, other.variant.value, side.variant.value);
      }
      reset();
    });
    side.variant.addEventListener("change", reset);
  }
  section.querySelector("form").addEventListener("submit", (event) => {
    event.preventDefault();
    void compare();
  });
  section.querySelector("#comparison-close").addEventListener("click", () => {
    if (pending) reset();
    section.hidden = true;
    (trigger?.isConnected ? trigger : document.getElementById("open-comparison")).focus();
  });
  return {open, setReports};

  function selection() {
    return selectors.map(({campaign, variant}) => ({id: campaign.value, variant: variant.value}));
  }

  function canCompare() {
    const [a, b] = selection();
    return Boolean(a.variant && b.variant && (a.id !== b.id || a.variant !== b.variant));
  }

  function reset() {
    pending?.abort();
    pending = null;
    output.replaceChildren();
    submit.disabled = !canCompare();
    state.textContent = "";
    if (!campaigns.size) state.textContent = "Las campañas con ejecuciones registradas aparecen acá.";
    else if (selectors.some(({variant}) => !variant.value)) state.textContent = "Elegí una campaña y una variante para cada opción.";
    else if (submit.disabled) state.textContent = "Elegí dos variantes distintas o una variante de otra campaña.";
  }

  function setVariant(side, ...preferred) {
    const report = campaigns.get(side.campaign.value);
    const variants = report?.variantNames || [];
    side.variant.replaceChildren(...variants.map((name) => option(variantLabel(name), name)));
    side.variant.disabled = !variants.length;
    if (variants.length) side.variant.value = preferred.find((name) => variants.includes(name)) || variants[0];
    else side.variant.append(option("Elegí una campaña primero", ""));
    side.meta.textContent = report ? `${report.provider} · ${dateTime(report.created_at)} · ${statuses[report.status] || report.status}` : "";
  }

  function setReports(reports) {
    const previous = selection();
    const previousCampaigns = campaigns;
    campaigns = new Map();
    for (const report of reports) {
      const names = Object.keys(report.variants || {}).sort((a, b) => a.localeCompare(b, "es", {numeric: true}));
      const variantNames = names.filter((name) => name.endsWith(":full")).concat(names.filter((name) => !name.endsWith(":full")));
      if (variantNames.length) campaigns.set(report.run_id, {...report, variantNames});
    }
    for (const [index, side] of selectors.entries()) {
      const options = [option("Elegí una campaña", "")];
      for (const report of campaigns.values()) {
        const corpus = (report.splits || []).join(" / ") || "Corpus sin dato";
        options.push(option(`${report.model} · ${corpus} · ${report.completed}/${report.planned} · ${report.run_id.slice(0, 8)}`, report.run_id));
      }
      side.campaign.replaceChildren(...options);
      const {id, variant} = previous[index];
      side.campaign.value = campaigns.has(id) ? id : "";
      setVariant(side, variant);
    }
    const current = selection();
    const selectionChanged = current.some(({id, variant}, index) => id !== previous[index].id || variant !== previous[index].variant);
    const campaignChanged = current.some(({id}) => {
      const before = previousCampaigns.get(id);
      const now = campaigns.get(id);
      return before && now && (before.completed !== now.completed || before.status !== now.status);
    });
    if (selectionChanged || campaignChanged || (!pending && !output.childElementCount)) reset();
    if (campaignChanged && canCompare()) state.textContent = "Se actualizó una campaña. Compará la selección para ver los resultados nuevos.";
  }

  function open(preferred, button) {
    trigger = button;
    section.hidden = false;
    if (preferred || !selectors[0].campaign.value) {
      const options = [...campaigns.values()];
      const report = campaigns.get(preferred) || options.find(({variantNames}) => variantNames.length > 1) || options[0];
      const [a, b] = selectors;
      const [first, second] = report?.variantNames || [];
      a.campaign.value = report?.run_id || "";
      b.campaign.value = second ? report.run_id : "";
      setVariant(a, first);
      setVariant(b, second);
      reset();
    }
    heading.focus({preventScroll: true});
    section.scrollIntoView({block: "start"});
    if (!pending && !output.childElementCount && canCompare()) void compare();
  }

  async function compare() {
    if (pending || !canCompare()) return;
    const [a, b] = selection();
    const controller = new AbortController();
    pending = controller;
    submit.disabled = true;
    output.replaceChildren();
    state.textContent = "Leyendo campañas guardadas…";
    const load = (id) => getJSON(`/api/lab/evaluations/${encodeURIComponent(id)}`, {signal: controller.signal});
    try {
      const left = load(a.id);
      const [reportA, reportB] = await Promise.all([left, a.id === b.id ? left : load(b.id)]);
      if (controller.signal.aborted) return;
      const result = compareVariants(reportA, a.variant, reportB, b.variant);
      renderComparison(output, result, onOpenRun);
      state.textContent = "Comparación lista.";
    } catch (error) {
      if (!controller.signal.aborted) state.textContent = errorMessage(error);
    } finally {
      if (pending === controller) {
        pending = null;
        submit.disabled = !canCompare();
      }
    }
  }
}
