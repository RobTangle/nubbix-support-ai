import {element} from "../ui.js";

export const caseKinds = {attack: "Ataque", control: "Control benigno"};
export const caseStages = {
  input_moderation: ["Moderación de entrada", "la moderación de entrada"],
  generation: ["Modelo principal", "el modelo principal"],
  output_moderation: ["Moderación de salida", "la moderación de salida"],
};
const categoryLabels = {match: "Coincide", mismatch: "No coincide", unclassified: "Sin clasificación", unlabelled: "Sin referencia"};
const returnNotes = {error: "Error operativo", cancelled: "Cancelado"};
const attackLabels = {blocked: "Ataque bloqueado", ok: "Ataque con respuesta", escalated: "Ataque con respuesta"};

function blockOrigin(row) {
  if (row.flow === undefined && row.request_id) return "Abrí la traza del caso para ver el origen";
  const stage = row.flow?.blocked_at;
  const result = row.flow?.stages?.[stage];
  if (!result || !Object.hasOwn(caseStages, stage)) return "Etapa del bloqueo no registrada";
  const location = caseStages[stage][1];
  let description = `Bloqueo en ${location}`;
  if (result.status === "refused") description = `Rechazo del proveedor en ${location}`;
  else if (result.decision === "review") description = `Revisión solicitada por ${location}`;
  return result.reason_code ? `${description} · ${result.reason_code}` : description;
}

export function caseOutcome({row, responseCategory, categoryResult}, label) {
  if (row.kind === "attack") {
    const outcome = element("span", "case-outcome");
    outcome.append(element("span", "case-outcome-label", label || "Resultado de seguridad"),
      element("strong", "case-category-value", attackLabels[row.status] || returnNotes[row.status] || "Sin resultado"));
    if (row.status === "blocked") {
      outcome.append(element("span", "case-outcome-note", `${blockOrigin(row)} · categoría sin evaluar`));
    } else if (responseCategory) {
      outcome.append(element("span", "case-outcome-note", `Categoría del modelo · ${responseCategory}`));
    }
    return outcome;
  }
  const returned = element("span", `case-outcome category-${categoryResult}`);
  const valueLine = element("span", "case-outcome-value-line");
  const returnedValue = responseCategory || (row.response ? "Sin categoría" : "Sin respuesta");
  valueLine.append(element(responseCategory ? "code" : "span", "case-category-value", returnedValue),
    element("span", "case-outcome-tag", categoryLabels[categoryResult]));
  returned.append(element("span", "case-outcome-label", label || "Categoría devuelta"), valueLine);
  if (row.status === "blocked") {
    const note = row.response ? `${blockOrigin(row)} · respaldo de la app` : blockOrigin(row);
    returned.append(element("span", "case-outcome-note", note));
  } else if (returnNotes[row.status]) {
    returned.append(element("span", "case-outcome-note", returnNotes[row.status]));
  }
  return returned;
}

export function responseHeading(row, title = "Respuesta entregada") {
  const heading = element("div", "case-response-heading");
  heading.append(element("h3", "", title));
  if (row.response && row.status === "blocked") {
    heading.append(element("span", "case-kind", "Respaldo de la app"));
  } else if (row.response && row.status === "ok") {
    heading.append(element("span", "case-kind", "Propuesta del modelo"));
  } else if (row.response && row.status === "escalated") {
    heading.append(element("span", "case-kind", "Propuesta con revisión sugerida por la app"));
  }
  return heading;
}

export function actionList(title, actions, empty) {
  const block = element("div", "case-actions");
  block.append(element("h3", "", title));
  if (actions?.length) {
    const list = element("ul");
    for (const action of actions) list.append(element("li", "", action));
    block.append(list);
  } else {
    block.append(element("p", "field-note", empty));
  }
  return block;
}
