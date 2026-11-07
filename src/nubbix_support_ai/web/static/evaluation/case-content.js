import {element} from "../ui.js";

export const caseKinds = {attack: "Ataque", control: "Control benigno"};
const categoryLabels = {match: "Coincide", mismatch: "No coincide", unclassified: "Sin clasificación", unlabelled: "Sin referencia"};
const returnNotes = {blocked: "Bloqueado por controles", error: "Error operativo", cancelled: "Cancelado"};

export function returnedCategory({row, responseCategory, categoryResult}, label = "Categoría devuelta") {
  const returned = element("span", `case-outcome category-${categoryResult}`);
  const valueLine = element("span", "case-outcome-value-line");
  const returnedValue = responseCategory || (row.response ? "Sin categoría" : "Sin respuesta");
  valueLine.append(element(responseCategory ? "code" : "span", "case-category-value", returnedValue),
    element("span", "case-outcome-tag", categoryLabels[categoryResult]));
  returned.append(element("span", "case-outcome-label", label), valueLine);
  if (returnNotes[row.status]) {
    const note = row.status === "blocked" && row.response ? "Bloqueado por controles · respuesta de respaldo" : returnNotes[row.status];
    returned.append(element("span", "case-outcome-note", note));
  }
  return returned;
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
