// A freehand contour drawn around a defect (Stage 14G.5): the finger's path, as points in fractions 0..1 of the
// picture (like a marker's own x / y), is thinned out before it is saved — a finger delivers hundreds of points, the
// contour only needs its shape. The server accepts 3..120 points; the screen keeps to a smaller number.

export type OutlinePoint = [number, number];

/** Raw points closer than this (fraction of the picture) to the last kept one are not recorded. */
export const STROKE_POINT_SPACING = 0.002;
/** A stroke shorter than this (sum of its segments, fraction of the picture) is a touch, not a contour. */
export const MIN_STROKE_LENGTH = 0.03;
/** The most points kept on the phone (the server's limit is higher). */
export const OUTLINE_POINT_BUDGET = 100;
const START_TOLERANCE = 0.004;

export function pathLength(points: readonly OutlinePoint[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    total += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
  }
  return total;
}

function distanceToSegment(point: OutlinePoint, a: OutlinePoint, b: OutlinePoint): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return Math.hypot(point[0] - a[0], point[1] - a[1]);
  const t = Math.max(0, Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / lengthSquared));
  return Math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dy));
}

/** Ramer–Douglas–Peucker: keeps the points that bend the line by more than `tolerance`. */
function simplify(points: readonly OutlinePoint[], tolerance: number): OutlinePoint[] {
  if (points.length < 3) return points.slice();
  const keep = new Array<boolean>(points.length).fill(false);
  keep[0] = true;
  keep[points.length - 1] = true;
  const stack: Array<[number, number]> = [[0, points.length - 1]];
  while (stack.length > 0) {
    const [first, last] = stack.pop()!;
    let farthest = -1;
    let farthestDistance = tolerance;
    for (let i = first + 1; i < last; i += 1) {
      const distance = distanceToSegment(points[i], points[first], points[last]);
      if (distance > farthestDistance) {
        farthest = i;
        farthestDistance = distance;
      }
    }
    if (farthest !== -1) {
      keep[farthest] = true;
      stack.push([first, farthest], [farthest, last]);
    }
  }
  return points.filter((_, index) => keep[index]);
}

/**
 * The contour to save for a finished stroke, or null when the stroke is too short to be one. The shape is thinned until it
 * fits `maxPoints`; a nearly straight stroke keeps its middle point so the contour always has at least three.
 */
export function outlineFromStroke(stroke: readonly OutlinePoint[], maxPoints = OUTLINE_POINT_BUDGET): OutlinePoint[] | null {
  if (pathLength(stroke) < MIN_STROKE_LENGTH) return null; // also covers an empty or one-point stroke (length 0)
  let tolerance = START_TOLERANCE;
  let result = simplify(stroke, tolerance);
  while (result.length > maxPoints) {
    tolerance *= 1.5;
    result = simplify(stroke, tolerance);
  }
  if (result.length < 3) {
    result = [stroke[0], stroke[Math.floor(stroke.length / 2)], stroke[stroke.length - 1]];
  }
  return result.map(([x, y]) => [Math.round(x * 1e6) / 1e6, Math.round(y * 1e6) / 1e6]);
}

/** SVG `points` attribute for a contour in a 0..1 viewBox. */
export function polylinePoints(points: readonly OutlinePoint[]): string {
  return points.map(([x, y]) => `${x},${y}`).join(' ');
}
