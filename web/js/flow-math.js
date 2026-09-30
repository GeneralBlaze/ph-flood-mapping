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
