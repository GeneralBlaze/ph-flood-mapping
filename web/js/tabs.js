// Map / Sites / History tabs (WAI-ARIA tabs pattern: arrow keys move between tabs).
const TAB_IDS = ["map", "sites", "history"];

export function showTab(name) {
  for (const id of TAB_IDS) {
    const tab = document.getElementById(`tab-${id}`);
    const selected = id === name;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(`panel-${id}`).hidden = !selected;
  }
}

export function setupTabs(onSelect) {
  TAB_IDS.forEach((id, i) => {
    const tab = document.getElementById(`tab-${id}`);
    tab.addEventListener("click", () => onSelect(id));
    tab.addEventListener("keydown", (e) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const next = TAB_IDS[(i + step + TAB_IDS.length) % TAB_IDS.length];
      onSelect(next);
      document.getElementById(`tab-${next}`).focus();
    });
  });
}
