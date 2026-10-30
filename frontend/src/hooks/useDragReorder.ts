import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, TouchEvent as ReactTouchEvent } from 'react';
import { hapticSelect } from '../utils/telegramHaptics';

/** Move one item of a list to another place (the others keep their order). */
export function moveItem<T>(list: readonly T[], from: number, to: number): T[] {
  if (from === to || from < 0 || from >= list.length) return [...list];
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(Math.max(0, Math.min(to, next.length)), 0, item);
  return next;
}

/** Where the held row belongs: the number of the OTHER rows whose middle is above the finger. */
export function dropIndex(pointerY: number, middles: readonly number[], held: number): number {
  let index = 0;
  middles.forEach((middle, i) => {
    if (i !== held && middle < pointerY) index += 1;
  });
  return index;
}

/** A press on a control of the row (a button, a field) is that control's, never the start of a drag. */
const INTERACTIVE = 'button, input, textarea, select, a, label';
const HOLD_MS = 350; // press and hold a row this long to pick it up
const SLOP_PX = 8; // a finger that moves more before that is scrolling the page
const EDGE_PX = 90; // near the top / bottom edge the page scrolls by itself
const BOTTOM_BARS_PX = 140; // the bottom navigation + the "Gotowe" bar cover the lower edge

interface Options {
  ids: readonly string[];
  /** Called once, when the row is let go at a new place, with the whole new order. */
  onDrop: (nextIds: string[]) => void;
  disabled?: boolean;
}

/**
 * Press-and-hold drag of the rows of a list (the order of walls): hold a row ~0.35 s (or take its ⠿ handle at once), move the finger, let go.
 * The rows reorder live under the finger, the page scrolls by itself near its edges, and the new order is given back once at the drop.
 * Touch (Telegram WebView on a phone) and a mouse (development in a browser) both work; a quick swipe still scrolls the page.
 */
export function useDragReorder({ ids, onDrop, disabled = false }: Options) {
  const [order, setOrder] = useState<string[] | null>(null); // the live order while a row is held
  const [heldId, setHeldId] = useState<string | null>(null);
  const rows = useRef(new Map<string, HTMLElement>());
  const live = useRef<{ id: string; order: string[]; start: string[]; y: number } | null>(null);
  const pending = useRef<{ id: string; x: number; y: number; timer: number } | null>(null);
  const frame = useRef<number | null>(null);
  const dropRef = useRef(onDrop);
  dropRef.current = onDrop;

  const cancelPending = () => {
    if (pending.current) window.clearTimeout(pending.current.timer);
    pending.current = null;
  };

  const place = useCallback((y: number) => {
    const state = live.current;
    if (!state) return;
    state.y = y;
    const held = state.order.indexOf(state.id);
    const middles = state.order.map((id) => {
      const box = rows.current.get(id)?.getBoundingClientRect();
      return box ? box.top + box.height / 2 : Number.POSITIVE_INFINITY;
    });
    const to = dropIndex(y, middles, held);
    if (to !== held) {
      state.order = moveItem(state.order, held, to);
      setOrder(state.order);
      hapticSelect('step');
    }
  }, []);

  const scrollTick = useCallback(() => {
    const state = live.current;
    if (!state) {
      frame.current = null;
      return;
    }
    const bottom = window.innerHeight - BOTTOM_BARS_PX;
    let step = 0;
    if (state.y < EDGE_PX) step = -Math.ceil((EDGE_PX - state.y) / 6);
    else if (state.y > bottom - EDGE_PX) step = Math.ceil((state.y - (bottom - EDGE_PX)) / 6);
    if (step !== 0) {
      window.scrollBy(0, step);
      place(state.y);
    }
    frame.current = window.requestAnimationFrame(scrollTick);
  }, [place]);

  const finish = useCallback((commit: boolean) => {
    cancelPending();
    const state = live.current;
    live.current = null;
    if (frame.current !== null) window.cancelAnimationFrame(frame.current);
    frame.current = null;
    setHeldId(null);
    setOrder(null);
    if (state && commit && state.order.some((id, i) => id !== state.start[i])) dropRef.current(state.order);
  }, []);

  const begin = useCallback((id: string, y: number) => {
    cancelPending();
    if (disabled || !ids.includes(id)) return;
    live.current = { id, order: [...ids], start: [...ids], y };
    setOrder([...ids]);
    setHeldId(id);
    hapticSelect('pick');
    if (frame.current === null) frame.current = window.requestAnimationFrame(scrollTick);
  }, [disabled, ids, scrollTick]);

  // While a row is held the finger must not scroll the page: a non-passive touchmove on the document stops it.
  useEffect(() => {
    const onTouchMove = (event: TouchEvent) => {
      const touch = event.touches[0];
      if (!touch) return;
      if (live.current) {
        event.preventDefault();
        place(touch.clientY);
      } else if (pending.current && Math.hypot(touch.clientX - pending.current.x, touch.clientY - pending.current.y) > SLOP_PX) {
        cancelPending(); // the finger is scrolling, not holding
      }
    };
    const onTouchEnd = () => finish(true);
    const onTouchCancel = () => finish(false);
    const onPointerMove = (event: PointerEvent) => {
      if (live.current && event.pointerType !== 'touch') place(event.clientY);
    };
    const onPointerUp = (event: PointerEvent) => {
      if (event.pointerType !== 'touch') finish(true);
    };
    document.addEventListener('touchmove', onTouchMove, { passive: false });
    document.addEventListener('touchend', onTouchEnd);
    document.addEventListener('touchcancel', onTouchCancel);
    document.addEventListener('pointermove', onPointerMove);
    document.addEventListener('pointerup', onPointerUp);
    return () => {
      document.removeEventListener('touchmove', onTouchMove);
      document.removeEventListener('touchend', onTouchEnd);
      document.removeEventListener('touchcancel', onTouchCancel);
      document.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('pointerup', onPointerUp);
    };
  }, [finish, place]);

  useEffect(() => () => finish(false), [finish]);

  /** The props of a row: its element is measured, and press-and-hold picks it up. */
  const rowProps = (id: string) => ({
    ref: (element: HTMLElement | null) => {
      if (element) rows.current.set(id, element);
      else rows.current.delete(id);
    },
    onTouchStart: (event: ReactTouchEvent) => {
      if (disabled || live.current || (event.target as HTMLElement).closest(INTERACTIVE)) return;
      const touch = event.touches[0];
      cancelPending();
      pending.current = { id, x: touch.clientX, y: touch.clientY, timer: window.setTimeout(() => begin(id, touch.clientY), HOLD_MS) };
    },
    onMouseDown: (event: ReactMouseEvent) => {
      if (disabled || live.current || event.button !== 0 || (event.target as HTMLElement).closest(INTERACTIVE)) return;
      const y = event.clientY;
      cancelPending();
      pending.current = { id, x: event.clientX, y, timer: window.setTimeout(() => begin(id, y), HOLD_MS) };
    },
    onMouseUp: () => cancelPending(),
    onContextMenu: (event: ReactMouseEvent) => {
      if (pending.current || live.current) event.preventDefault(); // a long press must not open the phone's menu
    },
  });

  /** The props of the ⠿ handle: it picks the row up at once (no waiting). */
  const handleProps = (id: string) => ({
    onPointerDown: (event: ReactPointerEvent) => {
      if (disabled) return;
      event.preventDefault();
      begin(id, event.clientY);
    },
  });

  return { order: order ?? [...ids], heldId, rowProps, handleProps };
}
