import { el } from "./dom.js";
import { formatDate, formatHectares, keyFigure, yearSpan } from "./format.js";
import { findPass, listPasses } from "./passes.js";

const RAMP = ["--ramp-1", "--ramp-2", "--ramp-3", "--ramp-4", "--ramp-5", "--ramp-6"];

export function renderLgaSelect(select, manifest, current, onChange) {
  select.replaceChildren(
    ...manifest.lgas.map((lga) => el("option", { value: lga.slug, text: lga.name, selected: lga.slug === current }))
  );
  select.onchange = () => onChange(select.value);
}

function layerOption(value, title, note, checked, disabled, onChange, extra = []) {
  return el("label", { class: "layer" }, [
    el("input", { type: "radio", name: "layer", value, checked, disabled, onchange: () => onChange(value) }),
    el("span", { class: "layer__title", text: title }),
    el("span", { class: "layer__note", text: note }),
    ...extra,
  ]);
}

function passPicker(passes, current, onPick) {
  return el("select", {
    class: "select layer__picker",
    "aria-label": "Radar pass",
    onchange: (e) => onPick(passes.find((p) => p.id === e.target.value)),
  }, passes.map((p) => el("option", { value: p.id, text: p.label, selected: p.id === current?.id })));
}

/**
 * Four choices: drainage problems, recurrent flooding, one radar pass (picked from a date list), or nothing.
 * onChange receives a state patch ({ layer, pass }).
 */
export function renderLayerControls(fieldset, lga, layer, passId, onChange) {
  const legend = fieldset.querySelector("legend");
  const f = lga.frequency;
  const suspects = lga.suspects;
  const passes = listPasses(lga);
  const onPass = layer === "event" || layer === "standing";
  const current = onPass ? findPass(lga, layer, passId) : null;
  const choose = (value) => {
    if (value === "pass") onChange({ layer: passes[0].layer, pass: null });
    else onChange({ layer: value, pass: null });
  };
  fieldset.replaceChildren(
    legend,
    layerOption("suspects", "Drainage problems",
      suspects ? `${suspects.counts.suspect} built-up places to check on the ground, ranked` : "Not yet analysed here",
      layer === "suspects", !suspects, choose),
    layerOption("frequency", f ? `Recurrent flooding ${yearSpan(f.years)}` : "Recurrent flooding",
      f ? "Shaded by how many rainy seasons each place flooded" : "Still processing",
      layer === "frequency", !f, choose),
    layerOption("pass", passes.length > 1 ? `Radar pass (${passes.length})` : "Radar pass",
      current ? current.note : passes.length ? "Pick a date" : "No passes mapped here yet",
      onPass, !passes.length, choose,
      onPass ? [passPicker(passes, current, (p) => onChange({ layer: p.layer, pass: p.id }))] : []),
    layerOption("none", "No flood layer", "Basemap and boundary only", layer === "none", false, choose),
  );
}

function about(text) {
  return el("details", { class: "about" }, [el("summary", { text: "About this layer" }), el("p", { text })]);
}

function frequencyLegend(frequency) {
  const steps = frequency.years.length;
  const dates = frequency.min_flood_dates_per_year ?? 1;
  const ramp = RAMP.slice(0, steps);
  return el("div", { class: "legend", style: { "--steps": steps } }, [
    el(
      "div",
      { class: "legend__ramp", "aria-hidden": "true" },
      ramp.map((token) => el("span", { class: "legend__step", style: { background: `var(${token})` } }))
    ),
    el(
      "div",
      { class: "legend__nums", "aria-hidden": "true" },
      ramp.map((_, i) => el("span", { text: String(i + 1) }))
    ),
    el("p", { class: "legend__caption", text: `Rainy seasons flooded, of ${steps}. Darker means more often.` }),
    about(`A season counts when the radar saw standing water on at least ${dates} separate dates. ` +
      "Brief flash floods seen only once are not counted here."),
  ]);
}

function suspectsLegend(counts) {
  return el("div", { class: "legend" }, [
    el("p", { class: "legend__caption" }, [
      el("span", { class: "legend__swatch legend__swatch--suspect", "aria-hidden": "true" }),
      "Suspected site, numbered by priority. Faint blue beneath shows how often each place flooded.",
    ]),
    about(`Of ${counts.suspect + counts.natural + counts.unclear} recurrent flood areas, ${counts.natural} are natural ` +
      `floodplain or wetland and ${counts.unclear} are inconclusive (open land, or too small to assess). ` +
      "Only built-up areas are ranked."),
  ]);
}

const KIND_LABELS = { raised_ground: "Elevated ground", road_crossing: "Road crossing" };

function swatchRow(modifier, text) {
  return el("p", { class: "legend__caption" }, [
    el("span", { class: `legend__swatch legend__swatch--${modifier}`, "aria-hidden": "true" }),
    text,
  ]);
}

function standingLegend(standing) {
  const after = formatDate(standing.after);
  const ha = standing.hectares;
  return el("div", { class: "legend legend__rows" }, [
    swatchRow("standing", `Still under water on ${after} (${formatHectares(ha.standing)})`),
    swatchRow("drained", `Flooded on ${formatDate(standing.before)}, drained since (${formatHectares(ha.drained)})`),
    swatchRow("new", `Wet on ${after} only (${formatHectares(ha.new)})`),
    ...(ha.not_imaged > 0
      ? [swatchRow("unseen", `Outside the radar's view on one of the dates (${formatHectares(ha.not_imaged)}): no information, not dry`)]
      : []),
    about("Ground that drains normally clears within a day or two of rain. Water still present after dry days " +
      "points to blocked or missing drainage. In swamps and floodplains it is normal for the season. " +
      "Radar sees open ground best; water in narrow streets between buildings is often missed."),
  ]);
}

function eventLegend(date) {
  return el("p", { class: "legend__caption" }, [
    el("span", { class: "legend__swatch", "aria-hidden": "true" }),
    `New standing water on ${formatDate(date)}, compared with the dry season`,
  ]);
}

export function renderFigure(figureEl, legendEl, lga, layer, passId = null) {
  const figure = keyFigure(lga, layer, passId);
  figureEl.replaceChildren(
    el("p", { class: "figure" }, [
      el("span", { class: "figure__value", text: figure.value }),
      el("span", { class: "figure__caption", text: figure.caption }),
    ])
  );
  const pass = layer === "standing" || layer === "event" ? findPass(lga, layer, passId) : null;
  if (layer === "suspects" && lga.suspects) legendEl.replaceChildren(suspectsLegend(lga.suspects.counts));
  else if (pass?.layer === "standing") legendEl.replaceChildren(standingLegend(pass.data));
  else if (layer === "frequency" && lga.frequency) legendEl.replaceChildren(frequencyLegend(lga.frequency));
  else if (pass?.layer === "event") legendEl.replaceChildren(eventLegend(pass.date));
  else legendEl.replaceChildren();
}

function tags(h, standing) {
  const list = [];
  if (h.kind) list.push(el("span", { class: "tag", text: KIND_LABELS[h.kind] ?? h.kind }));
  if (standing && h.water_now === "standing") {
    list.push(el("span", { class: "tag tag--water", text: `Still wet ${formatDate(standing.after).replace(/ \d{4}$/, "")}` }));
  }
  if (standing && h.water_now === "not_imaged") {
    list.push(el("span", {
      class: "tag tag--muted", text: "Not imaged",
      title: `Outside the radar's view on ${formatDate(standing.after)}: no information, not dry`,
    }));
  }
  return list;
}

const firstLandmark = (nearby) => (nearby ? nearby.split(" · ")[0] : null);

export function renderHotspots(list, heading, hotspots, layer, onSelect, lga) {
  const headings = {
    suspects: "Priority sites",
    standing: "Largest areas still under water",
    frequency: "Places that flood year after year",
  };
  heading.textContent = headings[layer] ?? "Largest flooded areas";
  if (!hotspots.length) {
    list.replaceChildren(el("li", { class: "status", text: "No flooded areas to list for this layer." }));
    return;
  }
  const standing = [lga?.standing ?? []].flat()[0];
  list.replaceChildren(
    ...hotspots.map((h) => {
      const near = firstLandmark(h.nearby);
      return el("li", {}, [
        el("button", {
          class: "site-row",
          type: "button",
          "aria-label": `${h.rank}. ${h.place}${near ? `, near ${near}` : ""}. Open`,
          onclick: () => onSelect(h),
        }, [
          el("span", { class: "hotspot__rank", text: String(h.rank) }),
          el("span", { class: "site-row__body" }, [
            el("span", { class: "site-row__place", text: h.place }),
            ...(near ? [el("span", { class: "site-row__near", text: near })] : []),
            el("span", { class: "site-row__tags" }, tags(h, standing)),
          ]),
          el("span", { class: "site-row__area", text: h.area_ha != null ? formatHectares(h.area_ha) : "" }),
        ]),
      ]);
    })
  );
}

export function renderTerrainControls(drainageBox, handBox, legendEl, lga, state) {
  const available = Boolean(lga.terrain);
  drainageBox.disabled = !available;
  handBox.disabled = !available;
  drainageBox.checked = available && state.drainage;
  handBox.checked = available && state.hand;
  if (!available || !state.hand) {
    legendEl.replaceChildren();
    return;
  }
  legendEl.replaceChildren(
    el("div", { class: "hand-legend" }, [
      el("span", { class: "hand-legend__bar", "aria-hidden": "true" }),
      el("span", { class: "hand-legend__ends" }, [el("span", { text: "0 m · at a channel" }), el("span", { text: "10 m+ · raised" })]),
    ])
  );
}
