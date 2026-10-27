import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/http';
import { previewTradeTransfer, runTradeTransfer } from '../api/tradeLinks';
import { useI18n } from '../hooks/useI18n';
import type { LinkTrade, TransferCandidate, TransferKind, TransferMapping, TransferMaterialKind, TransferPreview, TransferRow } from '../types/tradeLink';
import { formatQuantity } from '../utils/format';
import { resolveKey } from '../utils/i18nKeys';
import { Ico } from './Ico';

interface TradeTransferPanelProps {
  projectId: string;
  trade: LinkTrade;
  onClose: () => void;
}

const PRIMARY = 'w-full min-h-11 px-4 py-1 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50';
const SECONDARY = 'w-full min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium hover:bg-slate-50 disabled:opacity-50';
const FIELD = 'w-full border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 pe-surface min-h-11';

/** The name of a price item as the owner reads it: the own name, else the built-in name of its key, else the code. */
function itemName(item: { display_name: string | null; name_key: string | null; code: string }, t: unknown): string {
  return item.display_name ?? (item.name_key ? resolveKey(t, item.name_key) : item.code);
}

/** The number of a calculation of materials -> the typical position that fills it (to name it in the owner's language). */
const NUMBER_POSITION: Record<string, string> = {
  sockets: 'SOCKET',
  switches: 'SWITCH',
  lights: 'LIGHT_POINT',
  circuits: 'CIRCUIT',
  route_m: 'CABLE_ROUTE',
  water_points: 'WATER_POINT',
  drain_points: 'DRAIN_POINT',
  manifold_outlets: 'MANIFOLD_OUT',
  pipe_m: 'PIPE_ROUTE',
};

const BADGE: Record<TransferKind | TransferMaterialKind, string> = {
  NEW: 'bg-emerald-100 text-emerald-800',
  CHANGE: 'bg-amber-100 text-amber-800',
  SAME: 'bg-slate-200 text-slate-700',
  REMOVE: 'bg-red-100 text-red-800',
  NONE: 'bg-slate-200 text-slate-700',
  INVALID: 'bg-red-100 text-red-800',
};

/**
 * V2-14a — carrying the answers of a craftsman over into "Punkty i trasy" and the materials of the rooms. First a preview (nothing is written): which item of the price book each typical
 * position goes to (the owner may change it), and what happens in each room; then the owner's own button writes it. A second press changes nothing that is already carried.
 */
export function TradeTransferPanel({ projectId, trade, onClose }: TradeTransferPanelProps) {
  const { t } = useI18n();
  const text = t.trade_transfer;
  const [mapping, setMapping] = useState<TransferMapping>({});
  const [preview, setPreview] = useState<TransferPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [points, setPoints] = useState(true);
  const [materials, setMaterials] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const request = useRef(0);

  const errorText = useCallback(
    (err: unknown): string => {
      const code = err instanceof ApiError ? err.code : undefined;
      const table = text.errors as Record<string, string>;
      return (code && table[code]) || table.GENERIC;
    },
    [text],
  );

  const load = useCallback(
    async (choice: TransferMapping) => {
      const mine = ++request.current;
      setLoading(true);
      setLoadError(null);
      try {
        const loaded = await previewTradeTransfer(projectId, trade, choice);
        if (mine === request.current) setPreview(loaded);
      } catch (err) {
        if (mine === request.current) setLoadError(errorText(err));
      } finally {
        if (mine === request.current) setLoading(false);
      }
    },
    [projectId, trade, errorText],
  );

  useEffect(() => {
    void load({});
  }, [load]);

  const choose = (key: string, value: string) => {
    const next = { ...mapping, [key]: value === '' ? null : value };
    setMapping(next);
    setMessage(null);
    void load(next);
  };

  const run = async () => {
    if (busy || !preview) return;
    setBusy(true);
    setMessage(null);
    try {
      const done = await runTradeTransfer(projectId, trade, mapping, points, materials);
      const changed = done.points_added + done.points_changed + done.points_removed + done.materials_added + done.materials_changed + done.materials_removed;
      setMessage({
        kind: 'ok',
        text:
          changed === 0
            ? text.done_nothing
            : text.done
                .replace('{pa}', String(done.points_added))
                .replace('{pc}', String(done.points_changed))
                .replace('{pr}', String(done.points_removed))
                .replace('{ma}', String(done.materials_added))
                .replace('{mc}', String(done.materials_changed))
                .replace('{mr}', String(done.materials_removed)),
      });
      await load(mapping);
    } catch (err) {
      setMessage({ kind: 'error', text: errorText(err) });
    } finally {
      setBusy(false);
    }
  };

  const names = t.master_page.positions as Record<string, string>;
  const items = new Map<string, TransferCandidate>();
  for (const position of preview?.positions ?? []) for (const candidate of position.candidates) items.set(candidate.id, candidate);
  const kindLabel = (kind: TransferKind | TransferMaterialKind) => (text.kind as Record<string, string>)[kind];
  const rowText = (row: TransferRow) => {
    const item = items.get(row.item_id);
    const unit = item?.unit ?? 'PCS';
    const unitLabel = unit === 'LM' ? t.master_page.unit_LM : t.master_page.unit_PCS;
    const was = row.was_quantity !== null ? ` (${text.was.replace('{q}', formatQuantity(row.was_quantity, unit))})` : '';
    return `${item ? itemName(item, t) : '—'}: ${formatQuantity(row.quantity, unit)} ${unitLabel}${was}`;
  };
  const numbersText = (numbers: Record<string, string>) =>
    Object.entries(numbers)
      .map(([param, value]) => `${names[NUMBER_POSITION[param]] ?? param} ${value.includes('.') ? formatQuantity(value, 'LM') : value}`)
      .join(' · ');

  const visibleRooms = (preview?.rooms ?? []).filter((room) => room.rows.length > 0 || room.material.kind !== 'NONE');
  const answered = (preview?.positions ?? []).filter((p) => p.goes_to_points && p.answered_rooms > 0);
  const hasInvalid = visibleRooms.some((room) => room.material.kind === 'INVALID');

  return (
    <section aria-label={`trade-transfer-${trade}`} className="rounded-2xl border border-blue-200 p-3 space-y-3">
      <h4 className="text-sm font-semibold text-slate-900 break-words">{text.title}</h4>
      <p className="text-xs text-slate-600 break-words">{text.intro}</p>

      {loading && preview === null && <p className="text-sm text-slate-500 text-center py-2">{text.loading}</p>}
      {loadError && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-600 break-words">{loadError}</p>
          <button type="button" aria-label={`trade-transfer-retry-${trade}`} onClick={() => void load(mapping)} className={SECONDARY}><Ico>🔄</Ico>{text.retry}</button>
        </div>
      )}

      {preview && (
        <>
          {answered.length > 0 && (
            <div className="space-y-2">
              <h5 className="text-sm font-semibold text-slate-800 break-words">{text.items_title}</h5>
              {answered.map((position) => (
                <label key={position.key} className="block text-sm font-medium text-slate-700">
                  {names[position.key] ?? position.key}
                  <select
                    aria-label={`trade-transfer-item-${trade}-${position.key}`}
                    value={position.item_id ?? ''}
                    disabled={busy}
                    onChange={(e) => choose(position.key, e.target.value)}
                    className={`${FIELD} mt-1`}
                  >
                    <option value="">{text.pick_none}</option>
                    {position.candidates.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>{itemName(candidate, t)}</option>
                    ))}
                  </select>
                  {position.item_id === null && <span className="block text-xs text-slate-500 font-normal break-words">{text.item_missing}</span>}
                </label>
              ))}
            </div>
          )}

          <div className="space-y-1">
            <label className="flex items-start gap-3 text-sm text-slate-800 min-h-11 cursor-pointer">
              <input type="checkbox" aria-label={`trade-transfer-points-${trade}`} checked={points} onChange={(e) => setPoints(e.target.checked)} className="mt-1 h-6 w-6 shrink-0" />
              <span className="break-words">{text.opt_points}</span>
            </label>
            <label className="flex items-start gap-3 text-sm text-slate-800 min-h-11 cursor-pointer">
              <input type="checkbox" aria-label={`trade-transfer-materials-${trade}`} checked={materials} onChange={(e) => setMaterials(e.target.checked)} className="mt-1 h-6 w-6 shrink-0" />
              <span className="break-words">{text.opt_materials}</span>
            </label>
          </div>

          {visibleRooms.length === 0 ? (
            <p aria-label={`trade-transfer-empty-${trade}`} className="text-sm text-slate-500 break-words">{text.nothing}</p>
          ) : (
            <ul aria-label={`trade-transfer-rooms-${trade}`} className="space-y-2">
              {visibleRooms.map((room) => (
                <li key={room.room_id} className="rounded-xl border border-slate-200 p-3 space-y-2">
                  <p className="text-sm font-semibold text-slate-900 break-words">{room.room_name}</p>
                  {points &&
                    room.rows.map((row, index) => (
                      <div key={`${row.item_id}-${index}`} className="flex flex-wrap items-start gap-2">
                        <span className={`shrink-0 text-xs font-semibold px-2 py-1 rounded-full ${BADGE[row.kind]}`}>{kindLabel(row.kind)}</span>
                        <span className="min-w-0 flex-1 text-sm text-slate-800 break-words">{rowText(row)}</span>
                      </div>
                    ))}
                  {materials && room.material.kind !== 'NONE' && (
                    <div className="flex flex-wrap items-start gap-2">
                      <span className={`shrink-0 text-xs font-semibold px-2 py-1 rounded-full ${BADGE[room.material.kind]}`}>{kindLabel(room.material.kind)}</span>
                      <span className="min-w-0 flex-1 text-sm text-slate-800 break-words">
                        {room.material.kind === 'INVALID' ? text.material_invalid : `${text.material_label}: ${numbersText(room.material.numbers) || '—'}`}
                      </span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {preview.own_not_carried > 0 && (
            <p aria-label={`trade-transfer-own-${trade}`} className="text-xs text-slate-600 break-words">{text.own_note.replace('{count}', String(preview.own_not_carried))}</p>
          )}
          {materials && hasInvalid && <p role="alert" className="text-sm text-red-600 break-words">{text.invalid_hint}</p>}
        </>
      )}

      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>{message.text}</p>
      )}

      <div className="flex flex-col gap-2">
        <button
          type="button"
          aria-label={`trade-transfer-run-${trade}`}
          disabled={busy || loading || !preview || preview.nothing || (!points && !materials) || (materials && hasInvalid && !points)}
          onClick={() => void run()}
          className={PRIMARY}
        >
          <Ico>📥</Ico>{text.run}
        </button>
        <button type="button" aria-label={`trade-transfer-close-${trade}`} onClick={onClose} className={SECONDARY}>{text.close}</button>
      </div>
    </section>
  );
}
