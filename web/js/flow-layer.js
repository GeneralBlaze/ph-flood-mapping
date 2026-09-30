import { arrowFrame, lineWidth, phaseFor } from "./flow-math.js";

// Canvas layer drawing drainage paths with arrows gliding downstream, like a
// wind map. One canvas instead of thousands of markers keeps phones smooth.
const CYCLE_MS = 1800;
const MIN_ARROW_PX = 14; // segments shorter than this on screen get no arrow
const ARROW_PX = 4;

export function createFlowLayer({ colour, reducedMotion, arrowPx = ARROW_PX, minArrowPx = MIN_ARROW_PX, lineAlpha = 0.55, widthScale = 1, pane = "flowPane", zIndex = 450 }) {
  let map = null;
  let canvas = null;
  let segments = [];
  let frame = 0;

  function resize() {
    const size = map.getSize();
    const ratio = window.devicePixelRatio || 1;
    canvas.width = size.x * ratio;
    canvas.height = size.y * ratio;
    canvas.style.width = `${size.x}px`;
    canvas.style.height = `${size.y}px`;
    canvas.getContext("2d").setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function reposition() {
    L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
  }

  function draw(time) {
    const ctx = canvas.getContext("2d");
    const size = map.getSize();
    ctx.clearRect(0, 0, size.x, size.y);
    ctx.strokeStyle = colour;
    ctx.fillStyle = colour;
    const bounds = map.getBounds().pad(0.05);
    segments.forEach(([lon1, lat1, lon2, lat2, upa], i) => {
      if (!bounds.contains([lat1, lon1])) return;
      const a = map.latLngToContainerPoint([lat1, lon1]);
      const b = map.latLngToContainerPoint([lat2, lon2]);
      ctx.globalAlpha = lineAlpha;
      ctx.lineWidth = lineWidth(upa) * widthScale;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      if (Math.hypot(b.x - a.x, b.y - a.y) < minArrowPx) return;
      const t = reducedMotion ? 0.5 : ((time / CYCLE_MS + phaseFor(i)) % 1);
      const arrow = arrowFrame(a, b, t);
      ctx.globalAlpha = reducedMotion ? 0.9 : arrow.alpha;
      ctx.save();
      ctx.translate(arrow.x, arrow.y);
      ctx.rotate(arrow.angle);
      ctx.beginPath();
      ctx.moveTo(arrowPx, 0);
      ctx.lineTo(-arrowPx, -arrowPx * 0.8);
      ctx.lineTo(-arrowPx, arrowPx * 0.8);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    });
    ctx.globalAlpha = 1;
  }

  function loop(time) {
    draw(time);
    if (!reducedMotion) frame = requestAnimationFrame(loop);
  }

  const redraw = () => {
    reposition();
    if (reducedMotion) draw(0);
  };

  const onResize = () => {
    resize();
    redraw();
  };

  return {
    setData(data) {
      segments = data ?? [];
      if (map) redraw();
    },
    addTo(targetMap) {
      map = targetMap;
      if (!map.getPane(pane)) map.createPane(pane).style.zIndex = zIndex;
      canvas = L.DomUtil.create("canvas", "flow-canvas", map.getPane(pane));
      canvas.setAttribute("aria-hidden", "true");
      resize();
      reposition();
      map.on("move zoomend", redraw).on("resize", onResize);
      frame = requestAnimationFrame(loop);
      return this;
    },
    remove() {
      cancelAnimationFrame(frame);
      map?.off("move zoomend", redraw).off("resize", onResize);
      canvas?.remove();
      map = null;
    },
  };
}
