import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { ZoomableImage } from './ZoomableImage';

// jsdom has no layout and no PointerEvent: the sizes are stubbed (container 400x600, picture fitted 400x300) and the pointer
// events are plain mouse events with a pointerId.
function touch(target: Element, type: 'pointerdown' | 'pointermove' | 'pointerup' | 'pointercancel', pointerId: number, x: number, y = 300) {
  const event = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y });
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  fireEvent(target, event);
}

function renderImage(props: Partial<React.ComponentProps<typeof ZoomableImage>> = {}) {
  const onError = vi.fn();
  const onInteract = vi.fn();
  render(
    <I18nProvider>
      <ZoomableImage src="https://r2.example/d/x.jpg" alt="Foto" onError={onError} onInteract={onInteract} {...props} />
    </I18nProvider>,
  );
  const area = screen.getByTestId('zoomable-image');
  const image = screen.getByAltText('Foto') as HTMLImageElement;
  area.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 600, right: 400, bottom: 600, x: 0, y: 0, toJSON: () => ({}) });
  Object.defineProperty(image, 'offsetWidth', { configurable: true, value: 400 });
  Object.defineProperty(image, 'offsetHeight', { configurable: true, value: 300 });
  return { area, image, onError, onInteract };
}

const transformOf = (image: HTMLElement) => {
  const match = /translate\((-?[\d.]+)px, (-?[\d.]+)px\) scale\(([\d.]+)\)/.exec(image.style.transform);
  return { x: Number(match?.[1]), y: Number(match?.[2]), scale: Number(match?.[3]) };
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-07T12:00:00Z'));
});
afterEach(() => {
  vi.useRealTimers();
});

describe('ZoomableImage', () => {
  it('shows the picture whole at first, without a zoom button, and blocks the browser gestures on it', () => {
    const { area, image } = renderImage();
    expect(transformOf(image)).toEqual({ x: 0, y: 0, scale: 1 });
    expect(screen.queryByRole('button')).toBeNull();
    expect(area.style.touchAction).toBe('none');
    expect(image.draggable).toBe(false);
  });

  it('zooms with two fingers around their midpoint and tells the host about the first touch', () => {
    const { area, image, onInteract } = renderImage();
    touch(area, 'pointerdown', 1, 100);
    touch(area, 'pointerdown', 2, 300); // midpoint x=200 (the centre), spread 200
    expect(onInteract).toHaveBeenCalled();
    touch(area, 'pointermove', 2, 400);
    touch(area, 'pointermove', 1, 0); // spread 400 around the same midpoint → 2x, the picture stays centred
    expect(transformOf(image)).toEqual({ x: 0, y: 0, scale: 2 });
    touch(area, 'pointermove', 2, 500);
    touch(area, 'pointermove', 1, -100); // spread 600 → 3x
    expect(transformOf(image)).toEqual({ x: 0, y: 0, scale: 3 });
    touch(area, 'pointermove', 1, 0); // both fingers drift right by 100: the picture follows
    touch(area, 'pointermove', 2, 600);
    expect(transformOf(image).x).toBeGreaterThan(0);
  });

  it('is limited to the maximum zoom and cannot go below the whole picture', () => {
    const { area, image } = renderImage();
    touch(area, 'pointerdown', 1, 190);
    touch(area, 'pointerdown', 2, 210);
    touch(area, 'pointermove', 2, 4000);
    expect(transformOf(image).scale).toBe(6);
    touch(area, 'pointermove', 2, 200);
    expect(transformOf(image)).toEqual({ x: 0, y: 0, scale: 1 });
  });

  it('pans with one finger only when zoomed, and never beyond the picture edges', () => {
    const { area, image } = renderImage();
    touch(area, 'pointerdown', 1, 200);
    touch(area, 'pointermove', 1, 260);
    expect(transformOf(image)).toEqual({ x: 0, y: 0, scale: 1 }); // whole picture: a drag does nothing
    touch(area, 'pointerup', 1, 260);

    touch(area, 'pointerdown', 1, 190);
    touch(area, 'pointerdown', 2, 210);
    touch(area, 'pointermove', 2, 410); // spread 20 → 220: 11x → clamped to 6x
    touch(area, 'pointerup', 2, 410);
    touch(area, 'pointerup', 1, 190);
    const zoomed = transformOf(image);
    expect(zoomed.scale).toBe(6);

    touch(area, 'pointerdown', 3, 200, 300);
    touch(area, 'pointermove', 3, 150, 250);
    const panned = transformOf(image);
    expect(panned.x).toBe(zoomed.x - 50);
    expect(panned.y).toBe(zoomed.y - 50);
    touch(area, 'pointermove', 3, -5000, -5000);
    const limit = (400 * 6 - 400) / 2; // 1000 px sideways; (300*6 - 600)/2 = 600 vertically
    expect(transformOf(image)).toEqual({ x: -limit, y: -600, scale: 6 });
  });

  it('a double tap closes in on the tapped point and the next one returns to the whole picture', () => {
    const { area, image } = renderImage();
    touch(area, 'pointerdown', 1, 300, 300);
    touch(area, 'pointerup', 1, 300, 300);
    vi.advanceTimersByTime(120);
    touch(area, 'pointerdown', 1, 302, 300);
    touch(area, 'pointerup', 1, 302, 300);
    const closer = transformOf(image);
    expect(closer.scale).toBe(2.5);
    expect(closer.x).toBeLessThan(0); // the tapped point (100 px right of the centre) stays put: the picture moves left
    touch(area, 'pointerdown', 1, 200, 300);
    touch(area, 'pointerup', 1, 200, 300);
    vi.advanceTimersByTime(100);
    touch(area, 'pointerdown', 1, 200, 300);
    touch(area, 'pointerup', 1, 200, 300);
    expect(transformOf(image)).toEqual({ x: 0, y: 0, scale: 1 });
  });

  it('two slow or distant taps are not a double tap, and a drag is not a tap', () => {
    const { area, image } = renderImage();
    touch(area, 'pointerdown', 1, 300);
    touch(area, 'pointerup', 1, 300);
    vi.advanceTimersByTime(700);
    touch(area, 'pointerdown', 1, 300);
    touch(area, 'pointerup', 1, 300);
    touch(area, 'pointerdown', 1, 50);
    touch(area, 'pointerup', 1, 50); // quick, but 250 px away from the previous tap
    touch(area, 'pointerdown', 1, 50);
    touch(area, 'pointermove', 1, 90);
    touch(area, 'pointerup', 1, 90);
    touch(area, 'pointerdown', 1, 90);
    touch(area, 'pointerup', 1, 90);
    expect(transformOf(image).scale).toBe(1);
  });

  it('a long press is not a tap: a quick tap after it does not make a double tap', () => {
    const { area, image } = renderImage();
    touch(area, 'pointerdown', 1, 300);
    vi.advanceTimersByTime(600);
    touch(area, 'pointerup', 1, 300);
    vi.advanceTimersByTime(100);
    touch(area, 'pointerdown', 1, 300);
    touch(area, 'pointerup', 1, 300);
    expect(transformOf(image).scale).toBe(1);
  });

  it('a cancelled touch does not count as a tap', () => {
    const { area, image } = renderImage();
    touch(area, 'pointerdown', 1, 300);
    touch(area, 'pointercancel', 1, 300);
    touch(area, 'pointerdown', 1, 300);
    touch(area, 'pointerup', 1, 300);
    expect(transformOf(image).scale).toBe(1);
  });

  it('zooms with the mouse wheel (desktop) around the pointer', () => {
    const { area, image } = renderImage();
    fireEvent.wheel(area, { deltaY: -400, clientX: 300, clientY: 300 });
    const zoomed = transformOf(image);
    expect(zoomed.scale).toBeCloseTo(Math.exp(0.8), 5);
    expect(zoomed.x).toBeLessThan(0);
    fireEvent.wheel(area, { deltaY: 4000, clientX: 300, clientY: 300 });
    expect(transformOf(image)).toEqual({ x: 0, y: 0, scale: 1 });
  });

  it('shows a 44 px button with the zoom while zoomed; it returns to the whole picture and is not itself a touch on the picture', () => {
    const { area, image, onInteract } = renderImage();
    fireEvent.wheel(area, { deltaY: -500, clientX: 200, clientY: 300 });
    const button = screen.getByRole('button', { name: /^Powiększenie 2\.7× — / });
    expect(button).toHaveTextContent('2.7×');
    expect(button.className).toContain('min-h-11');
    onInteract.mockClear();
    touch(button, 'pointerdown', 9, 200);
    touch(button, 'pointerup', 9, 200);
    expect(onInteract).not.toHaveBeenCalled(); // the button's touch never reaches the picture's gesture handling
    fireEvent.click(button);
    expect(transformOf(image)).toEqual({ x: 0, y: 0, scale: 1 });
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('passes load errors to the host', () => {
    const { image, onError } = renderImage();
    fireEvent.error(image);
    expect(onError).toHaveBeenCalledTimes(1);
  });
});
