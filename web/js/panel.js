import { el } from "./dom.js";
import { formatDate, formatHectares, keyFigure, yearSpan } from "./format.js";

const RAMP = ["--ramp-1", "--ramp-2", "--ramp-3", "--ramp-4", "--ramp-5", "--ramp-6"];

export function renderLgaSelect(select, manifest, current, onChange) {
  select.replaceChildren(
    ...manifest.lgas.map((lga) => el("option", { value: lga.slug, text: lga.name, selected: lga.slug === current }))
  );
  select.onchange = () => onChange(select.value);
}

function layerOption(value, title, note, checked, disabled, onChange) {
  return el("label", { class: "layer" }, [
    el("input", { type: "radio", name: "layer", value, checked, disabled, onchange: () => onChange(value) }),
    el("span", { class: "layer__title", text: title }),
    el("span", { class: "layer__note", text: note }),
  ]);
}

export function renderLayerControls(fieldset, lga, layer, onChange) {
  const legend = fieldset.querySelector("legend");
  const event = lga.events[0];
  const f = lga.frequency;
  const suspects = lga.suspects;
  fieldset.replaceChildren(
    legend,
    layerOption(
      "suspects",
      "Suspected drainage problems",
      suspects
        ? `${suspects.counts.suspect} built-up places to check on the ground, ranked`
        : "Not yet analysed for this area",
      layer === "suspects",
      !suspects,
      onChange
    ),
    layerOption(
      "standing",
      lga.standing ? `Water still standing, ${formatDate(lga.standing.after)}` : "Water still standing",
      lga.standing
        ? `Flooding from ${formatDate(lga.standing.before)} that had not drained after the dry days since`
        : "Not yet analysed for this area",
      layer === "standing",
      !lga.standing,
      onChange
    ),
    layerOption(
      "frequency",
      f ? `Recurrent flooding, ${yearSpan(f.years)}` : "Recurrent flooding",
      f ? "Shaded by number of rainy seasons flooded" : "Still processing — check back soon",
      layer === "frequency",
      !f,
      onChange
    ),
    layerOption(
      "event",
      event ? `Flood of ${formatDate(event.date)}` : "Latest flood",
      event ? "Standing water the morning and evening after heavy rain" : "No recent event mapped",
      layer === "event",
      !event,
      onChange
    ),
    layerOption("none", "No flood layer", "Basemap and boundary only", layer === "none", false, onChange)
  );
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
    el("p", {
      class: "legend__caption",
      text:
        `Number of rainy seasons (of ${steps}) in which the radar saw standing water on at least ${dates} ` +
        "separate dates. Darker means more often. Brief flash floods seen only once are not counted here.",
    }),
  ]);
}

function suspectsLegend(counts) {
  return el("div", { class: "legend" }, [
    el("p", { class: "legend__caption" }, [
      el("span", { class: "legend__swatch legend__swatch--suspect", "aria-hidden": "true" }),
      "Suspected site, numbered by priority. Faint blue beneath shows how often each place flooded.",
    ]),
    el("p", {
      class: "legend__caption",
      text:
        `Of ${counts.suspect + counts.natural + counts.unclear} recurrent flood areas, ${counts.natural} are natural ` +
        `floodplain or wetland and ${counts.unclear} are inconclusive (open land, or too small to assess). ` +
        "Only built-up areas are ranked.",
    }),
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
    el("p", {
      class: "legend__caption",
      text:
        "Ground that drains normally clears within a day or two of rain. Water still present after dry days " +
        "points to blocked or missing drainage. In swamps and floodplains it is normal for the season. " +
        "Radar sees open ground best; water in narrow streets between buildings is often missed.",
    }),
  ]);
}

function eventLegend(date) {
  return el("p", { class: "legend__caption" }, [
    el("span", { class: "legend__swatch", "aria-hidden": "true" }),
    `New standing water on ${formatDate(date)}, compared with the dry season`,
  ]);
}

export function renderFigure(figureEl, legendEl, lga, layer) {
  const figure = keyFigure(lga, layer);
  figureEl.replaceChildren(
    el("p", { class: "figure" }, [
      el("span", { class: "figure__value", text: figure.value }),
      el("span", { class: "figure__caption", text: figure.caption }),
    ])
  );
  if (layer === "suspects" && lga.suspects) legendEl.replaceChildren(suspectsLegend(lga.suspects.counts));
  else if (layer === "standing" && lga.standing) legendEl.replaceChildren(standingLegend(lga.standing));
  else if (layer === "frequency" && lga.frequency) legendEl.replaceChildren(frequencyLegend(lga.frequency));
  else if (layer === "event" && lga.events[0]) legendEl.replaceChildren(eventLegend(lga.events[0].date));
  else legendEl.replaceChildren();
}

function waterFlag(status, standing) {
  if (!standing) return [];
  if (status === "standing") {
    return [el("span", { class: "hotspot__flag", text: `Still under water on ${formatDate(standing.after)}` })];
  }
  if (status === "not_imaged") {
    return [el("span", { class: "hotspot__flag hotspot__flag--muted", text: `Not imaged on ${formatDate(standing.after)}` })];
  }
  return [];
}

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
  list.replaceChildren(
    ...hotspots.map((h) =>
      el("li", {}, [
        el(
          "button",
          {
            class: "hotspot",
            type: "button",
            "aria-label": `${h.rank}. ${h.place}, ${formatHectares(h.area_ha)}. Show on map`,
            onclick: (e) => {
              list.querySelectorAll("[aria-current]").forEach((b) => b.removeAttribute("aria-current"));
              e.currentTarget.setAttribute("aria-current", "true");
              onSelect(h);
            },
          },
          [
            el("span", { class: "hotspot__rank", text: String(h.rank) }),
            el("span", { class: "hotspot__place" }, [
              h.place,
              ...waterFlag(h.water_now, lga?.standing),
            ]),
            el("span", { class: "hotspot__area", text: h.kind ? KIND_LABELS[h.kind] : formatHectares(h.area_ha) }),
          ]
        ),
      ])
    )
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
