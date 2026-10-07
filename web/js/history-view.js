import { el } from "./dom.js";
import { formatHectares } from "./format.js";
import { catalogue } from "./history-store.js";

// History tab: the published radar passes and this browser's drawn areas, filtered by LGA.
const timeFormat = new Intl.DateTimeFormat("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const $ = (id) => document.getElementById(id);

function passRow(pass, isCurrent, onOpen) {
  return el("li", {}, [
    el("button", {
      class: "history-row",
      type: "button",
      "aria-current": isCurrent ? "true" : null,
      "aria-label": `${pass.label}, ${pass.lgaName}. Show on map`,
      onclick: () => onOpen(pass),
    }, [
      el("span", { class: "history-row__main" }, [
        el("span", { class: "history-row__title", text: pass.label }),
        el("span", { class: "history-row__meta", text: pass.lgaName }),
      ]),
      el("span", { class: "history-row__figure", text: formatHectares(pass.hectares) }),
    ]),
  ]);
}

function areaRow(run, onOpen, onRemove) {
  const when = timeFormat.format(new Date(run.savedAt));
  const meta = [run.lgaName, `${run.areaKm2.toFixed(1)} km²`, when].join(" · ");
  return el("li", { class: "history-item" }, [
    el("button", {
      class: "history-row",
      type: "button",
      "aria-label": `${run.place}, ${meta}. Open`,
      onclick: () => onOpen(run),
    }, [
      el("span", { class: "history-row__main" }, [
        el("span", { class: "history-row__title", text: run.place }),
        el("span", { class: "history-row__meta", text: meta }),
        ...(run.full ? [el("span", { class: "tag tag--water", text: "Full analysis saved" })] : []),
      ]),
    ]),
    el("button", {
      class: "history-item__remove",
      type: "button",
      "aria-label": `Remove ${run.place} from history`,
      title: "Remove",
      onclick: () => onRemove(run),
    }, ["×"]),
  ]);
}

/** Renders the History tab. handlers: { onFilter(slug|"all"), onOpenPass(pass), onOpenRun(run), onRemoveRun(run) } */
export function renderHistory({ manifest, runs, filter, current, handlers }) {
  const select = $("history-filter");
  select.replaceChildren(
    el("option", { value: "all", text: "All areas", selected: filter === "all" }),
    ...manifest.lgas.map((l) => el("option", { value: l.slug, text: l.name, selected: l.slug === filter })),
  );
  select.onchange = () => handlers.onFilter(select.value);

  const { passes, areas } = catalogue({ manifest, runs, lga: filter });
  $("history-passes").replaceChildren(
    ...(passes.length
      ? passes.map((p) => passRow(p, p.lga === current.lga && p.id === current.passId, handlers.onOpenPass))
      : [el("li", { class: "status", text: "No radar passes mapped here yet." })]),
  );
  $("history-areas").replaceChildren(
    ...(areas.length
      ? areas.map((r) => areaRow(r, handlers.onOpenRun, handlers.onRemoveRun))
      : [el("li", { class: "status", text: "Areas you draw and analyse will appear here." })]),
  );
}
