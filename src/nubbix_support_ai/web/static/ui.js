export const categories = {billing: "Facturación", technical: "Soporte técnico", account: "Cuenta", other: "Otras consultas"};
export const statuses = {ok: "Completado", blocked: "Derivado por controles", escalated: "Revisión humana", error: "Error", cancelled: "Cancelado", running: "En curso", completed: "Completado", interrupted: "Interrumpido", budget_exhausted: "Presupuesto agotado", failed: "Fallida"};
const errors = {invalid_request: "Revisá los datos ingresados.", missing_openai_key: "Configurá OPENAI_API_KEY en el entorno del servidor.", missing_google_key: "Configurá GEMINI_API_KEY en el entorno del servidor.", evaluation_in_progress: "Ya hay una campaña activa en este proceso.", budget_exceeded: "Se alcanzó el presupuesto estimado. Revisá el historial antes de volver a intentar.", unpriced_model: "El modelo seleccionado no tiene una tarifa registrada.", invalid_model_output: "El modelo no devolvió una salida válida después de los intentos permitidos.", timeout: "La llamada superó su tiempo máximo.", deadline_exceeded: "El ticket alcanzó su plazo total.", stream_interrupted: "La conexión se interrumpió. El trabajo no se reanuda automáticamente.", provider_unavailable: "El proveedor no está disponible.", storage_error: "No se pudo guardar o leer un archivo local.", unknown_prompt_version: "La versión del prompt no existe en el catálogo.", invalid_evaluation: "La configuración de la campaña no es válida.", evaluation_not_found: "No se encontró esta campaña.", run_not_found: "No se encontró esta ejecución."};

export function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = String(text ?? "");
  return node;
}

export function errorMessage(error) {
  if (error.name === "AbortError") return "Cancelaste la ejecución. Se conserva lo que alcanzó a registrarse; no se reanuda automáticamente.";
  const code = error.code || error.message;
  return (errors[code] || "No se pudo completar la operación. Revisá el historial antes de reintentar.") + (error.requestId ? ` ID: ${error.requestId}` : "");
}

export function notice(message, isError = false) {
  const node = document.getElementById("global-notice");
  node.textContent = message;
  node.classList.toggle("error", isError);
  node.hidden = !message;
}

export function money(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "Sin dato";
  const amount = Number(value);
  return `US$ ${amount.toFixed(amount > 0 && amount < .01 ? 6 : 4)}`;
}

export function dateTime(value) {
  if (!value) return "Sin fecha";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("es-AR", {dateStyle: "short", timeStyle: "short"});
}

export function statusBadge(status) {
  return element("span", `small-tag status-${status}`, statuses[status] || status || "Sin estado");
}

export function metrics(target, value = {}) {
  const complete = value.usage_complete !== false;
  const items = [["Latencia total", value.latency_seconds == null ? "—" : `${Number(value.latency_seconds).toFixed(2)} s`, "Incluye todas las etapas"],
    ["Tokens totales", value.total_tokens == null ? "—" : Number(value.total_tokens).toLocaleString("es-AR"), complete ? "Entrada + salida" : "Uso incompleto"],
    ["Costo estimado", value.estimated_cost_usd == null ? "—" : money(value.estimated_cost_usd), complete ? "Según tarifas registradas" : "Incluye reservas desconocidas"],
    ["Llamadas", value.calls == null ? "—" : value.calls, "Controles + generación + retries"]];
  target.replaceChildren(...items.map(([label, amount, note]) => {
    const card = element("div", "metric");
    card.append(element("div", "metric-label", label), element("strong", "metric-value", amount), element("span", "metric-note", note));
    return card;
  }));
}

export function jsonSection(parent, label, value, open = false) {
  const details = element("details", "inspection-section");
  details.open = open;
  const pre = element("pre", "", typeof value === "string" ? value : JSON.stringify(value, null, 2));
  pre.tabIndex = 0;
  details.append(element("summary", "", label), pre);
  parent.append(details);
  return details;
}

export async function copyJSON(value, button) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = "Copiado";
    setTimeout(() => { button.textContent = "Copiar JSON"; }, 1800);
  } catch {
    notice("No se pudo acceder al portapapeles. Podés seleccionar y copiar el JSON visible.", true);
  }
}

export function configureProviderSelectors(catalog, providerSelect, modelSelect) {
  providerSelect.replaceChildren(...catalog.providers.map((provider) => {
    const option = element("option", "", provider.label + (provider.available ? "" : " · sin clave"));
    option.value = provider.id;
    return option;
  }));
  providerSelect.value = catalog.default_provider;
  const updateModels = () => {
    const provider = catalog.providers.find((item) => item.id === providerSelect.value);
    modelSelect.replaceChildren(...provider.models.map((model) => {
      const option = element("option", "", model);
      option.value = model;
      return option;
    }));
    modelSelect.value = provider.default_model;
    if (!modelSelect.value && modelSelect.options.length) modelSelect.selectedIndex = 0;
  };
  updateModels();
  providerSelect.addEventListener("change", updateModels);
}
