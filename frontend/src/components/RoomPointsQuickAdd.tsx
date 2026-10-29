import { useMemo, useState } from 'react';
import { ApiError } from '../api/http';
import { createRoomPoint, updateRoomPoint } from '../api/roomPoints';
import { useI18n } from '../hooks/useI18n';
import type { PriceItem } from '../types/priceItem';
import type { RoomPoint } from '../types/roomPoints';
import { resolveKey } from '../utils/i18nKeys';
import { formatPlain, positiveAmount } from '../utils/paymentFormat';
import { Ico } from './Ico';
import { primaryButton, secondaryButton } from './paymentUi';

type Eligible = Pick<PriceItem, 'id' | 'code' | 'name_key' | 'display_name' | 'unit' | 'category'>;

/** The categories whose items are points and routes by their nature; the other items in pieces / metres (corners, seams, ...) wait behind a button. */
const POINT_CATEGORIES = ['ELECTRICAL', 'PLUMBING', 'POINTS_ROUTES'];
/** The typical set (owner 2026-10-29): one piece of every electric and plumbing point -- the quantity is the owner's to correct, nothing is guessed per room. */
const TYPICAL_CATEGORIES = ['ELECTRICAL', 'PLUMBING'];

interface RoomPointsQuickAddProps {
  projectId: string;
  roomId: string;
  eligible: Eligible[];
  /** The rows the room has: an item that is already there is shown with its quantity and the new quantity is added to that row (no duplicate row). */
  rows: RoomPoint[];
  onSaved: (written: number) => void;
  onCancel: () => void;
}

function nameOf(item: Eligible, t: unknown): string {
  return item.display_name ?? (item.name_key ? resolveKey(t, item.name_key) : item.code);
}

/**
 * B8: several points in one go. The items of the trades of the points and routes stand in one list with a quantity field each; the owner types the quantities (or taps the typical
 * set) and saves them with one button. An item the room has already is marked and its row grows instead of a second row appearing.
 */
export function RoomPointsQuickAdd({ projectId, roomId, eligible, rows, onSaved, onCancel }: RoomPointsQuickAddProps) {
  const { t } = useI18n();
  const text = t.roomPoints;
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [showOthers, setShowOthers] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const main = useMemo(() => eligible.filter((item) => POINT_CATEGORIES.includes(item.category)), [eligible]);
  const others = useMemo(() => eligible.filter((item) => !POINT_CATEGORIES.includes(item.category)), [eligible]);
  const typical = useMemo(() => main.filter((item) => item.unit === 'PCS' && TYPICAL_CATEGORIES.includes(item.category)), [main]);
  const existing = (itemId: string) => rows.find((row) => row.item.id === itemId);
  const filled = Object.entries(quantities).filter(([, value]) => value.trim() !== '');

  const setQuantity = (id: string, value: string) => setQuantities((current) => ({ ...current, [id]: value }));
  const applyTypical = () =>
    setQuantities((current) => {
      const next = { ...current };
      for (const item of typical) if ((next[item.id] ?? '').trim() === '') next[item.id] = '1';
      return next;
    });

  const save = async () => {
    if (busy) return;
    const todo: Array<{ id: string; value: string }> = [];
    for (const [id, raw] of filled) {
      const value = positiveAmount(raw);
      if (value === null) {
        setFailure(text.err_quantity);
        return;
      }
      todo.push({ id, value });
    }
    if (todo.length === 0) return;
    setBusy(true);
    setFailure(null);
    let written = 0;
    try {
      for (const { id, value } of todo) {
        const row = existing(id);
        if (row) {
          const sum = (Number(row.quantity) + Number(value)).toFixed(2);
          await updateRoomPoint(projectId, roomId, row.id, { quantity: sum });
        } else {
          await createRoomPoint(projectId, roomId, { price_item_id: id, quantity: value, note: null });
        }
        written += 1;
        setQuantities((current) => {
          const next = { ...current };
          delete next[id]; // what is saved is not saved twice by a second tap after a failure further down the list
          return next;
        });
      }
      onSaved(written);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : undefined;
      setFailure(code === 'POINT_ITEM_ARCHIVED' ? text.err_item_archived : code === 'POINT_ITEM_UNKNOWN' ? text.err_item_unknown : text.save_error);
      setBusy(false);
      if (written > 0) onSaved(written); // the list shows what was saved already; the form stays with the rest
    }
  };

  const renderItem = (item: Eligible) => {
    const there = existing(item.id);
    const unit = item.unit === 'LM' ? text.unit_lm : text.unit_pcs;
    return (
      <li key={item.id} aria-label={`room-qa-item-${item.id}`} className="py-1.5 space-y-1">
        <div className="flex items-center gap-3">
          <label htmlFor={`room-qa-qty-${item.id}`} className="min-w-0 flex-1 text-sm text-slate-900 break-words">{nameOf(item, t)}</label>
          <input
            id={`room-qa-qty-${item.id}`}
            aria-label={`room-qa-qty-${item.id}`}
            inputMode="decimal"
            autoComplete="off"
            value={quantities[item.id] ?? ''}
            placeholder="0"
            onChange={(event) => setQuantity(item.id, event.target.value)}
            className="w-20 shrink-0 min-h-11 border border-slate-200 rounded-xl px-2 py-2 text-base text-center text-slate-900 pe-surface"
          />
          <span className="w-9 shrink-0 text-xs text-slate-500">{unit}</span>
        </div>
        {there && (
          <p aria-label={`room-qa-there-${item.id}`} className="text-xs text-amber-700 break-words">
            {text.qa_there.replace('{n}', `${formatPlain(there.quantity)} ${unit}`)}
          </p>
        )}
      </li>
    );
  };

  return (
    <div aria-label="room-points-quick-add" className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="text-sm font-semibold text-slate-900 break-words">{text.qa_title}</h3>
      <p className="text-xs text-slate-600 break-words">{text.qa_hint}</p>
      {typical.length > 0 && (
        <button type="button" aria-label="room-qa-typical" onClick={applyTypical} className={secondaryButton}>
          <Ico>⚡</Ico>{text.qa_typical}
        </button>
      )}
      {main.length === 0 ? (
        <p className="text-sm text-slate-600 break-words">{text.qa_none}</p>
      ) : (
        <ul className="divide-y divide-slate-100">{main.map(renderItem)}</ul>
      )}
      {others.length > 0 && (
        <>
          <button type="button" aria-label="room-qa-others" aria-expanded={showOthers} onClick={() => setShowOthers((on) => !on)} className={secondaryButton}>
            {showOthers ? text.qa_others_hide : text.qa_others_show.replace('{n}', String(others.length))}
          </button>
          {showOthers && <ul aria-label="room-qa-others-list" className="divide-y divide-slate-100">{others.map(renderItem)}</ul>}
        </>
      )}
      {failure && <p role="alert" className="text-sm text-red-600 break-words">{failure}</p>}
      <div className="flex flex-col gap-2">
        <button type="button" aria-label="room-qa-save" disabled={busy || filled.length === 0} onClick={() => void save()} className={primaryButton}>
          <Ico>{busy ? '⏳' : '💾'}</Ico>{busy ? t.common.saving : text.qa_save.replace('{n}', String(filled.length))}
        </button>
        <button type="button" aria-label="room-qa-cancel" onClick={onCancel} className={secondaryButton}>
          <Ico>✖️</Ico>{t.common.cancel}
        </button>
      </div>
    </div>
  );
}
