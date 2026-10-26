import { FormEvent, ReactNode, useCallback, useEffect, useState } from 'react';
import { ApiError } from '../api/http';
import { fetchTradePage, saveTradeRoom, submitTradeAnswers } from '../api/tradePortal';
import { useI18n } from '../hooks/useI18n';
import { TRADE_LINK_LIMITS, type PortalTradePage, type PortalTradeRoom, type PositionUnit, type RoomWrite } from '../types/tradeLink';
import { formatQuantity } from '../utils/format';
import { isLocale, LOCALES, LOCALE_NAMES, type Locale } from '../utils/locale';
import { formatNoteTime } from '../utils/noteFormat';

/** Where the open page of the electrician and the plumber lives: `/m` (the secret is in the fragment). */
export function isMasterPagePath(pathname: string): boolean {
  return pathname === '/m' || pathname === '/m/';
}

type Failure = 'not_found' | 'inactive' | 'limited' | 'error';

const CARD = 'pe-card rounded-2xl p-4 shadow-sm space-y-3';
const FIELD = 'w-full border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 pe-surface min-h-12';
const PRIMARY = 'w-full min-h-12 px-4 py-2 text-base bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50';
const SECONDARY = 'w-full min-h-12 px-4 py-2 text-base rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium hover:bg-slate-50 disabled:opacity-50';

function failureOf(err: unknown): Failure {
  if (err instanceof ApiError) {
    if (err.status === 404) return 'not_found';
    if (err.status === 410) return 'inactive';
    if (err.status === 429) return 'limited';
  }
  return 'error';
}

interface OwnDraft {
  id: number;
  name: string;
  quantity: string;
  unit: PositionUnit;
  note: string;
}

interface RoomDraft {
  typical: Record<string, { quantity: string; note: string }>;
  own: OwnDraft[];
  dirty: boolean;
}

/** "2.00" -> "2", "12.50" -> "12.5": what the craftsman sees in the field is what he would type. */
function plain(value: string | null): string {
  if (value === null) return '';
  return value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
}

let ownSeq = 0;

function draftOf(room: PortalTradeRoom): RoomDraft {
  const typical: RoomDraft['typical'] = {};
  for (const row of room.typical) typical[row.key] = { quantity: plain(row.quantity), note: row.note ?? '' };
  const own = room.own.map((row) => ({ id: ++ownSeq, name: row.name, quantity: plain(row.quantity), unit: row.unit, note: row.note ?? '' }));
  return { typical, own, dirty: false };
}

function writeOf(draft: RoomDraft, keys: string[]): RoomWrite {
  const typical = keys.flatMap((key) => {
    const row = draft.typical[key];
    if (!row || (row.quantity.trim() === '' && row.note.trim() === '')) return [];
    return [{ key, quantity: row.quantity.trim() === '' ? null : row.quantity.trim(), note: row.note.trim() === '' ? null : row.note.trim() }];
  });
  const own = draft.own
    .filter((row) => row.name.trim() !== '' || row.quantity.trim() !== '')
    .map((row) => ({ name: row.name.trim(), quantity: row.quantity.trim() === '' ? null : row.quantity.trim(), unit: row.unit, note: row.note.trim() === '' ? null : row.note.trim() }));
  return { typical, own };
}

function filledCount(draft: RoomDraft): number {
  return Object.values(draft.typical).filter((row) => row.quantity.trim() !== '' || row.note.trim() !== '').length + draft.own.length;
}

/**
 * The open page of the electrician or the plumber (V2-14): the rooms with their sizes, the checklist of the typical positions, the craftsman's own
 * positions, and the button that sends it to the owner. No login, nothing is kept in the browser; the language is the one the owner chose and the
 * craftsman may change it. There are no prices, no client and no address here.
 */
export function MasterPage({ token }: { token: string }) {
  const { t, locale, setLocale } = useI18n();
  const text = t.master_page;
  const [page, setPage] = useState<PortalTradePage | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [drafts, setDrafts] = useState<Record<string, RoomDraft>>({});
  const [busy, setBusy] = useState(false);
  const [roomError, setRoomError] = useState<{ roomId: string; text: string } | null>(null);
  const [roomSaved, setRoomSaved] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    document.title = 'Plan & Estimate';
    const meta = [
      ['robots', 'noindex, nofollow'],
      ['referrer', 'no-referrer'],
    ] as const;
    const added = meta.map(([key, content]) => {
      const el = document.createElement('meta');
      el.name = key;
      el.content = content;
      document.head.appendChild(el);
      return el;
    });
    return () => added.forEach((el) => el.remove());
  }, []);

  /** A page that arrives refreshes the rooms the craftsman has not touched; a room with unsaved typing is kept as it is. */
  const take = useCallback((loaded: PortalTradePage, keep: boolean) => {
    setPage(loaded);
    setDrafts((current) => {
      const next: Record<string, RoomDraft> = {};
      for (const room of loaded.rooms) next[room.id] = keep && current[room.id]?.dirty ? current[room.id] : draftOf(room);
      return next;
    });
  }, []);

  const load = useCallback(
    async (lang: Locale | null, first = false) => {
      if (token === '') {
        setFailure('not_found');
        return;
      }
      try {
        const loaded = await fetchTradePage(token, lang);
        take(loaded, !first);
        setFailure(null);
        if (first && isLocale(loaded.lang)) setLocale(loaded.lang);
      } catch (err) {
        setFailure(failureOf(err));
      }
    },
    [token, setLocale, take],
  );

  useEffect(() => {
    void load(null, true);
  }, [load]);

  const changeLanguage = (next: Locale) => {
    setLocale(next);
    void load(next);
  };

  const codeText = (err: unknown): string => {
    const code = err instanceof ApiError ? (err.status === 0 ? 'NETWORK' : err.code) : undefined;
    const table = text.errors as Record<string, string>;
    return (code && table[code]) || table.GENERIC;
  };

  const edit = (roomId: string, change: (draft: RoomDraft) => RoomDraft) => {
    setSubmitted(false);
    setRoomSaved(null);
    setDrafts((current) => ({ ...current, [roomId]: { ...change(current[roomId]), dirty: true } }));
  };

  const keysOf = (loaded: PortalTradePage) => loaded.positions.map((p) => p.key);

  const saveRoom = async (roomId: string): Promise<boolean> => {
    if (!page) return false;
    setRoomError(null);
    try {
      const saved = await saveTradeRoom(token, roomId, locale, writeOf(drafts[roomId], keysOf(page)));
      setPage(saved);
      setDrafts((current) => {
        const next = { ...current };
        const room = saved.rooms.find((r) => r.id === roomId);
        if (room) next[roomId] = draftOf(room);
        return next;
      });
      return true;
    } catch (err) {
      setRoomError({ roomId, text: codeText(err) });
      if (err instanceof ApiError && (err.status === 404 || err.status === 410)) setFailure(failureOf(err));
      return false;
    }
  };

  const onSaveRoom = async (roomId: string) => {
    if (busy) return;
    setBusy(true);
    setSubmitError(null);
    const ok = await saveRoom(roomId);
    if (ok) setRoomSaved(roomId);
    setBusy(false);
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (busy || !page) return;
    setBusy(true);
    setSubmitError(null);
    setRoomSaved(null);
    try {
      for (const room of page.rooms) {
        if (drafts[room.id]?.dirty && !(await saveRoom(room.id))) {
          setSubmitError(text.fix_room_first);
          return;
        }
      }
      take(await submitTradeAnswers(token, locale, name), true);
      setSubmitted(true);
    } catch (err) {
      setSubmitError(codeText(err));
      if (err instanceof ApiError && (err.status === 404 || err.status === 410)) setFailure(failureOf(err));
    } finally {
      setBusy(false);
    }
  };

  const date = (iso: string) => formatNoteTime(iso, locale);

  const header = (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm font-semibold text-slate-700">Plan &amp; Estimate</span>
      <label className="text-xs text-slate-600 flex items-center gap-2">
        <span className="sr-only">{text.language}</span>
        <select
          aria-label="master-language"
          value={locale}
          onChange={(e) => changeLanguage(e.target.value as Locale)}
          className="border border-slate-200 rounded-xl px-2 min-h-11 text-sm pe-surface text-slate-900"
        >
          {LOCALES.map((code) => (
            <option key={code} value={code}>{LOCALE_NAMES[code]}</option>
          ))}
        </select>
      </label>
    </div>
  );

  const shell = (children: ReactNode) => (
    <main className="min-h-screen w-full max-w-xl mx-auto px-4 py-4 space-y-3 overflow-x-hidden" aria-label="master-page">
      {header}
      {children}
    </main>
  );

  if (failure !== null && (page === null || failure === 'inactive' || failure === 'not_found')) {
    const key = { not_found: 'not_found', inactive: 'inactive', limited: 'limited', error: 'error' }[failure];
    return shell(
      <div aria-label={`master-${failure}`} className={CARD}>
        <h1 className="text-lg font-semibold text-slate-900 break-words">{text[`${key}_title` as 'not_found_title']}</h1>
        <p className="text-sm text-slate-600 break-words">{text[`${key}_text` as 'not_found_text']}</p>
        {failure === 'error' && (
          <button type="button" aria-label="master-retry" onClick={() => void load(null, true)} className={PRIMARY}>{text.retry}</button>
        )}
      </div>,
    );
  }

  if (page === null) {
    return shell(<p aria-label="master-loading" className="text-sm text-slate-500 text-center py-6">{text.loading}</p>);
  }

  const { contractor, rooms, positions } = page;
  const unitLabel = (unit: PositionUnit) => (unit === 'PCS' ? text.unit_PCS : text.unit_LM);
  const positionName = (key: string) => (text.positions as Record<string, string>)[key] ?? key;
  const length = (value: string | null) => (value === null ? null : formatQuantity(value, 'LM'));

  const sizeLine = (room: PortalTradeRoom): string => {
    const parts: string[] = [];
    const dims = [length(room.length), length(room.width), length(room.height)];
    if (dims[0] && dims[1]) parts.push(`${dims[0]} × ${dims[1]} m${dims[2] ? ` × h ${dims[2]} m` : ''}`);
    else if (dims[2]) parts.push(`h ${dims[2]} m`);
    if (room.floor_area) parts.push(`${text.size_floor} ${formatQuantity(room.floor_area, 'M2')} m²`);
    if (room.perimeter) parts.push(`${text.size_perimeter} ${formatQuantity(room.perimeter, 'LM')} m`);
    return parts.join(' · ');
  };

  const total = rooms.reduce((sum, room) => sum + filledCount(drafts[room.id] ?? draftOf(room)), 0);

  return shell(
    <>
      <section aria-label="master-contractor" className={CARD}>
        <h1 className="text-lg font-semibold text-slate-900 break-words">{text.trade_title[page.trade]}</h1>
        <p className="text-sm text-slate-900 break-words">
          <span className="text-xs font-semibold uppercase text-slate-500">{text.object}</span>
          <br />
          {page.project_name}
        </p>
        <p className="text-sm text-slate-900 break-words">
          <span className="text-xs font-semibold uppercase text-slate-500">{text.contractor}</span>
          <br />
          {contractor.name ?? '—'}
        </p>
        {contractor.phone && (
          <a aria-label="master-call" href={`tel:${contractor.phone}`} className={`${SECONDARY} flex items-center justify-center text-center`}>
            {text.call}: {contractor.phone}
          </a>
        )}
        {page.owner_note && (
          <div aria-label="master-owner-note" className="rounded-xl bg-amber-50 border border-amber-200 p-3 space-y-1">
            <p className="text-xs font-semibold uppercase text-amber-800">{text.owner_note}</p>
            <p className="text-sm text-amber-900 whitespace-pre-wrap break-words">{page.owner_note}</p>
          </div>
        )}
        <p className="text-sm text-slate-600 break-words">{text.intro}</p>
      </section>

      {rooms.length === 0 && <p aria-label="master-no-rooms" className="text-sm text-slate-600 text-center py-4 break-words">{text.no_rooms}</p>}

      {rooms.map((room) => {
        const draft = drafts[room.id] ?? draftOf(room);
        const size = sizeLine(room);
        const filled = filledCount(draft);
        return (
          <section key={room.id} aria-label={`master-room-${room.id}`} className={CARD}>
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-slate-900 break-words">{room.name}</h2>
              {size && <p className="text-xs text-slate-500 break-words">{size}</p>}
              <p className="text-xs text-slate-500">{text.room_filled.replace('{count}', String(filled))}</p>
            </div>

            <ul className="space-y-3">
              {positions.map((position) => {
                const row = draft.typical[position.key] ?? { quantity: '', note: '' };
                const noteOpen = row.note !== '';
                return (
                  <li key={position.key} aria-label={`master-${room.id}-${position.key}`} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="flex-1 min-w-0 text-sm font-medium text-slate-800 break-words">{positionName(position.key)}</span>
                      <input
                        aria-label={`master-qty-${room.id}-${position.key}`}
                        inputMode={position.unit === 'PCS' ? 'numeric' : 'decimal'}
                        autoComplete="off"
                        placeholder="—"
                        value={row.quantity}
                        maxLength={8}
                        onChange={(e) =>
                          edit(room.id, (d) => ({
                            ...d,
                            typical: { ...d.typical, [position.key]: { ...row, quantity: position.unit === 'PCS' ? e.target.value.replace(/\D/g, '') : e.target.value.replace(/[^\d.,]/g, '') } },
                          }))
                        }
                        className="w-20 shrink-0 border border-slate-200 rounded-xl px-3 py-2 text-base text-right text-slate-900 pe-surface min-h-12"
                      />
                      <span className="w-8 shrink-0 text-xs text-slate-500">{unitLabel(position.unit)}</span>
                    </div>
                    {noteOpen ? (
                      <input
                        aria-label={`master-note-${room.id}-${position.key}`}
                        value={row.note}
                        maxLength={TRADE_LINK_LIMITS.note}
                        placeholder={text.note_placeholder}
                        onChange={(e) => edit(room.id, (d) => ({ ...d, typical: { ...d.typical, [position.key]: { ...row, note: e.target.value } } }))}
                        className={FIELD}
                      />
                    ) : (
                      <button
                        type="button"
                        aria-label={`master-note-add-${room.id}-${position.key}`}
                        onClick={() => edit(room.id, (d) => ({ ...d, typical: { ...d.typical, [position.key]: { ...row, note: ' ' } } }))}
                        className="text-xs text-blue-700 min-h-11 px-1"
                      >
                        {text.note_add}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>

            <div className="space-y-3 border-t border-slate-200 pt-3">
              <h3 className="text-sm font-semibold text-slate-700 break-words">{text.own_title}</h3>
              {draft.own.map((row, index) => (
                <div key={row.id} aria-label={`master-own-${room.id}-${index}`} className="rounded-xl border border-slate-200 p-3 space-y-2">
                  <input
                    aria-label={`master-own-name-${room.id}-${index}`}
                    value={row.name}
                    maxLength={TRADE_LINK_LIMITS.name}
                    placeholder={text.own_name_placeholder}
                    onChange={(e) => edit(room.id, (d) => ({ ...d, own: d.own.map((o) => (o.id === row.id ? { ...o, name: e.target.value } : o)) }))}
                    className={FIELD}
                  />
                  <div className="flex items-center gap-2">
                    <input
                      aria-label={`master-own-qty-${room.id}-${index}`}
                      inputMode="decimal"
                      autoComplete="off"
                      placeholder="—"
                      value={row.quantity}
                      maxLength={8}
                      onChange={(e) => edit(room.id, (d) => ({ ...d, own: d.own.map((o) => (o.id === row.id ? { ...o, quantity: e.target.value.replace(/[^\d.,]/g, '') } : o)) }))}
                      className="w-20 shrink-0 border border-slate-200 rounded-xl px-3 py-2 text-base text-right text-slate-900 pe-surface min-h-12"
                    />
                    <select
                      aria-label={`master-own-unit-${room.id}-${index}`}
                      value={row.unit}
                      onChange={(e) => edit(room.id, (d) => ({ ...d, own: d.own.map((o) => (o.id === row.id ? { ...o, unit: e.target.value as PositionUnit } : o)) }))}
                      className="flex-1 min-w-0 border border-slate-200 rounded-xl px-2 min-h-12 text-base pe-surface text-slate-900"
                    >
                      <option value="PCS">{text.unit_PCS}</option>
                      <option value="LM">{text.unit_LM}</option>
                    </select>
                    <button
                      type="button"
                      aria-label={`master-own-remove-${room.id}-${index}`}
                      onClick={() => edit(room.id, (d) => ({ ...d, own: d.own.filter((o) => o.id !== row.id) }))}
                      className="shrink-0 min-h-12 min-w-12 rounded-xl border border-slate-200 pe-surface text-slate-700"
                    >
                      <span aria-hidden="true">✕</span>
                      <span className="sr-only">{text.own_remove}</span>
                    </button>
                  </div>
                  <input
                    aria-label={`master-own-note-${room.id}-${index}`}
                    value={row.note}
                    maxLength={TRADE_LINK_LIMITS.note}
                    placeholder={text.note_placeholder}
                    onChange={(e) => edit(room.id, (d) => ({ ...d, own: d.own.map((o) => (o.id === row.id ? { ...o, note: e.target.value } : o)) }))}
                    className={FIELD}
                  />
                </div>
              ))}
              {draft.own.length < TRADE_LINK_LIMITS.own_per_room && (
                <button
                  type="button"
                  aria-label={`master-own-add-${room.id}`}
                  onClick={() => edit(room.id, (d) => ({ ...d, own: [...d.own, { id: ++ownSeq, name: '', quantity: '', unit: 'PCS', note: '' }] }))}
                  className={SECONDARY}
                >
                  ➕ {text.own_add}
                </button>
              )}
            </div>

            <button type="button" aria-label={`master-room-save-${room.id}`} disabled={busy || !draft.dirty} onClick={() => void onSaveRoom(room.id)} className={PRIMARY}>
              {text.room_save}
            </button>
            {draft.dirty && <p className="text-xs text-amber-700 break-words">{text.room_unsaved}</p>}
            {roomSaved === room.id && !draft.dirty && <p role="status" className="text-sm text-emerald-700 break-words">{text.room_saved}</p>}
            {roomError?.roomId === room.id && <p role="alert" className="text-sm text-red-600 break-words">{roomError.text}</p>}
          </section>
        );
      })}

      {rooms.length > 0 && (
        <form aria-label="master-submit-form" onSubmit={(e) => void onSubmit(e)} className={CARD}>
          <h2 className="text-base font-semibold text-slate-900 break-words">{text.submit_title}</h2>
          <p className="text-xs text-slate-500 break-words">{text.submit_hint.replace('{count}', String(total))}</p>
          <label className="block text-sm font-medium text-slate-700">
            {text.master_name_label}
            <input
              aria-label="master-name"
              autoComplete="name"
              value={name}
              maxLength={TRADE_LINK_LIMITS.master_name}
              placeholder={text.master_name_placeholder}
              onChange={(e) => setName(e.target.value)}
              className={`${FIELD} mt-1`}
            />
          </label>
          <button type="submit" aria-label="master-submit" disabled={busy || name.trim() === '' || total === 0} className={PRIMARY}>
            {text.submit_button}
          </button>
          {submitError && <p role="alert" className="text-sm text-red-600 break-words">{submitError}</p>}
          {submitted && <p role="status" aria-label="master-submitted" className="text-sm text-emerald-700 break-words">{text.submit_done}</p>}
          {page.last_submitted_at && !submitted && (
            <p aria-label="master-last-sent" className="text-xs text-slate-500 break-words">{text.last_sent.replace('{date}', date(page.last_submitted_at))}</p>
          )}
        </form>
      )}
    </>,
  );
}
