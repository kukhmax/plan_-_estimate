import { describe, expect, it } from 'vitest';
import {
  MIN_STROKE_LENGTH,
  OUTLINE_POINT_BUDGET,
  OutlinePoint,
  STROKE_POINT_SPACING,
  outlineFromStroke,
  pathLength,
  polylinePoints,
} from './outline';

// A rectangle walked point by point with a small step, like a finger would (dense points along straight sides).
function rectangleStroke(step = 0.005): OutlinePoint[] {
  const points: OutlinePoint[] = [];
  const walk = (from: OutlinePoint, to: OutlinePoint) => {
    const length = Math.hypot(to[0] - from[0], to[1] - from[1]);
    const n = Math.max(1, Math.round(length / step));
    for (let i = 0; i < n; i += 1) points.push([from[0] + ((to[0] - from[0]) * i) / n, from[1] + ((to[1] - from[1]) * i) / n]);
  };
  walk([0.2, 0.2], [0.6, 0.2]);
  walk([0.6, 0.2], [0.6, 0.5]);
  walk([0.6, 0.5], [0.2, 0.5]);
  walk([0.2, 0.5], [0.2, 0.2]);
  points.push([0.2, 0.2]);
  return points;
}

function wigglyCircle(n: number): OutlinePoint[] {
  return Array.from({ length: n }, (_, i) => {
    const angle = (2 * Math.PI * i) / (n - 1);
    const radius = 0.2 + 0.01 * Math.sin(angle * 9);
    return [0.5 + radius * Math.cos(angle), 0.5 + radius * Math.sin(angle)] as OutlinePoint;
  });
}

describe('pathLength', () => {
  it('sums the segments', () => {
    expect(pathLength([[0, 0], [0.3, 0], [0.3, 0.4]])).toBeCloseTo(0.7);
    expect(pathLength([[0.5, 0.5]])).toBe(0);
    expect(pathLength([])).toBe(0);
  });
});

describe('outlineFromStroke', () => {
  it('constants: a touch is shorter than 3 % of the picture, points closer than 0.2 % are not recorded, at most 100 are kept', () => {
    expect(MIN_STROKE_LENGTH).toBe(0.03);
    expect(STROKE_POINT_SPACING).toBe(0.002);
    expect(OUTLINE_POINT_BUDGET).toBe(100);
  });

  it('refuses a stroke that is a touch or a tiny scratch', () => {
    expect(outlineFromStroke([])).toBeNull();
    expect(outlineFromStroke([[0.5, 0.5]])).toBeNull();
    expect(outlineFromStroke([[0.5, 0.5], [0.5, 0.5]])).toBeNull();
    expect(outlineFromStroke([[0.5, 0.5], [0.51, 0.5], [0.52, 0.5], [0.528, 0.5]])).toBeNull(); // 0.028 < 0.03
  });

  it('accepts a stroke just over the minimum length', () => {
    expect(outlineFromStroke([[0.5, 0.5], [0.52, 0.5], [0.531, 0.5]])).not.toBeNull(); // 0.031
  });

  it('thins a dense rectangle down to its corners (the shape is kept, the points are not)', () => {
    const stroke = rectangleStroke();
    expect(stroke.length).toBeGreaterThan(200);
    const outline = outlineFromStroke(stroke)!;
    expect(outline.length).toBeLessThanOrEqual(8);
    expect(outline.length).toBeGreaterThanOrEqual(5);
    for (const corner of [[0.2, 0.2], [0.6, 0.2], [0.6, 0.5], [0.2, 0.5]]) {
      expect(outline.some(([x, y]) => Math.hypot(x - corner[0], y - corner[1]) < 0.01)).toBe(true);
    }
  });

  it('starts and ends where the finger did', () => {
    const stroke = wigglyCircle(300);
    const outline = outlineFromStroke(stroke)!;
    expect(outline[0]).toEqual([Math.round(stroke[0][0] * 1e6) / 1e6, Math.round(stroke[0][1] * 1e6) / 1e6]);
    const last = stroke[stroke.length - 1];
    expect(outline[outline.length - 1]).toEqual([Math.round(last[0] * 1e6) / 1e6, Math.round(last[1] * 1e6) / 1e6]);
  });

  it('keeps within the budget however wiggly the line is, and stays inside the server limit', () => {
    const noisy: OutlinePoint[] = Array.from({ length: 2000 }, (_, i) => [0.1 + (i / 2000) * 0.8, 0.5 + (i % 2 ? 0.02 : -0.02) * ((i % 13) / 13)]);
    const outline = outlineFromStroke(noisy)!;
    expect(outline.length).toBeLessThanOrEqual(100);
    expect(outline.length).toBeGreaterThanOrEqual(3);
    const small = outlineFromStroke(noisy, 20)!;
    expect(small.length).toBeLessThanOrEqual(20);
  });

  it('a straight stroke still becomes a contour of three points (the middle one is kept)', () => {
    const straight: OutlinePoint[] = Array.from({ length: 50 }, (_, i) => [0.1 + i * 0.01, 0.5]);
    const outline = outlineFromStroke(straight)!;
    expect(outline).toHaveLength(3);
    expect(outline[1][0]).toBeGreaterThan(outline[0][0]);
    expect(outline[1][0]).toBeLessThan(outline[2][0]);
  });

  it('rounds to six decimals and every point stays within 0..1', () => {
    const outline = outlineFromStroke([[0.123456789, 0.5], [0.4, 0.7777777777], [0.9999999, 0.2]])!;
    for (const [x, y] of outline) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(1);
      expect(String(x).split('.')[1]?.length ?? 0).toBeLessThanOrEqual(6);
      expect(String(y).split('.')[1]?.length ?? 0).toBeLessThanOrEqual(6);
    }
  });
});

describe('outlineFromStroke — how much shape is kept', () => {
  it('a small dent (2 % of the picture) in a long line is still in the contour', () => {
    const stroke: OutlinePoint[] = Array.from({ length: 101 }, (_, i) => [0.1 + i * 0.008, 0.5 + (i === 30 ? 0.03 : 0)]);
    const outline = outlineFromStroke(stroke)!;
    expect(outline.some(([x, y]) => Math.abs(x - 0.34) < 0.01 && y > 0.52)).toBe(true);
  });

  it('a contour that already fits the budget is kept whole (the budget is a maximum, not a target)', () => {
    const stroke = rectangleStroke();
    const natural = outlineFromStroke(stroke)!;
    const again = outlineFromStroke(stroke, natural.length)!;
    expect(again).toEqual(natural);
    expect(outlineFromStroke(stroke, natural.length - 1)!.length).toBeLessThan(natural.length);
  });
});

describe('polylinePoints', () => {
  it('writes the SVG points attribute', () => {
    expect(polylinePoints([[0.1, 0.2], [0.3, 0.4], [1, 0]])).toBe('0.1,0.2 0.3,0.4 1,0');
    expect(polylinePoints([])).toBe('');
  });
});
