# PH Flood Mapping — Design System (MASTER)

Source of truth for every page. Page files in `pages/` override this where they differ.
Derived from ui-ux-pro-max ("Accessible & Ethical" style for public/government audiences)
merged with a hydrographic survey-sheet direction. The generator's "Marketplace" page
pattern was rejected: this product is map-first, not search-first.

## Principles
1. **The map is the page.** UI floats over it like a chart's title block; never a sidebar-plus-cards dashboard.
2. **Honest by default.** Limitations are always one tap away and written in plain language.
3. **Readable in the field.** Built for phones on patchy connections: large text, 44px targets, light payloads.
4. **Colour is never the only signal.** Every colour on the map is paired with a number or label.

## Typography (2 families)
| Role | Font | Use |
|---|---|---|
| Display | **Newsreader** (opsz, 500/600, italic for asides) | Sheet title, section heads, big figures |
| Text/UI | **Public Sans** (400/500/600, `tnum` for figures) | Body, labels, buttons, legend |

Scale (rem): 0.8125 label · 0.9375 small · 1.0 body (16px min) · 1.25 h3 · 1.625 h2 · clamp(1.9, 1.5+1.6vw, 2.6) title.
Line-height 1.55 body, 1.1 display. Max line length 62ch. Labels: uppercase, 0.08em tracking, 600.

## Colour tokens
| Token | Light | Dark | Use |
|---|---|---|---|
| `--paper` | #F4F1E8 | #111A26 | Panel surface (chart paper) |
| `--paper-2` | #EAE5D6 | #172233 | Inset blocks, hover |
| `--ink` | #0F1B2D | #ECE8DC | Primary text (≥12:1) |
| `--ink-muted` | #3E4A5C | #A9B4C3 | Secondary text (≥7:1) |
| `--rule` | #C9C1AA | #2C3a4E | Hairlines, borders |
| `--accent` | #0369A1 | #63BDF2 | Links, focus, active control |
| `--signal` | #C2410C | #F2914F | Hotspot markers & ranks (always numbered) |
| `--event` | #1F6FFF | #1F6FFF | Single flood event overlay |
| `--channel` | #0891B2 | #22D3EE | Expected drainage channels (teal, never blue) |

Recurring-flood ramp (years flooded 1→6, single-hue, CVD-safe, labelled 1–6 in legend):
`#D6E6F4 #A8CBE8 #6FA8D6 #3A82C0 #1A5A9A #0B3470`

Only one flood layer (recurring *or* event) is shown at a time, so the two blues never compete.

Height-above-drainage ramp (earth tones — **blue is reserved for water**), 0 m → 10 m+:
`#F7F1E1 #E8D8B0 #D4B97F #B8925A #8C5A2B #5C3A1C`

## Space, shape, depth
- Spacing (4px base): 4 · 8 · 12 · 16 · 24 · 32 · 48. Section rhythm 24/32, not uniform.
- Radius: 2px controls, 4px panel. Crisp, chart-like.
- One elevation: `--shadow-sheet: 0 1px 0 var(--rule), 0 12px 32px -12px rgb(15 27 45 / .35)`.
- Texture: faint contour-line SVG pattern on the panel header only.
- z-index: map 0 · panel 20 · map controls 30 · toasts 50.

## Motion
150–250ms, `cubic-bezier(.2,.7,.2,1)`. One load reveal (panel slides in 12px + fade, staggered 60ms for sections).
Map `flyTo` for hotspot selection. All disabled under `prefers-reduced-motion`.

## Components
- **Cartouche** — sheet title block: LGA name (display), sheet number, data date, contour texture.
- **LGA switcher** — native `<select>` with label, styled; 44px tall.
- **Layer radio** — fieldset of radio cards (Recurring 2021–26 · Latest event · Off) + boundary checkbox.
- **Legend** — stepped ramp with numerals under each step; event swatch with label.
- **Hotspot list** — numbered rows (signal-coloured badge = same number as map marker), place, hectares. Button rows, full keyboard support; selecting flies the map and opens its popup.
- **Notice** — "What this map can and can't tell you", collapsible `<details>`.
- **Attribution footer** — data licences, always visible when panel expanded.
- **Bottom sheet (≤ 768px)** — panel docks to bottom, peek height 38vh, toggle button with `aria-expanded`.

## Accessibility checklist
- Contrast ≥ 4.5:1 text, ≥ 3:1 UI; focus ring 3px `--accent` + 2px offset.
- Skip link to panel; map has `aria-label`; hotspot list is the text alternative to the map.
- All user/API strings rendered with `textContent` (never `innerHTML`).
- `lang="en-NG"`; touch targets ≥ 44px with ≥ 8px gaps.

## Anti-patterns (do not)
Sidebar + card grid dashboards · purple/pink gradients · emoji icons · colour-only encoding ·
motion on data layers · hiding limitations · overclaiming ("blocked drain here").
