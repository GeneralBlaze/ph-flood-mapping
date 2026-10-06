import { el } from "./dom.js";
import { formatHectares } from "./format.js";
import { FULL_STEPS, siteLabel } from "./full-area.js";

// Panel rendering for the full (server) analysis of a drawn area.
const $ = (id) => document.getElementById(id);

export function resetFull({ startable, intro }) {
  $("full-start").hidden = !startable;
  $("full-start").disabled = false;
  $("full-intro").textContent = intro;
  $("full-progress").hidden = true;
  $("full-step").textContent = "";
  $("full-lines").replaceChildren();
  $("full-sites").replaceChildren();
  $("full-key").hidden = true;
  $("full-caveat").hidden = true;
}

export function showFullProgress(step) {
  const percent = Math.round((step / FULL_STEPS.length) * 100);
  $("full-start").hidden = true;
  $("full-progress").hidden = step >= FULL_STEPS.length;
  $("full-progress").setAttribute("aria-valuenow", String(percent));
  $("full-progress-bar").style.setProperty("width", `${percent}%`);
  $("full-step").textContent = step < FULL_STEPS.length
    ? `Step ${step + 1} of ${FULL_STEPS.length}: ${FULL_STEPS[step]}…`
    : "";
}

export function showFullError(message) {
  $("full-progress").hidden = true;
  $("full-step").textContent = "";
  $("full-start").hidden = false;
  $("full-start").textContent = "Try again";
  $("full-lines").replaceChildren(el("p", { class: "status status--error", role: "alert", text: message }));
}

function siteCard(site, i, onSelect) {
  return el("li", { class: "full-site" }, [
    el("button", {
      class: "full-site__head",
      type: "button",
      "aria-label": `Site ${i + 1}: ${siteLabel(site)}. Show on map`,
      onclick: () => onSelect(i),
    }, [
      el("span", { class: "hotspot__rank", text: String(i + 1) }),
      el("span", { class: "full-site__label", text: siteLabel(site) }),
      el("span", { class: "full-site__area", text: formatHectares(site.area_ha) }),
    ]),
    el("div", { class: "full-site__story" }, site.story.map((line) => el("p", { text: line }))),
    ...(site.nearby ? [el("p", { class: "full-site__nearby", text: `Near ${site.nearby}` })] : []),
  ]);
}

export function showFullResult(result, onSelect) {
  showFullProgress(FULL_STEPS.length);
  const notes = result.streetsAvailable ? [] : ["Street names could not be fetched this time (OpenStreetMap was busy)."];
  $("full-lines").replaceChildren(...[...result.lines, ...notes].map((line) => el("p", { text: line })));
  $("full-sites").replaceChildren(...result.sites.map((site, i) => siteCard(site, i, onSelect)));
  $("full-key").hidden = false;
  $("full-caveat").hidden = false;
}
