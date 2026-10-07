// Geometry of a zoomable picture: an image shown "contain"-fitted in a container, scaled by `scale` around the container's
// centre and shifted by (x, y) screen pixels. Points are relative to the container's centre. Pure functions, no DOM.

export interface Point {
  x: number;
  y: number;
}

export interface View {
  scale: number;
  x: number;
  y: number;
}

/** Container size (cw × ch) and the size of the fitted image at scale 1 (iw × ih). Zeros mean "not measured yet". */
export interface Box {
  cw: number;
  ch: number;
  iw: number;
  ih: number;
}

export const IDENTITY_VIEW: View = { scale: 1, x: 0, y: 0 };
export const MIN_SCALE = 1;
export const DOUBLE_TAP_SCALE = 2.5;
/** At or below this a picture counts as "not zoomed" (a pinch rarely lands on exactly 1). */
export const ZOOMED_THRESHOLD = 1.05;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/** Keeps the scale in range and the picture covering the container (no empty gaps beyond its edges once it is bigger than it). */
export function clampView(view: View, box: Box, maxScale: number): View {
  const scale = clamp(view.scale, MIN_SCALE, maxScale);
  if (scale <= MIN_SCALE) return { scale: MIN_SCALE, x: 0, y: 0 };
  if (box.cw <= 0 || box.ch <= 0 || box.iw <= 0 || box.ih <= 0) return { scale, x: view.x, y: view.y };
  const limitX = Math.max(0, (box.iw * scale - box.cw) / 2);
  const limitY = Math.max(0, (box.ih * scale - box.ch) / 2);
  return { scale, x: clamp(view.x, -limitX, limitX), y: clamp(view.y, -limitY, limitY) };
}

/** Zoom to `nextScale` keeping the picture point under `focal` where it is. */
export function zoomAt(view: View, nextScale: number, focal: Point, box: Box, maxScale: number): View {
  const scale = clamp(nextScale, MIN_SCALE, maxScale);
  const k = scale / view.scale;
  return clampView({ scale, x: focal.x - (focal.x - view.x) * k, y: focal.y - (focal.y - view.y) * k }, box, maxScale);
}

export interface PinchStart {
  view: View;
  mid: Point;
  distance: number;
}

/** Two fingers: scale follows their spread, and the picture point that was under their midpoint follows the midpoint. */
export function pinchView(start: PinchStart, mid: Point, distance: number, box: Box, maxScale: number): View {
  const scale = clamp(start.view.scale * (distance / Math.max(1, start.distance)), MIN_SCALE, maxScale);
  const pictureX = (start.mid.x - start.view.x) / start.view.scale;
  const pictureY = (start.mid.y - start.view.y) / start.view.scale;
  return clampView({ scale, x: mid.x - scale * pictureX, y: mid.y - scale * pictureY }, box, maxScale);
}

/** Double tap: back to the whole picture when zoomed, otherwise close in on the tapped point. */
export function doubleTapView(view: View, focal: Point, box: Box, maxScale: number): View {
  if (view.scale > ZOOMED_THRESHOLD) return IDENTITY_VIEW;
  return zoomAt(view, DOUBLE_TAP_SCALE, focal, box, maxScale);
}
