const SMALL_AREA_HA = 100;
const numberFormat = new Intl.NumberFormat("en-NG", { maximumFractionDigits: 0 });
const smallFormat = new Intl.NumberFormat("en-NG", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatHectares(value) {
  const formatter = value < SMALL_AREA_HA ? smallFormat : numberFormat;
  return `${formatter.format(value)} ha`;
}

export function formatDate(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

export function yearSpan(years) {
  return `${years[0]}–${years[years.length - 1]}`;
}

function repeatHectares(frequency) {
  return Object.entries(frequency.hectares_by_years_flooded)
    .filter(([years]) => Number(years) >= frequency.repeat_min_years)
    .reduce((sum, [, ha]) => sum + ha, 0);
}

export function keyFigure(lga, layer) {
  if (layer === "suspects" && lga.suspects) {
    const n = lga.suspects.counts.suspect;
    return {
      value: `${n} ${n === 1 ? "site" : "sites"}`,
      caption: "built-up locations with recurrent flooding on ground that should drain naturally",
    };
  }
  if (layer === "frequency" && lga.frequency) {
    const f = lga.frequency;
    return {
      value: formatHectares(repeatHectares(f)),
      caption: `flooded in ${f.repeat_min_years} or more of the rainy seasons ${yearSpan(f.years)}`,
    };
  }
  if (layer === "standing" && lga.standing) {
    const w = lga.standing;
    return {
      value: formatHectares(w.hectares.standing),
      caption: `still under water on ${formatDate(w.after)}, after the rain of ${formatDate(w.before)}`,
    };
  }
  const event = lga.events[0];
  if (layer === "event" && event) {
    return { value: formatHectares(event.flooded_ha), caption: `under standing water on ${formatDate(event.date)}` };
  }
  return { value: "—", caption: "Choose a flood layer to see figures." };
}
