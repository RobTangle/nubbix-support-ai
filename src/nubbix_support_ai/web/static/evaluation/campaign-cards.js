import {dateTime, element, statusBadge} from "../ui.js";
import {percentage} from "./view-data.js";

const corpusLabels = {dev: "Dev", test: "Test", adversarial: "Adversarial"};

export function createCampaignCard(report, selected, onOpenReport) {
  const button = element("button", "report-card");
  button.type = "button";
  if (selected) button.setAttribute("aria-current", "true");
  const heading = element("span", "report-card-heading");
  heading.append(element("strong", "", `${report.provider} · ${report.model}`), statusBadge(report.status));
  const metadata = element("span", "report-card-meta");
  metadata.append(element("span", "", dateTime(report.created_at)),
    element("code", "", report.run_id.slice(0, 8)));
  const variants = Object.keys(report.variants || {});
  const evaluated = [...new Set(variants.map((variant) => variant.split(":")[0]))];
  const prompts = evaluated.length ? evaluated : report.prompt_versions || [];
  const context = element("span", "report-card-context");
  const splits = (report.splits || []).map((split) => corpusLabels[split] || split);
  if (variants.some((variant) => variant.endsWith(":unguarded"))) splits.push("Con ablación");
  if (splits.length) context.append(element("span", "report-corpus", splits.join(" · ")));
  const promptGroup = element("span", "report-prompts");
  const promptLabel = evaluated.length ? "Prompts evaluados" : "Prompts previstos";
  promptGroup.append(element("span", "report-stat-label", promptLabel));
  for (const prompt of prompts) promptGroup.append(element("span", "report-prompt", prompt));
  if (!prompts.length) promptGroup.append(element("span", "", "Sin dato"));
  context.append(promptGroup);
  const classification = report.classification || {};
  const coverage = Object.values(classification.per_category || {}).filter((category) => category.support > 0).length;
  const stats = element("span", "report-card-stats");
  for (const [label, value, note] of [
    ["Exactitud", percentage(classification.accuracy), classification.labelled ?
      `${classification.correct}/${classification.labelled} aciertos` : ""],
    ["Macro-F1", percentage(classification.macro_f1), coverage ? `${coverage}/4 categorías` : ""],
    ["Errores / bloqueos", `${report.errors ?? "—"} / ${report.blocked ?? "—"}`, ""],
  ]) {
    const stat = element("span", "report-stat");
    stat.append(element("span", "report-stat-label", label), element("strong", "", value));
    if (note) stat.append(element("span", "report-stat-note", note));
    stats.append(stat);
  }
  const footer = element("span", "report-card-footer");
  footer.append(element("span", "", `${report.completed}/${report.planned} ejecuciones`),
    element("span", "", `Revisión humana ${percentage(report.human_review?.coverage)}`));
  button.append(heading, metadata, context, stats, footer);
  button.addEventListener("click", () => onOpenReport(report.run_id));
  return button;
}
