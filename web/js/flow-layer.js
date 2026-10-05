import { arrowCount, arrowFrame, lineWidth, phaseFor, zoomScale } from "./flow-math.js";

// Canvas layer drawing drainage paths with arrows gliding downstream, like a
// wind map. One canvas instead of thousands of markers keeps phones smooth.
const CYCLE_MS = 1800;
const ARROW_PX = 4;
const ARROW_SPACING_PX = 70; // one arrow per this much line on screen
const CASING = "rgba(255, 255, 255, 0.75)"; // light outline keeps lines readable on satellite imagery

export function createFlowLayer({ colour, reducedMotion, arrowPx = ARROW_PX, lineAlpha = 0.55, widthScale = 1, pane = "flowPane", zIndex = 450, casing = true }) {
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
    const scale = zoomScale(map.getZoom());
    const bounds = map.getBounds().pad(0.05);
    const visible = [];
    segments.forEach(([lon1, lat1, lon2, lat2, upa], i) => {
      if (!bounds.contains([lat1, lon1])) return;
      visible.push({ a: map.latLngToContainerPoint([lat1, lon1]), b: map.latLngToContainerPoint([lat2, lon2]), upa, i });
    });
    ctx.lineCap = "round";
    // Casing first, then lines on top, so neighbouring segments don't paint over each other's outline
    const passes = casing ? [[CASING, 2.5, 1], [colour, 0, lineAlpha]] : [[colour, 0, lineAlpha]];
    for (const [style, extra, alpha] of passes) {
      ctx.strokeStyle = style;
      ctx.globalAlpha = alpha;
      for (const { a, b, upa } of visible) {
        ctx.lineWidth = lineWidth(upa) * widthScale * scale + extra;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
    }
    for (const { a, b, upa, i } of visible) drawArrows(ctx, a, b, upa, i, scale, time);
    ctx.globalAlpha = 1;
  }

  function drawArrows(ctx, a, b, upa, i, scale, time) {
    const count = arrowCount(Math.hypot(b.x - a.x, b.y - a.y), ARROW_SPACING_PX);
    // Bigger channels get bigger arrows, so the main drainage routes read first
    const size = arrowPx * scale * (0.75 + 0.25 * lineWidth(upa));
    for (let k = 0; k < count; k++) {
      const t = reducedMotion ? (k + 0.5) / count : ((time / CYCLE_MS + phaseFor(i) + k / count) % 1);
      const arrow = arrowFrame(a, b, t);
      ctx.save();
      ctx.translate(arrow.x, arrow.y);
      ctx.rotate(arrow.angle);
      ctx.beginPath();
      ctx.moveTo(size, 0);
      ctx.lineTo(-size, -size * 0.8);
      ctx.lineTo(-size, size * 0.8);
      ctx.closePath();
      ctx.globalAlpha = reducedMotion ? 0.95 : arrow.alpha;
      if (casing) {
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = CASING;
        ctx.stroke();
      }
      ctx.fillStyle = colour;
      ctx.fill();
      ctx.restore();
    }
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
