import {element} from "../ui.js";
import {blockOrigin} from "./case-flow.js";

export const caseKinds = {attack: "Ataque", control: "Control benigno"};
const categoryLabels = {match: "Coincide", mismatch: "No coincide", unclassified: "Sin clasificación", unlabelled: "Sin referencia"};
const returnNotes = {error: "Error operativo", cancelled: "Cancelado"};

export function returnedCategory({row, responseCategory, categoryResult}, label = "Categoría devuelta") {
  const returned = element("span", `case-outcome category-${categoryResult}`);
  const valueLine = element("span", "case-outcome-value-line");
  const returnedValue = responseCategory || (row.response ? "Sin categoría" : "Sin respuesta");
  valueLine.append(element(responseCategory ? "code" : "span", "case-category-value", returnedValue),
    element("span", "case-outcome-tag", categoryLabels[categoryResult]));
  returned.append(element("span", "case-outcome-label", label), valueLine);
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
