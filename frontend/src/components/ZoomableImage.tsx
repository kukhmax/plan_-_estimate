import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { PhotoAnnotationRead } from '../types/photo';
import {
  Box,
  IDENTITY_VIEW,
  Point,
  PinchStart,
  View,
  ZOOMED_THRESHOLD,
  clampView,
  doubleTapView,
  pinchView,
  zoomAt,
} from '../utils/zoomMath';
import { PointMarkerLayer } from './PointMarkerLayer';

// A picture that can be zoomed with two fingers, panned with one finger when zoomed, double-tapped (closer / back) and, on a
// desktop, zoomed with the wheel. The picture is the display image (the original is never served, contract §7), so zooming
// past its native pixels only enlarges them; the limit is therefore modest.

export const MAX_ZOOM = 6;
const DOUBLE_TAP_MS = 300;
const DOUBLE_TAP_DISTANCE = 30;
const TAP_SLOP = 10;
const WHEEL_STEP = 0.002;
/** While placing a marker a tap this short counts (no double-tap wait, so the marker lands immediately). */
const PLACE_TAP_MS = 600;

interface ZoomableImageProps {
  src: string;
  alt: string;
  onError?: () => void;
  /** Called on the first gesture (the host may hide its hint). */
  onInteract?: () => void;
  /** Point markers drawn over the picture; they follow its zoom and pan. */
  markers?: readonly PhotoAnnotationRead[];
  selectedMarkerId?: string | null;
  onMarkerSelect?: (marker: PhotoAnnotationRead) => void;
  /** Marker placing mode: a tap puts a marker (x, y = fractions of the picture) instead of waiting for a double tap. */
  placing?: boolean;
  onPlace?: (x: number, y: number) => void;
}

interface ImageBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

const distanceBetween = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
const midpoint = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

export function ZoomableImage({
  src,
  alt,
  onError,
  onInteract,
  markers = [],
  selectedMarkerId = null,
  onMarkerSelect,
  placing = false,
  onPlace,
}: ZoomableImageProps) {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [view, setView] = useState<View>(IDENTITY_VIEW);
  const viewRef = useRef<View>(IDENTITY_VIEW);
  const pointers = useRef(new Map<number, Point>());
  const pinchStart = useRef<PinchStart | null>(null);
  const tapStart = useRef<{ x: number; y: number; time: number } | null>(null);
  const lastTap = useRef<{ x: number; y: number; time: number } | null>(null);

  // Where the picture sits inside the container (the marker layer is laid over exactly this box).
  const [imageBox, setImageBox] = useState<ImageBox | null>(null);
  const measureImage = () => {
    const image = imageRef.current;
    if (!image) return;
    setImageBox((previous) => {
      const next = { left: image.offsetLeft, top: image.offsetTop, width: image.offsetWidth, height: image.offsetHeight };
      return previous && previous.left === next.left && previous.top === next.top && previous.width === next.width && previous.height === next.height
        ? previous
        : next;
    });
  };
  useLayoutEffect(measureImage, [src]);
  useEffect(() => {
    window.addEventListener('resize', measureImage);
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measureImage);
    if (observer && containerRef.current) observer.observe(containerRef.current);
    return () => {
      window.removeEventListener('resize', measureImage);
      observer?.disconnect();
    };
  }, []);

  const commit = (next: View) => {
    viewRef.current = next;
    setView(next);
  };

  const measure = (): { box: Box; origin: Point } => {
    const rect = containerRef.current?.getBoundingClientRect();
    const image = imageRef.current;
    const cw = rect?.width ?? 0;
    const ch = rect?.height ?? 0;
    return {
      box: { cw, ch, iw: image?.offsetWidth ?? 0, ih: image?.offsetHeight ?? 0 },
      origin: { x: (rect?.left ?? 0) + cw / 2, y: (rect?.top ?? 0) + ch / 2 },
    };
  };
  const relative = (point: Point, origin: Point): Point => ({ x: point.x - origin.x, y: point.y - origin.y });

  const onPointerDown = (event: React.PointerEvent) => {
    onInteract?.();
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.current.size === 2) {
      const [a, b] = Array.from(pointers.current.values());
      const { origin } = measure();
      pinchStart.current = { view: viewRef.current, mid: relative(midpoint(a, b), origin), distance: distanceBetween(a, b) };
      tapStart.current = null;
    } else if (pointers.current.size === 1) {
      tapStart.current = { x: event.clientX, y: event.clientY, time: Date.now() };
    }
  };

  const onPointerMove = (event: React.PointerEvent) => {
    const previous = pointers.current.get(event.pointerId);
    if (!previous) return;
    const current = { x: event.clientX, y: event.clientY };
    pointers.current.set(event.pointerId, current);
    const { box, origin } = measure();
    if (pointers.current.size === 2 && pinchStart.current) {
      const [a, b] = Array.from(pointers.current.values());
      commit(pinchView(pinchStart.current, relative(midpoint(a, b), origin), distanceBetween(a, b), box, MAX_ZOOM));
      return;
    }
    const start = tapStart.current;
    if (start && Math.hypot(current.x - start.x, current.y - start.y) > TAP_SLOP) tapStart.current = null;
    if (pointers.current.size === 1 && viewRef.current.scale > ZOOMED_THRESHOLD) {
      const now = viewRef.current;
      commit(clampView({ scale: now.scale, x: now.x + current.x - previous.x, y: now.y + current.y - previous.y }, box, MAX_ZOOM));
    }
  };

  const onPointerEnd = (event: React.PointerEvent) => {
    if (!pointers.current.has(event.pointerId)) return;
    pointers.current.delete(event.pointerId);
    if (pointers.current.size < 2) pinchStart.current = null;
    const start = tapStart.current;
    tapStart.current = null;
    if (event.type !== 'pointerup' || !start || pointers.current.size > 0) return;
    const now = Date.now();
    if (placing && onPlace) {
      const rect = imageRef.current?.getBoundingClientRect();
      if (rect && rect.width > 0 && rect.height > 0 && now - start.time <= PLACE_TAP_MS) {
        const x = (start.x - rect.left) / rect.width;
        const y = (start.y - rect.top) / rect.height;
        if (x >= 0 && x <= 1 && y >= 0 && y <= 1) onPlace(x, y);
      }
      return;
    }
    if (now - start.time > DOUBLE_TAP_MS) return;
    const previous = lastTap.current;
    if (previous && now - previous.time <= DOUBLE_TAP_MS && Math.hypot(start.x - previous.x, start.y - previous.y) <= DOUBLE_TAP_DISTANCE) {
      lastTap.current = null;
      const { box, origin } = measure();
      commit(doubleTapView(viewRef.current, relative({ x: start.x, y: start.y }, origin), box, MAX_ZOOM));
    } else {
      lastTap.current = { x: start.x, y: start.y, time: now };
    }
  };

  const onWheel = (event: React.WheelEvent) => {
    onInteract?.();
    const { box, origin } = measure();
    const next = viewRef.current.scale * Math.exp(-event.deltaY * WHEEL_STEP);
    commit(zoomAt(viewRef.current, next, relative({ x: event.clientX, y: event.clientY }, origin), box, MAX_ZOOM));
  };

  const zoomed = view.scale > ZOOMED_THRESHOLD;
  return (
    <div
      ref={containerRef}
      data-testid="zoomable-image"
      className="relative flex h-full w-full select-none items-center justify-center overflow-hidden"
      style={{ touchAction: 'none' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onWheel={onWheel}
    >
      <img
        ref={imageRef}
        src={src}
        alt={alt}
        referrerPolicy="no-referrer"
        draggable={false}
        onDragStart={(event) => event.preventDefault()}
        onError={onError}
        className="max-h-full max-w-full object-contain"
        style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`, transformOrigin: 'center', willChange: 'transform' }}
      />
      {imageBox && markers.length > 0 && onMarkerSelect && (
        <div
          className="pointer-events-none absolute"
          style={{
            left: imageBox.left,
            top: imageBox.top,
            width: imageBox.width,
            height: imageBox.height,
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
            transformOrigin: 'center',
            willChange: 'transform',
          }}
        >
          <PointMarkerLayer markers={markers} selectedId={selectedMarkerId} onSelect={onMarkerSelect} inverseScale={1 / view.scale} />
        </div>
      )}
      {zoomed && (
        <button
          type="button"
          aria-label={t.photos.viewer.zoom_reset.replace('{value}', (Math.round(view.scale * 10) / 10).toString())}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={() => commit(IDENTITY_VIEW)}
          className="absolute bottom-3 left-1/2 flex min-h-11 min-w-11 -translate-x-1/2 items-center justify-center rounded-full bg-black/60 px-4 text-sm font-semibold text-white"
        >
          {(Math.round(view.scale * 10) / 10).toString()}×
        </button>
      )}
    </div>
  );
}
