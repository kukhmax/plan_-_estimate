import { useEffect, useSyncExternalStore } from 'react';
import { fetchTrades, saveTrades } from '../api/trades';
import type { Trade, TradeKey, TradesResponse } from '../types/trades';

// One shared `GET /api/trades` per session (V2-13): the price book, the plan of a wall, the materials and the points of a room read the same snapshot. While the answer is not
// known (no signal, not loaded yet) NOTHING is hidden: the safe side of a filter that only serves convenience.

type LoadStatus = 'idle' | 'loading' | 'ready' | 'error';
interface Snapshot {
  status: LoadStatus;
  data: TradesResponse | null;
}

let snapshot: Snapshot = { status: 'idle', data: null };
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function publish(next: Snapshot): void {
  snapshot = next;
  listeners.forEach((listener) => listener());
}
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
const getSnapshot = () => snapshot;

/** Fetch (or join the fetch in flight). Never rejects; the last good answer is kept on a failure. */
export function refreshTrades(): Promise<void> {
  if (inflight) return inflight;
  publish({ status: snapshot.data ? snapshot.status : 'loading', data: snapshot.data });
  inflight = Promise.resolve()
    .then(fetchTrades)
    .then((data) => publish(data ? { status: 'ready', data } : { status: 'error', data: snapshot.data }))
    .catch(() => publish({ status: 'error', data: snapshot.data }))
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/** Forget the cached answer (tests). */
export function resetTrades(): void {
  inflight = null;
  publish({ status: 'idle', data: null });
}

export interface TradesView {
  /** The server's answer is known; until then nothing is hidden. */
  known: boolean;
  trades: readonly Trade[];
  enabled: ReadonlySet<TradeKey>;
  isEnabled: (key: TradeKey) => boolean;
  /** A price-book category is offered: it belongs to a trade that is on, or to none (or the answer is not known). */
  categoryVisible: (category: string) => boolean;
  /** A package of the materials of a room is offered. */
  packageVisible: (pkg: string) => boolean;
  /** At least one category is hidden by the choice (the price book then offers "show all"). */
  anyHidden: boolean;
  /** The section "Punkty i trasy" of a room belongs to a trade that is on. */
  pointsVisible: boolean;
  /** At least one package of the materials of a room belongs to a trade that is on. */
  materialsVisible: boolean;
  /** Save the choice; the answer replaces the snapshot. Rejects on a failure so that the screen can say so. */
  save: (enabled: TradeKey[]) => Promise<void>;
}

const NOTHING_HIDDEN: TradesView = {
  known: false,
  trades: [],
  enabled: new Set(),
  isEnabled: () => true,
  categoryVisible: () => true,
  packageVisible: () => true,
  anyHidden: false,
  pointsVisible: true,
  materialsVisible: true,
  save: async (enabled) => {
    publish({ status: 'ready', data: await saveTrades(enabled) });
  },
};

export function useTrades(): TradesView {
  const current = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  useEffect(() => {
    if (snapshot.status === 'idle') void refreshTrades();
  }, []);
  const data = current.data;
  if (!data) return NOTHING_HIDDEN;
  const enabled = new Set<TradeKey>(data.enabled);
  const owner = (key: TradeKey) => enabled.has(key);
  const hiddenCategories = new Set(data.trades.filter((t) => !owner(t.key)).flatMap((t) => t.price_categories));
  return {
    known: true,
    trades: data.trades,
    enabled,
    isEnabled: owner,
    categoryVisible: (category) => !hiddenCategories.has(category),
    packageVisible: (pkg) => !data.trades.some((t) => !owner(t.key) && t.material_packages.includes(pkg)),
    anyHidden: hiddenCategories.size > 0,
    pointsVisible: data.trades.some((t) => t.room_points && owner(t.key)),
    materialsVisible: data.trades.some((t) => t.material_packages.length > 0 && owner(t.key)),
    save: NOTHING_HIDDEN.save,
  };
}
