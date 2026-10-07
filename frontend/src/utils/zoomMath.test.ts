import { describe, expect, it } from 'vitest';
import { Box, IDENTITY_VIEW, clampView, doubleTapView, pinchView, zoomAt } from './zoomMath';

// A 400x600 container with a 400x300 picture fitted inside (letterboxed top and bottom).
const box: Box = { cw: 400, ch: 600, iw: 400, ih: 300 };
const MAX = 6;

describe('clampView', () => {
  it('limits the scale to 1..max and centres the picture at 1x', () => {
    expect(clampView({ scale: 0.4, x: 50, y: 50 }, box, MAX)).toEqual(IDENTITY_VIEW);
    expect(clampView({ scale: 20, x: 0, y: 0 }, box, MAX).scale).toBe(MAX);
  });

  it('keeps the picture covering the container: it can only move by the overflow on each side', () => {
    // at 2x the picture is 800x600 in a 400x600 container: free to move 200 px sideways, not at all vertically
    expect(clampView({ scale: 2, x: 999, y: 999 }, box, MAX)).toEqual({ scale: 2, x: 200, y: 0 });
    expect(clampView({ scale: 2, x: -999, y: -999 }, box, MAX)).toEqual({ scale: 2, x: -200, y: -0 });
    // at 4x it is 1600x1200: 600 px vertically
    expect(clampView({ scale: 4, x: 0, y: 700 }, box, MAX)).toEqual({ scale: 4, x: 0, y: 300 });
  });

  it('does not clamp the position while the sizes are unknown (not measured yet)', () => {
    expect(clampView({ scale: 2, x: 33, y: 44 }, { cw: 0, ch: 0, iw: 0, ih: 0 }, MAX)).toEqual({ scale: 2, x: 33, y: 44 });
  });
});

describe('zoomAt', () => {
  it('keeps the picture point under the focal point where it was', () => {
    // focal point 100 px right of the centre; at 1x the picture point there is 100 px from its centre
    const zoomed = zoomAt(IDENTITY_VIEW, 3, { x: 100, y: 0 }, box, MAX);
    expect(zoomed.scale).toBe(3);
    // the point's screen position = x + scale * pictureX = -200 + 3*100 = 100 (unchanged)
    expect(zoomed.x + zoomed.scale * 100).toBeCloseTo(100);
  });

  it('zooming at the centre does not move the picture', () => {
    expect(zoomAt(IDENTITY_VIEW, 2, { x: 0, y: 0 }, box, MAX)).toEqual({ scale: 2, x: 0, y: 0 });
  });

  it('is clamped to the maximum and back to 1x', () => {
    expect(zoomAt(IDENTITY_VIEW, 99, { x: 0, y: 0 }, box, MAX).scale).toBe(MAX);
    expect(zoomAt({ scale: 3, x: 80, y: 0 }, 0.2, { x: 0, y: 0 }, box, MAX)).toEqual(IDENTITY_VIEW);
  });
});

describe('pinchView', () => {
  const start = { view: IDENTITY_VIEW, mid: { x: 0, y: 0 }, distance: 100 };

  it('scales with the spread of the fingers', () => {
    expect(pinchView(start, { x: 0, y: 0 }, 200, box, MAX).scale).toBe(2);
    expect(pinchView(start, { x: 0, y: 0 }, 50, box, MAX)).toEqual(IDENTITY_VIEW);
    expect(pinchView(start, { x: 0, y: 0 }, 5000, box, MAX).scale).toBe(MAX);
  });

  it('moves the picture with the midpoint of the fingers', () => {
    const moved = pinchView(start, { x: 60, y: 0 }, 200, box, MAX); // spread x2 and the hand drifts 60 px right
    expect(moved).toEqual({ scale: 2, x: 60, y: 0 });
  });

  it('keeps the picture point that was under the fingers under them (fingers not at the centre)', () => {
    const offCentre = { view: IDENTITY_VIEW, mid: { x: 100, y: 0 }, distance: 100 };
    const zoomed = pinchView(offCentre, { x: 100, y: 0 }, 200, box, MAX); // spread x2, hand stays
    expect(zoomed.scale).toBe(2);
    expect(zoomed.x + zoomed.scale * 100).toBeCloseTo(100); // the point 100 px right of the centre is still at 100
  });

  it('continues from the zoom the previous pinch left', () => {
    const second = { view: { scale: 2, x: 0, y: 0 }, mid: { x: 0, y: 0 }, distance: 100 };
    expect(pinchView(second, { x: 0, y: 0 }, 150, box, MAX).scale).toBe(3);
  });

  it('survives a zero start distance', () => {
    expect(Number.isFinite(pinchView({ ...start, distance: 0 }, { x: 0, y: 0 }, 80, box, MAX).scale)).toBe(true);
  });
});

describe('doubleTapView', () => {
  it('closes in on the tapped point when the whole picture is shown', () => {
    const next = doubleTapView(IDENTITY_VIEW, { x: 100, y: 0 }, box, MAX);
    expect(next.scale).toBe(2.5);
    expect(next.x + next.scale * 100).toBeCloseTo(100);
  });

  it('returns to the whole picture when already zoomed', () => {
    expect(doubleTapView({ scale: 3, x: 40, y: 0 }, { x: 0, y: 0 }, box, MAX)).toEqual(IDENTITY_VIEW);
    expect(doubleTapView({ scale: 1.04, x: 0, y: 0 }, { x: 0, y: 0 }, box, MAX).scale).toBe(2.5); // a near-1 pinch counts as not zoomed
  });
});
