import {element} from "./ui.js";

const stages = [
  ["input_moderation", "Revisión de entrada", "Revisando tu consulta"],
  ["generation", "Preparar propuesta", "Preparando la propuesta"],
  ["output_moderation", "Revisión de salida", "Verificando la respuesta"],
];
const stageStatuses = {pending: "Pendiente", active: "En curso", retrying: "Reintentando", completed: "Listo", blocked: "Revisión", skipped: "Sin ejecutar", error: "Interrumpida", cancelled: "Cancelada"};
const outcomes = {
  ok: ["Propuesta lista", "El análisis terminó y la propuesta está disponible."],
  escalated: ["Revisión humana sugerida", "El análisis terminó; revisá la propuesta y sus acciones."],
  blocked: ["Consulta derivada a revisión", "Un control indicó que la consulta requiere revisión humana."],
  error: ["El análisis se interrumpió", "No se obtuvo una propuesta final. Consultá la traza antes de volver a intentar."],
  cancelled: ["Análisis cancelado", "Se cerró la conexión. Consultá la traza y el historial para revisar lo registrado."],
};

export class TicketProgress {
  constructor() {
    this.start();
    this.status = "idle";
  }

  start() {
    this.status = "running";
    this.activeStage = null;
    this.headline = "Analizando tu ticket";
    this.message = "Conectando con el proveedor para iniciar la revisión.";
    this.activities = [];
    this.stages = stages.map(([id, label, headline]) => ({id, label, headline, status: "pending", attempt: 0, note: "Se ejecuta al llegar su turno."}));
  }

  append(event) {
    if (this.status !== "running") return;
    const stage = this.stages.find((item) => item.id === event.stage);
    let activity = null;
    if (event.event === "request.received") {
      this.message = "Ticket recibido. Comenzamos con el contexto y las políticas de soporte.";
      activity = "Ticket recibido";
    } else if (stage) {
      this.activeStage = stage.id;
      if (event.event === "llm.request.started") {
        stage.status = "active";
        stage.attempt = event.attempt || 1;
        stage.note = `Intento ${stage.attempt} en curso`;
        this.headline = stage.headline;
        this.message = stage.id === "input_moderation" ? "Comprobando el mensaje según el contexto y las políticas de soporte." : stage.id === "generation" ? "Preparando una respuesta y acciones sugeridas con el contexto disponible." : "Revisando la respuesta completa y las acciones antes de mostrarlas.";
        activity = `${stage.label} · intento ${stage.attempt}`;
      } else if (event.event === "schema.validation.started") {
        stage.note = "Validando el formato recibido";
        this.message = stage.id === "generation" ? "Comprobando que la propuesta cumpla el contrato de cuatro campos." : "Validando la respuesta del control antes de aplicar su decisión.";
      } else if (event.event === "schema.validation.failed") {
        stage.note = "El formato necesita una corrección";
        this.message = "La salida requiere una corrección de formato. El siguiente intento aparecerá en esta etapa.";
        activity = "Se detectó un formato que requiere reparación";
      } else if (event.event === "schema.validation.completed") {
        if (stage.id === "generation") {
          stage.status = "completed";
          stage.note = "Contrato de cuatro campos validado";
          activity = "Formato de la propuesta validado";
        } else {
          stage.note = "Formato válido; confirmando la decisión";
        }
      } else if (event.event === "moderation.completed") {
        const allowed = event.details?.decision === "allow";
        stage.status = allowed ? "completed" : "blocked";
        stage.note = allowed ? "Control completado" : "Se requiere revisión humana";
        this.message = allowed ? "El control terminó. Preparando el siguiente paso." : "El control indicó revisión humana. Preparando la derivación.";
        activity = allowed ? `${stage.label} completada` : `${stage.label}: derivación a revisión`;
      } else if (event.event === "retry.scheduled") {
        stage.status = "retrying";
        const delay = Number(event.details?.delay_seconds);
        stage.note = Number.isFinite(delay) ? `Pausa de ${delay.toLocaleString("es-AR")} s antes de reintentar` : "Esperando para reintentar";
        this.headline = "Esperando para reintentar";
        this.message = event.details?.error_code === "rate_limited" ? "El proveedor solicitó una pausa. Respetamos su espera y conservamos el avance." : "Se programó otro intento dentro de los límites de esta etapa.";
        activity = `${stage.label}: nuevo intento programado`;
      } else if (event.event === "llm.request.failed") {
        stage.note = "La llamada no pudo completarse";
        this.message = "El proveedor no completó este intento. Verificando si es posible reintentar.";
        activity = `${stage.label}: intento interrumpido`;
      } else if (event.event === "attempt.completed" && event.details?.status === "refused") {
        stage.status = "blocked";
        stage.note = "El proveedor indicó una derivación";
        activity = `${stage.label}: respuesta derivada`;
      }
    } else if (event.event === "human_review.suggested") {
      activity = "La propuesta requiere revisión humana";
    } else if (event.event === "run.completed") {
      this.headline = "Preparando el resultado";
      this.message = "El flujo terminó. Guardando la traza y preparando el resultado.";
      activity = "Flujo terminado";
    }
    if (activity) {
      this.activities.push({text: activity, elapsedMs: Number(event.elapsed_ms) || 0});
      this.activities = this.activities.slice(-3);
    }
  }

  cancel() {
    if (this.status !== "running") return;
    this.status = "cancelling";
    this.headline = "Deteniendo el análisis";
    this.message = "Cerrando la conexión y cancelando el trabajo pendiente.";
  }

  finish(status) {
    this.status = outcomes[status] ? status : "error";
    [this.headline, this.message] = outcomes[this.status];
    for (const stage of this.stages) {
      if (stage.status === "pending") stage.status = "skipped";
      else if (["active", "retrying"].includes(stage.status)) {
        stage.status = ["ok", "escalated"].includes(this.status) ? "completed" : this.status;
        stage.note = this.status === "cancelled" ? `Intento ${stage.attempt} cancelado` : this.status === "error" ? `Intento ${stage.attempt} interrumpido` : this.status === "blocked" ? "Se requiere revisión humana" : "Etapa finalizada";
      }
    }
  }
}

export function createResponseProgress(target, onCancel) {
  const state = new TicketProgress();
  const card = target.closest(".response-card");
  const response = document.getElementById("response-content");
  const heading = element("div", "progress-heading");
  const indicator = element("span", "progress-indicator");
  indicator.setAttribute("aria-hidden", "true");
  const identity = element("div", "progress-identity");
  const eyebrow = element("p", "progress-eyebrow", "ANÁLISIS EN VIVO");
  const title = element("h3", "progress-title");
  title.setAttribute("role", "status");
  title.setAttribute("aria-live", "polite");
  identity.append(eyebrow, title);
  const clock = element("span", "progress-clock", "00:00");
  clock.title = "Tiempo transcurrido desde el envío";
  clock.setAttribute("aria-hidden", "true");
  heading.append(indicator, identity, clock);
  const description = element("p", "progress-description");
  const details = element("details", "progress-details");
  const summary = element("summary", "", "Ver etapas y actividad");
  const counter = element("p", "progress-counter");
  const steps = element("ol", "progress-stages");
  steps.setAttribute("aria-label", "Avance del análisis");
  const recent = element("div", "progress-recent");
  const activities = element("ol", "progress-activity");
  recent.append(element("p", "progress-eyebrow", "ÚLTIMAS SEÑALES"), activities);
  details.append(summary, counter, steps, recent);
  const footer = element("div", "progress-footer");
  const hint = element("span", "", "La propuesta aparece al finalizar el flujo.");
  const actions = element("div", "progress-actions");
  const cancel = element("button", "progress-cancel", "Cancelar análisis");
  cancel.type = "button";
  cancel.addEventListener("click", onCancel);
  const link = element("a", "progress-trace-link", "Ver traza completa ↓");
  link.href = "#trace-heading";
  link.addEventListener("click", (event) => {
    event.preventDefault();
    const trace = document.getElementById("trace-heading");
    trace.scrollIntoView({block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
    trace.focus({preventScroll: true});
  });
  actions.append(cancel, link);
  footer.append(hint, actions);
  target.replaceChildren(heading, description, details, footer);
  let started = 0;
  let timer = null;

  function tick() {
    const seconds = Math.floor((performance.now() - started) / 1000);
    clock.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function render() {
    const busy = ["running", "cancelling"].includes(state.status);
    target.dataset.status = state.status;
    target.classList.toggle("is-finished", !busy);
    card.classList.toggle("is-processing", busy);
    response.setAttribute("aria-busy", String(busy));
    indicator.textContent = busy ? "" : ["ok", "escalated"].includes(state.status) ? "✓" : state.status === "cancelled" ? "Ⅱ" : "!";
    eyebrow.textContent = busy ? "ANÁLISIS EN VIVO" : "RESUMEN DEL ANÁLISIS";
    if (title.textContent !== state.headline) title.textContent = state.headline;
    description.textContent = state.message;
    summary.hidden = busy;
    const done = state.stages.filter((stage) => ["completed", "blocked"].includes(stage.status)).length;
    counter.textContent = `${done} de 3 etapas finalizadas`;
    steps.replaceChildren(...state.stages.map((stage, index) => {
      const row = element("li", `progress-stage is-${stage.status}`);
      if (["active", "retrying"].includes(stage.status)) row.setAttribute("aria-current", "step");
      const marker = element("span", "progress-marker", stage.status === "completed" ? "✓" : stage.status === "blocked" || stage.status === "error" ? "!" : String(index + 1).padStart(2, "0"));
      marker.setAttribute("aria-hidden", "true");
      const text = element("div", "progress-stage-copy");
      text.append(element("strong", "", stage.label), element("span", "", stage.status === "skipped" ? "El flujo terminó antes de esta etapa." : stage.note));
      row.append(marker, text, element("span", "progress-stage-status", stageStatuses[stage.status] || stage.status));
      return row;
    }));
    recent.hidden = state.activities.length === 0;
    activities.replaceChildren(...state.activities.map((activity) => {
      const row = element("li");
      row.append(element("span", "progress-event-time", `${(activity.elapsedMs / 1000).toLocaleString("es-AR", {maximumFractionDigits: 1})} s`), element("span", "", activity.text));
      return row;
    }));
    hint.hidden = !busy;
    cancel.hidden = !busy;
    cancel.disabled = state.status === "cancelling";
  }

  return {
    start() {
      clearInterval(timer);
      state.start();
      started = performance.now();
      target.hidden = false;
      details.open = true;
      render();
      tick();
      timer = setInterval(tick, 1000);
      if (matchMedia("(max-width: 700px)").matches) card.scrollIntoView({block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
    },
    append(event) {
      state.append(event);
      render();
    },
    cancel() {
      state.cancel();
      render();
    },
    finish(status) {
      clearInterval(timer);
      tick();
      state.finish(status);
      details.open = ["error", "cancelled"].includes(state.status);
      render();
    },
  };
}
