import { FormEvent, useCallback, useState } from 'react';
import { ApiError } from '../api/http';
import { fetchPriceItems } from '../api/priceItems';
import { createRoomPoint, deleteRoomPoint, fetchRoomPoints, makePointsPack, updateRoomPoint } from '../api/roomPoints';
import { useI18n } from '../hooks/useI18n';
import { useConnection } from '../offline/connection';
import type { PriceItem } from '../types/priceItem';
import type { PointItem, RoomPoint } from '../types/roomPoints';
import { MAX_POINT_NOTE_LENGTH } from '../types/roomPoints';
import { resolveKey } from '../utils/i18nKeys';
import { formatPlain, positiveAmount, toInput } from '../utils/paymentFormat';
import { Ico } from './Ico';
import { fieldClass, labelClass, primaryButton, secondaryButton } from './paymentUi';
import { VoiceInput } from './VoiceInput';

interface RoomPointsSectionProps {
  projectId: string;
  roomId: string;
}

type Eligible = Pick<PriceItem, 'id' | 'code' | 'name_key' | 'display_name' | 'unit'>;

/** The categories of the trades that work in points and routes: while the price book has none of them, the typical items are offered. */
const TRADE_CATEGORIES = ['ELECTRICAL', 'PLUMBING', 'TILE', 'POINTS_ROUTES'];

/** The two buttons of a row stand side by side: a narrow half is enough, a long word wraps. */
const compactButton = 'w-full min-h-11 px-2 py-2 text-sm leading-tight rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium break-words hover:bg-slate-50 disabled:opacity-50';
const compactDanger = 'w-full min-h-11 px-2 py-2 text-sm leading-tight rounded-xl border border-red-200 bg-red-50 text-red-800 font-semibold break-words hover:bg-red-100 disabled:opacity-50';

/** The name of a price item as the owner reads it: the own name, else the built-in name of its key, else the code. */
function itemName(item: { display_name: string | null; name_key: string | null; code: string }, t: unknown): string {
  return item.display_name ?? (item.name_key ? resolveKey(t, item.name_key) : item.code);
}

/**
 * V2-10 — the points and routes of a room: a list of "a price-book item (pieces or metres) x a quantity". Closed until it is opened, so a room's screen asks the server for
 * nothing it does not show. The estimate takes the rows with the button of the estimate. Online only.
 */
export function RoomPointsSection({ projectId, roomId }: RoomPointsSectionProps) {
  const { t } = useI18n();
  const text = t.roomPoints;
  const { offline } = useConnection();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<RoomPoint[] | null>(null);
  const [eligible, setEligible] = useState<Eligible[]>([]);
  const [hasTradeItems, setHasTradeItems] = useState(true);
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [form, setForm] = useState<{ row?: RoomPoint } | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [packBusy, setPackBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const [points, items] = await Promise.all([fetchRoomPoints(projectId, roomId), fetchPriceItems({ archived: 'active' })]);
      setRows(points);
      setEligible(items.items.filter((item) => item.unit === 'PCS' || item.unit === 'LM'));
      setHasTradeItems(items.items.some((item) => TRADE_CATEGORIES.includes(item.category)));
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [projectId, roomId]);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && rows === null) void load();
  };

  const failure = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (err.code === 'POINT_ITEM_UNKNOWN') return text.err_item_unknown;
      if (err.code === 'POINT_ITEM_ARCHIVED') return text.err_item_archived;
      if (err.code === 'POINT_UNIT_INVALID') return text.err_unit;
    }
    return text.save_error;
  };

  const saved = async () => {
    setForm(null);
    setMessage({ kind: 'ok', text: text.saved });
    await load();
  };

  const remove = async (row: RoomPoint) => {
    if (busyId) return;
    setBusyId(row.id);
    setMessage(null);
    try {
      await deleteRoomPoint(projectId, roomId, row.id);
      setConfirmId(null);
      setMessage({ kind: 'ok', text: text.deleted });
      await load();
    } catch (err) {
      setMessage({ kind: 'error', text: failure(err) });
    } finally {
      setBusyId(null);
    }
  };

  const makePack = async () => {
    if (packBusy) return;
    setPackBusy(true);
    setMessage(null);
    try {
      const result = await makePointsPack();
      setMessage({ kind: 'ok', text: result.created > 0 ? text.pack_done.replace('{n}', String(result.created)) : text.pack_none });
      await load();
    } catch (err) {
      setMessage({ kind: 'error', text: failure(err) });
    } finally {
      setPackBusy(false);
    }
  };

  return (
    <section aria-label="room-points-section" className="w-full min-w-0 max-w-full mt-5 space-y-3">
      <button
        type="button"
        aria-label="room-points-toggle"
        aria-expanded={open}
        onClick={toggle}
        className="w-full min-h-11 px-4 py-2 flex flex-wrap items-center justify-between gap-x-3 text-left text-base font-bold text-slate-900 pe-card rounded-2xl shadow-sm"
      >
        <span className="break-words"><Ico>🔌</Ico>{text.title}</span>
        <span className="text-sm font-semibold text-blue-700">{open ? text.hide : text.show}</span>
      </button>
      {open && (
        <div aria-label="room-points" className="space-y-3">
          <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>
          {loading && rows === null && <p className="text-sm text-slate-500 text-center py-3">{text.loading}</p>}
          {!loading && loadFailed && (
            <div className="space-y-2">
              <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
              <button type="button" aria-label="room-points-retry" onClick={() => void load()} className={primaryButton}><Ico>🔄</Ico>{text.retry}</button>
            </div>
          )}
          {rows && (
            <>
              {form === null ? (
                <>
                  {eligible.length > 0 && (
                    <button type="button" aria-label="room-point-add" disabled={offline} onClick={() => { setMessage(null); setForm({}); }} className={primaryButton}>
                      <Ico>➕</Ico>{text.add}
                    </button>
                  )}
                  {!hasTradeItems && (
                    <div aria-label="room-points-pack-card" className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
                      <p className="text-sm text-slate-800 break-words">{eligible.length === 0 ? text.no_items : text.pack_prompt}</p>
                      <p className="text-xs text-slate-600 break-words">{text.pack_hint}</p>
                      <button type="button" aria-label="room-points-pack" disabled={packBusy || offline} onClick={() => void makePack()} className={secondaryButton}>
                        <Ico>{packBusy ? '⏳' : '📦'}</Ico>{text.pack_button}
                      </button>
                    </div>
                  )}
                  {offline && <p aria-label="room-points-offline" className="text-xs text-slate-500 break-words">{text.needs_connection}</p>}
                </>
              ) : (
                <PointForm
                  key={form.row?.id ?? 'new'}
                  projectId={projectId}
                  roomId={roomId}
                  row={form.row}
                  eligible={eligible}
                  onSaved={() => void saved()}
                  onCancel={() => setForm(null)}
                />
              )}
              {message && (
                <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>
                  {message.text}
                </p>
              )}
              {rows.length === 0 ? (
                <p aria-label="room-points-empty" className="text-sm text-slate-500 text-center py-3">{text.empty}</p>
              ) : (
                <ul aria-label="room-points-list" className="space-y-2 min-w-0">
                  {rows.map((row) => (
                    <li key={row.id} aria-label={`room-point-${row.id}`} className="pe-card rounded-2xl p-3 shadow-sm space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <p className="min-w-0 flex-1 text-sm font-semibold text-slate-900 break-words">{itemName(row.item, t)}</p>
                        <p aria-label={`room-point-quantity-${row.id}`} className="shrink-0 text-base font-bold text-slate-900 whitespace-nowrap">
                          {formatPlain(row.quantity)} {row.item.unit === 'LM' ? text.unit_lm : text.unit_pcs}
                        </p>
                      </div>
                      {row.note && <p className="text-xs text-slate-600 whitespace-pre-wrap break-words">{row.note}</p>}
                      {confirmId !== row.id ? (
                        <div className="grid grid-cols-2 gap-2">
                          <button type="button" aria-label={`room-point-edit-${row.id}`} disabled={offline} onClick={() => { setMessage(null); setForm({ row }); }} className={compactButton}>
                            <Ico>✏️</Ico>{text.edit}
                          </button>
                          <button type="button" aria-label={`room-point-delete-${row.id}`} disabled={busyId === row.id || offline} onClick={() => setConfirmId(row.id)} className={compactButton}>
                            <Ico>🗑️</Ico>{text.delete}
                          </button>
                        </div>
                      ) : (
                        <div aria-label={`room-point-confirm-${row.id}`} className="space-y-2">
                          <p className="text-sm text-slate-800 break-words">{text.delete_confirm}</p>
                          <div className="grid grid-cols-2 gap-2">
                            <button type="button" aria-label={`room-point-delete-yes-${row.id}`} disabled={busyId === row.id} onClick={() => void remove(row)} className={compactDanger}>
                              <Ico>🗑️</Ico>{text.delete_yes}
                            </button>
                            <button type="button" aria-label={`room-point-delete-no-${row.id}`} onClick={() => setConfirmId(null)} className={compactButton}>
                              <Ico>✖️</Ico>{t.common.cancel}
                            </button>
                          </div>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

function PointForm({
  projectId, roomId, row, eligible, onSaved, onCancel,
}: { projectId: string; roomId: string; row?: RoomPoint; eligible: Eligible[]; onSaved: () => void; onCancel: () => void }) {
  const { t } = useI18n();
  const text = t.roomPoints;
  // the item of a row may have left the list of the live ones (archived, another unit): it stays chosen until the owner picks another
  const choices: Array<Eligible | PointItem> = row && !eligible.some((item) => item.id === row.item.id) ? [row.item, ...eligible] : eligible;
  const [itemId, setItemId] = useState(row?.item.id ?? '');
  const [quantity, setQuantity] = useState(toInput(row?.quantity));
  const [note, setNote] = useState(row?.note ?? '');
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const chosen = choices.find((item) => item.id === itemId);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const value = positiveAmount(quantity);
    const found: string[] = [];
    if (itemId === '') found.push('item');
    if (value === null) found.push('quantity');
    setErrors(found);
    if (found.length > 0 || value === null) return;
    const fields = { price_item_id: itemId, quantity: value, note: note.trim() !== '' ? note.trim() : null };
    setBusy(true);
    setFailure(null);
    try {
      if (row) await updateRoomPoint(projectId, roomId, row.id, fields);
      else await createRoomPoint(projectId, roomId, fields);
      onSaved();
    } catch (err) {
      const code = err instanceof ApiError ? err.code : undefined;
      setFailure(
        code === 'POINT_ITEM_UNKNOWN' ? text.err_item_unknown
          : code === 'POINT_ITEM_ARCHIVED' ? text.err_item_archived
            : code === 'POINT_UNIT_INVALID' ? text.err_unit
              : text.save_error,
      );
      setBusy(false);
    }
  };

  return (
    <form aria-label="room-point-form" onSubmit={submit} noValidate className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="text-sm font-semibold text-slate-900 break-words">{row ? text.edit_title : text.add_title}</h3>
      <div>
        <label htmlFor="room-point-item" className={labelClass}>{text.item_label}</label>
        <select id="room-point-item" aria-label="room-point-item" value={itemId} onChange={(event) => setItemId(event.target.value)} className={fieldClass}>
          <option value="">{text.item_placeholder}</option>
          {choices.map((item) => (
            <option key={item.id} value={item.id}>{`${itemName(item, t)} · ${item.unit === 'LM' ? text.unit_lm : text.unit_pcs}`}</option>
          ))}
        </select>
        {errors.includes('item') && <p role="alert" className="text-xs text-red-600 mt-1">{text.err_item}</p>}
      </div>
      <div>
        <label htmlFor="room-point-quantity" className={labelClass}>{chosen?.unit === 'LM' ? text.quantity_lm : text.quantity_pcs}</label>
        <VoiceInput name="room-point-quantity" mode="plain" onValue={(value) => setQuantity(value.replace('.', ','))}>
          <input id="room-point-quantity" aria-label="room-point-quantity" inputMode="decimal" autoComplete="off" value={quantity} placeholder="1" onChange={(event) => setQuantity(event.target.value)} className={`${fieldClass} min-w-0 flex-1`} />
        </VoiceInput>
        {errors.includes('quantity') && <p role="alert" className="text-xs text-red-600 mt-1">{text.err_quantity}</p>}
      </div>
      <div>
        <label htmlFor="room-point-note" className={labelClass}>{text.note_label}</label>
        <textarea id="room-point-note" aria-label="room-point-note" value={note} maxLength={MAX_POINT_NOTE_LENGTH} onChange={(event) => setNote(event.target.value)} className={`${fieldClass} min-h-20`} />
      </div>
      {failure && <p role="alert" className="text-sm text-red-600 break-words">{failure}</p>}
      <div className="flex flex-col gap-2">
        <button type="submit" aria-label="room-point-save" disabled={busy} className={primaryButton}>
          <Ico>{busy ? '⏳' : '💾'}</Ico>{busy ? t.common.saving : t.common.save}
        </button>
        <button type="button" aria-label="room-point-cancel" onClick={onCancel} className={secondaryButton}>
          <Ico>✖️</Ico>{t.common.cancel}
        </button>
      </div>
    </form>
  );
}
