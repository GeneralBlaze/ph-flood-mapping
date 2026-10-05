// Pure helpers for the animated drainage-flow layer (see flow-layer.js).

const MIN_WIDTH = 1;
const MAX_WIDTH = 4;

/** Position, direction and opacity of an arrow t (0..1) of the way along a segment. */
export function arrowFrame(start, end, t) {
  return {
    x: start.x + (end.x - start.x) * t,
    y: start.y + (end.y - start.y) * t,
    angle: Math.atan2(end.y - start.y, end.x - start.x),
    alpha: Math.sin(Math.PI * t),
  };
}

/** Stable pseudo-random phase per segment so arrows don't move in lockstep. */
export function phaseFor(index) {
  const x = Math.sin(index * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

/** Wider lines where more land drains through (upstream area in km²). */
export function lineWidth(upstreamKm2) {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, MIN_WIDTH + Math.log10(Math.max(upstreamKm2, 1))));
}

const BASE_ZOOM = 13;
const GROWTH_PER_ZOOM = 1.4;
const MAX_SCALE = 3.5;
const MIN_ARROW_SEGMENT_PX = 14;
const MAX_ARROWS_PER_SEGMENT = 6;

/** Size multiplier for lines and arrows: 1 at city scale, larger at street level. */
export function zoomScale(zoom) {
  return Math.min(MAX_SCALE, Math.max(1, GROWTH_PER_ZOOM ** (zoom - BASE_ZOOM)));
}

/** Arrows to draw on a segment lengthPx long on screen, one per spacingPx. */
export function arrowCount(lengthPx, spacingPx) {
  if (lengthPx < MIN_ARROW_SEGMENT_PX) return 0;
  return Math.min(MAX_ARROWS_PER_SEGMENT, Math.max(1, Math.floor(lengthPx / spacingPx)));
}
