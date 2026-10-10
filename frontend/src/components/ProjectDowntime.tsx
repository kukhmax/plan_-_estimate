import { useCallback, useEffect, useRef, useState } from 'react';
import { abandonDowntime, fetchDowntimes, issueDowntimeNotice, issueDowntimeProtocol, openDowntime, updateDowntime } from '../api/downtimes';
import { fetchContractCatalog } from '../api/contractCatalog';
import { previewDowntimeNoticePdf, previewDowntimeProtocolPdf } from '../api/documents';
import { ApiError } from '../api/http';
import { fetchRepresentatives } from '../api/representatives';
import { useI18n } from '../hooks/useI18n';
import type { ContractCatalog } from '../types/contractCatalog';
import type { Downtime, DowntimeBlocker, DowntimeChange, DowntimePhoto } from '../types/downtime';
import type { ProjectRepresentative } from '../types/representative';
import { documentErrorText } from '../utils/documentErrors';
import { formatPrice } from '../utils/priceFormat';
import { CommitText, FIELD } from './CommitText';

interface ProjectDowntimeProps {
  projectId: string;
}

const BUTTON = 'min-h-11 px-3 text-sm font-semibold rounded-xl border transition disabled:opacity-60 break-words';
const SECONDARY = 'text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200';
const OPEN_STATUSES = ['DRAFT', 'NOTICED'];

function nowParts(): { day: string; time: string } {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return { day: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`, time: `${pad(now.getHours())}:${pad(now.getMinutes())}` };
}

/** The next Monday-to-Friday day after an ISO day: one tap adds the next day of the downtime without choosing a date. */
export function nextWorkingDay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  do {
    date.setUTCDate(date.getUTCDate() + 1);
  } while (date.getUTCDay() === 0 || date.getUTCDay() === 6);
  return date.toISOString().slice(0, 10);
}

/**
 * Stage 16I.4 — the notice and the protocol of downtime on the customer's side, on the phone. What the customer owes stops the work:
 * the owner picks the cause from the contract's list, ticks the rooms and the photos of the obstacle, says what he needs and until
 * when, and issues the **notice**. If the obstacle stays, the same card takes the **days**: one tap adds the next working day, each day
 * says whether other work could be done (such a day is not paid for); the sum for readiness is shown as the server derives it from the
 * contract, never typed. Every tap is saved at once (one request at a time, in order); the server answers with the whole episode and
 * what is still missing for the document that is next.
 */
export function ProjectDowntime({ projectId }: ProjectDowntimeProps) {
  const { t } = useI18n();
  const text = t.downtime;
  const causeText = t.contractCatalog.downtime_causes;
  const [episode, setEpisode] = useState<Downtime | null>(null);
  const [latest, setLatest] = useState<Downtime | null>(null);
  const [catalog, setCatalog] = useState<ContractCatalog | null>(null);
  const [people, setPeople] = useState<ProjectRepresentative[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [confirmFinish, setConfirmFinish] = useState(false);
  const [extra, setExtra] = useState('');
  const [pickedDay, setPickedDay] = useState('');
  const alive = useRef(true);
  const queue = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const list = await fetchDowntimes(projectId);
      if (!alive.current) return;
      setEpisode(list.items.find((e) => OPEN_STATUSES.includes(e.status)) ?? null);
      setLatest(list.items.find((e) => !OPEN_STATUSES.includes(e.status) && e.status !== 'ARCHIVED') ?? list.items.find((e) => e.status === 'ARCHIVED') ?? null);
    } catch {
      if (alive.current) setLoadFailed(true);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const reasonText = (err: unknown): string => {
    if (err instanceof ApiError && err.code === 'DOWNTIME_INVALID') {
      const reason = (err.detail as { details?: { reason?: string } } | null)?.details?.reason ?? '';
      return text.errors[reason as keyof typeof text.errors] ?? text.errors.UNKNOWN;
    }
    if (err instanceof ApiError && err.code === 'DOWNTIME_NOT_EDITABLE') return text.errors.NOT_EDITABLE;
    return text.errors.UNKNOWN;
  };

  /** One request at a time, in the order of the taps; the answer replaces the screen's copy of the episode. */
  const save = (changes: DowntimeChange, id?: string) => {
    const target = id ?? episode?.id;
    if (!target) return;
    queue.current = queue.current.then(async () => {
      if (!alive.current) return;
      setSaving((n) => n + 1);
      try {
        const next = await updateDowntime(projectId, target, changes);
        if (alive.current) {
          setEpisode(next);
          setError(null);
        }
      } catch (err) {
        if (alive.current) setError(reasonText(err));
      } finally {
        if (alive.current) setSaving((n) => n - 1);
      }
    });
  };

  const start = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const [opened, loadedCatalog, representatives] = await Promise.all([
        openDowntime(projectId),
        catalog ? Promise.resolve(catalog) : fetchContractCatalog(),
        fetchRepresentatives(projectId),
      ]);
      if (!alive.current) return;
      setCatalog(loadedCatalog);
      setPeople(representatives.items.filter((p) => !p.is_archived));
      setEpisode(opened);
      setOpen(true);
      const { day, time } = nowParts();  // the usual day and hour: now
      const defaults: DowntimeChange = {};
      if (opened.status === 'DRAFT') {
        if (!opened.noticed_on) defaults.noticed_on = day;
        if (!opened.noticed_time) defaults.noticed_time = time;
      } else {
        if (!opened.held_on) defaults.held_on = day;
        if (!opened.held_time) defaults.held_time = time;
      }
      if (Object.keys(defaults).length > 0) save(defaults, opened.id);
    } catch {
      if (alive.current) setError(text.load_failed);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const preview = async (which: 'notice' | 'protocol') => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await queue.current;
      await (which === 'notice' ? previewDowntimeNoticePdf(projectId) : previewDowntimeProtocolPdf(projectId));
      if (alive.current) setNote(which === 'notice' ? text.preview_notice_ok : text.preview_protocol_ok);
    } catch (err) {
      if (alive.current) setError(documentErrorText(t.documents.errors, err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const issue = async (which: 'notice' | 'protocol') => {
    if (!episode || busy || episode.blockers.length > 0) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await queue.current;
      await (which === 'notice' ? issueDowntimeNotice(projectId, episode.id) : issueDowntimeProtocol(projectId, episode.id));
      if (!alive.current) return;
      if (which === 'protocol') {
        setOpen(false);
        setEpisode(null);
      }
      setNote(which === 'notice' ? text.issue_notice_note : text.issue_protocol_note);
      await load();  // the notice moves the episode on to its protocol; the card stays open on it
    } catch (err) {
      if (!alive.current) return;
      const blockers = err instanceof ApiError && err.code === 'DOWNTIME_GATE_BLOCKED'
        ? (err.detail as { details?: { blockers?: DowntimeBlocker[] } } | null)?.details?.blockers
        : undefined;
      if (blockers && episode) setEpisode({ ...episode, blockers });
      else setError(err instanceof ApiError && err.code === 'DOWNTIME_NOT_EDITABLE' ? text.errors.NOT_EDITABLE : documentErrorText(t.documents.errors, err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const abandon = async () => {
    if (!episode || busy) return;
    if (!confirmFinish) {
      setConfirmFinish(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await queue.current;
      await abandonDowntime(projectId, episode.id);
      if (!alive.current) return;
      setEpisode(null);
      setOpen(false);
      setConfirmFinish(false);
      setNote(episode.status === 'DRAFT' ? text.abandoned : text.finished);
      await load();
    } catch {
      if (alive.current) setError(text.errors.UNKNOWN);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  // --- the notice -----------------------------------------------------------------------------------------------------------------
  const toggleRoom = (id: string) => {
    if (!episode) return;
    save({ room_ids: episode.room_ids.includes(id) ? episode.room_ids.filter((x) => x !== id) : [...episode.room_ids, id] });
  };
  const togglePhoto = (id: string) => {
    if (!episode) return;
    save({ photo_ids: episode.photo_ids.includes(id) ? episode.photo_ids.filter((x) => x !== id) : [...episode.photo_ids, id] });
  };
  const photoLabel = (photo: DowntimePhoto): string => {
    const taken = photo.captured_at ? photo.captured_at.replace('T', ' ').slice(0, 16) : null;
    return [photo.caption ?? text.photo_untitled, photo.room_name, taken].filter(Boolean).join(' · ');
  };

  // --- the protocol ---------------------------------------------------------------------------------------------------------------
  const presentIds = new Set((episode?.attendees ?? []).map((a) => a.person_id).filter((id): id is string => !!id));
  const strangers = (episode?.attendees ?? []).filter((a) => !a.person_id);
  const sendAttendees = (ids: string[], outsiders: Array<{ name: string; role: string | null }>) =>
    save({ attendees: [...ids.map((person_id) => ({ person_id })), ...outsiders.map((o) => ({ name: o.name, role: o.role }))] });
  const togglePerson = (id: string) => sendAttendees(presentIds.has(id) ? [...presentIds].filter((x) => x !== id) : [...presentIds, id], strangers);
  const addExtra = () => {
    const [name, ...role] = extra.split(',');
    if (!name.trim()) return;
    sendAttendees([...presentIds], [...strangers, { name: name.trim(), role: role.join(',').trim() || null }]);
    setExtra('');
  };
  const removeExtra = (index: number) => sendAttendees([...presentIds], strangers.filter((_, i) => i !== index));
  const addDay = (iso: string) => save({ days: { [iso]: {} } });
  const addNextDay = () => {
    if (!episode) return;
    const last = episode.days.length > 0 ? episode.days[episode.days.length - 1].date : episode.noticed_on;
    if (last) addDay(nextWorkingDay(last));
  };
  const money = (value: string | null) => (value === null ? '' : `${formatPrice(value)} zł`);

  const gate = (blockers: DowntimeBlocker[], issueKey: 'notice' | 'protocol') => (
    <>
      <section aria-label="downtime-gate" className="space-y-2 border-t border-slate-200 pt-3">
        <h4 className="text-sm font-semibold text-slate-900 break-words">{text.gate_title}</h4>
        {blockers.length === 0 ? (
          <p className="text-sm text-emerald-800 break-words">{text.gate_ready}</p>
        ) : (
          <div className="space-y-2">
            <p className="text-sm font-semibold text-red-700 break-words">{text.gate_blocked}</p>
            <ul className="space-y-2">
              {blockers.map((blocker) => (
                <li key={blocker.code} aria-label={`gate-${blocker.code}`} className="text-xs text-slate-800 break-words bg-red-50 border border-red-200 rounded-xl px-3 py-2">
                  {text.gate[blocker.code]}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
      {saving > 0 && <p role="status" aria-label="downtime-saving" className="text-xs text-slate-600">{text.saving}</p>}
      {error && <p role="alert" aria-label="downtime-error" className="text-sm text-red-700 break-words">{error}</p>}
      {note && <p role="status" aria-label="downtime-note" className="text-sm text-emerald-800 break-words">{note}</p>}
      <button type="button" aria-label={`preview-downtime-${issueKey}`} disabled={busy} onClick={() => void preview(issueKey)} className={`w-full ${BUTTON} ${SECONDARY}`}>
        {issueKey === 'notice' ? text.preview_notice : text.preview_protocol}
      </button>
      <button type="button" aria-label={`issue-downtime-${issueKey}`} disabled={busy || blockers.length > 0} onClick={() => void issue(issueKey)} className={`w-full ${BUTTON} text-white bg-sky-700 border-sky-700 hover:bg-sky-800`}>
        {issueKey === 'notice' ? text.issue_notice : text.issue_protocol}
      </button>
      <button type="button" aria-label="close-downtime-form" disabled={busy} onClick={() => { setOpen(false); setConfirmFinish(false); }} className={`w-full ${BUTTON} text-slate-800 bg-white border-slate-300 hover:bg-slate-100`}>{text.close}</button>
      <button type="button" aria-label="abandon-downtime" disabled={busy} onClick={() => void abandon()} className={`w-full ${BUTTON} text-red-800 bg-white border-red-300 hover:bg-red-50`}>
        {confirmFinish ? (issueKey === 'notice' ? text.abandon_confirm : text.finish_confirm) : issueKey === 'notice' ? text.abandon : text.finish_without}
      </button>
    </>
  );

  return (
    <article aria-label="project-downtime" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{text.title}</h3>
      <p className="text-xs text-slate-600 break-words">{text.intro}</p>

      {loading && <p role="status" className="text-sm text-slate-600">{text.loading}</p>}
      {loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-700 break-words">{text.load_failed}</p>
          <button type="button" onClick={() => void load()} className={`w-full ${BUTTON} text-slate-800 bg-slate-100 border-slate-200`}>{text.retry}</button>
        </div>
      )}

      {!loading && !loadFailed && !open && (
        <>
          {latest && <p className="text-sm text-slate-700 break-words">{text.latest.replace('{n}', String(latest.sequence)).replace('{status}', text.status[latest.status])}</p>}
          <button type="button" aria-label="start-downtime" disabled={busy} onClick={() => void start()} className={`w-full ${BUTTON} text-white bg-blue-600 border-blue-600 hover:bg-blue-700`}>
            {busy ? text.loading : episode ? text.continue : text.start}
          </button>
          <button type="button" aria-label="preview-downtime-notice" disabled={busy} onClick={() => void preview('notice')} className={`w-full ${BUTTON} ${SECONDARY}`}>{text.preview_notice}</button>
          <button type="button" aria-label="preview-downtime-protocol" disabled={busy} onClick={() => void preview('protocol')} className={`w-full ${BUTTON} ${SECONDARY}`}>{text.preview_protocol}</button>
        </>
      )}

      {open && episode && catalog && episode.status === 'DRAFT' && (
        <div aria-label="downtime-form" className="space-y-4">
          <h4 className="text-sm font-semibold text-slate-900">{text.notice_title}</h4>
          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900">{text.cause}</span>
            <select aria-label="downtime-cause" value={episode.cause_key ?? ''} onChange={(e) => save({ cause_key: e.target.value || null })} className={FIELD}>
              <option value="">{text.cause_none}</option>
              {catalog.downtime_causes.items.map((cause) => (
                <option key={cause.key} value={cause.key}>{causeText[cause.key as keyof typeof causeText] ?? cause.key}</option>
              ))}
            </select>
          </label>
          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900 break-words">{text.cause_note}</span>
            <CommitText label="downtime-cause-note" multiline value={episode.cause_note ?? ''} onCommit={(v) => save({ cause_note: v.trim() === '' ? null : v })} />
          </label>

          <fieldset className="space-y-1">
            <legend className="text-sm font-semibold text-slate-900">{text.rooms}</legend>
            <p className="text-xs text-slate-600 break-words">{text.rooms_hint}</p>
            {episode.rooms.map((room) => (
              <label key={room.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                <input type="checkbox" aria-label={`downtime-room-${room.id}`} className="h-5 w-5 shrink-0" checked={episode.room_ids.includes(room.id)} onChange={() => toggleRoom(room.id)} />
                <span className="min-w-0 break-words">{room.name}</span>
              </label>
            ))}
          </fieldset>

          <div className="grid grid-cols-1 gap-3">
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.noticed_on}</span>
              <input type="date" aria-label="downtime-noticed-on" value={episode.noticed_on ?? ''} onChange={(e) => save({ noticed_on: e.target.value || null })} className={FIELD} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.noticed_time}</span>
              <CommitText label="downtime-noticed-time" type="time" value={episode.noticed_time ?? ''} onCommit={(v) => save({ noticed_time: v || null })} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900 break-words">{text.channel}</span>
              <CommitText label="downtime-channel" value={episode.notice_channel ?? ''} onCommit={(v) => save({ notice_channel: v.trim() === '' ? null : v })} />
            </label>
          </div>

          <fieldset className="space-y-1">
            <legend className="text-sm font-semibold text-slate-900">{text.photos}</legend>
            <p className="text-xs text-slate-600 break-words">{text.photos_hint}</p>
            {episode.photo_options.length === 0 && <p className="text-xs text-amber-800 break-words">{text.photos_none}</p>}
            {episode.photo_options.map((photo) => (
              <label key={photo.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                <input type="checkbox" aria-label={`downtime-photo-${photo.id}`} className="h-5 w-5 shrink-0" checked={episode.photo_ids.includes(photo.id)} onChange={() => togglePhoto(photo.id)} />
                <span className="min-w-0 break-words">{photoLabel(photo)}</span>
              </label>
            ))}
          </fieldset>

          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900 break-words">{text.need}</span>
            <CommitText label="downtime-need" multiline value={episode.need_text ?? ''} onCommit={(v) => save({ need_text: v.trim() === '' ? null : v })} />
          </label>
          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900">{text.need_by}</span>
            <input type="date" aria-label="downtime-need-by" value={episode.need_by ?? ''} onChange={(e) => save({ need_by: e.target.value || null })} className={FIELD} />
          </label>
          {gate(episode.blockers, 'notice')}
        </div>
      )}

      {open && episode && catalog && episode.status === 'NOTICED' && (
        <div aria-label="downtime-form" className="space-y-4">
          <p aria-label="downtime-noticed-row" className="text-sm font-semibold text-slate-900 break-words">
            {text.noticed_row.replace('{number}', episode.notice_number ?? '').replace('{cause}', episode.cause_text ?? '')}
          </p>

          <section aria-label="downtime-days" className="space-y-2">
            <h4 className="text-sm font-semibold text-slate-900">{text.days}</h4>
            <p className="text-xs text-slate-600 break-words">{text.days_hint}</p>
            {episode.days.length === 0 && <p className="text-xs text-slate-600 break-words">{text.days_none}</p>}
            {episode.days.map((day) => (
              <div key={day.date} aria-label={`downtime-day-${day.date}`} className="border border-slate-200 rounded-xl p-3 space-y-2">
                <p className="text-sm font-semibold text-slate-900 break-words">{text.day_row.replace('{date}', day.date).replace('{weekday}', text.weekdays[day.weekday])}</p>
                <label className="flex items-start gap-3 min-h-11 text-sm text-slate-900">
                  <input type="checkbox" aria-label={`downtime-other-work-${day.date}`} className="mt-1 h-5 w-5 shrink-0" checked={day.other_work} onChange={() => save({ days: { [day.date]: { other_work: !day.other_work } } })} />
                  <span className="min-w-0 break-words">{text.other_work}</span>
                </label>
                <label className="block space-y-1">
                  <span className="block text-sm font-medium text-slate-900">{text.day_note}</span>
                  <CommitText label={`downtime-day-note-${day.date}`} value={day.note ?? ''} onCommit={(v) => save({ days: { [day.date]: { note: v.trim() === '' ? null : v } } })} />
                </label>
                <button type="button" aria-label={`downtime-day-remove-${day.date}`} onClick={() => save({ days: { [day.date]: null } })} className={`w-full ${BUTTON} text-red-800 bg-white border-red-300 hover:bg-red-50`}>{text.day_remove}</button>
              </div>
            ))}
            <button type="button" aria-label="downtime-add-next-day" disabled={!episode.noticed_on} onClick={addNextDay} className={`w-full ${BUTTON} text-white bg-blue-600 border-blue-600 hover:bg-blue-700`}>{text.add_next}</button>
            <label className="block space-y-1">
              <span className="block text-xs text-slate-700 break-words">{text.add_date}</span>
              <input type="date" aria-label="downtime-pick-day" value={pickedDay} onChange={(e) => setPickedDay(e.target.value)} className={FIELD} />
            </label>
            <button type="button" aria-label="downtime-add-picked-day" disabled={!pickedDay} onClick={() => { addDay(pickedDay); setPickedDay(''); }} className={`w-full ${BUTTON} ${SECONDARY}`}>{text.add_date_button}</button>
          </section>

          {episode.days.length > 0 && (
            <section aria-label="downtime-settlement" className="space-y-1 bg-slate-50 border border-slate-200 rounded-xl p-3">
              <h4 className="text-sm font-semibold text-slate-900">{text.settlement}</h4>
              <p className="text-sm text-slate-800 break-words">{text.settlement_days.replace('{listed}', String(episode.settlement.listed)).replace('{chargeable}', String(episode.settlement.chargeable))}</p>
              {episode.settlement.rate === null ? (
                <p className="text-xs text-amber-800 break-words">{text.no_rate}</p>
              ) : (
                <>
                  <p className="text-sm text-slate-800 break-words">{text.rate.replace('{rate}', money(episode.settlement.rate))}</p>
                  <p className="text-base font-semibold text-slate-900 break-words">{text.amount.replace('{amount}', money(episode.settlement.payable))}</p>
                </>
              )}
              {episode.settlement.capped && <p className="text-xs text-amber-800 break-words">{text.capped.replace('{cap}', money(episode.settlement.cap))}</p>}
              {episode.settlement.limit_exceeded && <p className="text-xs font-semibold text-red-700 break-words">{text.limit_exceeded.replace('{n}', String(episode.settlement.limit_days))}</p>}
            </section>
          )}

          <div className="grid grid-cols-1 gap-3">
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_on}</span>
              <input type="date" aria-label="downtime-held-on" value={episode.held_on ?? ''} onChange={(e) => save({ held_on: e.target.value || null })} className={FIELD} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_time}</span>
              <CommitText label="downtime-held-time" type="time" value={episode.held_time ?? ''} onCommit={(v) => save({ held_time: v || null })} />
            </label>
          </div>

          <fieldset className="space-y-1">
            <legend className="text-sm font-semibold text-slate-900">{text.attendees}</legend>
            {people.length === 0 && <p className="text-xs text-slate-600 break-words">{text.attendees_none}</p>}
            {people.map((person) => (
              <label key={person.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                <input type="checkbox" aria-label={`downtime-person-${person.id}`} className="h-5 w-5 shrink-0" checked={presentIds.has(person.id)} onChange={() => togglePerson(person.id)} />
                <span className="min-w-0 break-words">{person.name}{person.role_title ? ` · ${person.role_title}` : ''}</span>
              </label>
            ))}
            {strangers.map((a, index) => (
              <div key={`${a.name}-${index}`} className="flex items-center justify-between gap-3 min-h-11 text-sm text-slate-900">
                <span className="min-w-0 break-words">{a.name}{a.role ? ` · ${a.role}` : ''}</span>
                <button type="button" aria-label={`downtime-extra-remove-${index}`} onClick={() => removeExtra(index)} className={`shrink-0 ${BUTTON} text-red-800 bg-white border-red-300`}>{text.extra_remove}</button>
              </div>
            ))}
            <label className="block space-y-1 pt-1">
              <span className="block text-xs text-slate-700 break-words">{text.extra_label}</span>
              <input aria-label="downtime-extra" value={extra} onChange={(e) => setExtra(e.target.value)} className={FIELD} />
            </label>
            <button type="button" aria-label="downtime-extra-add" disabled={!extra.trim()} onClick={addExtra} className={`w-full ${BUTTON} ${SECONDARY}`}>{text.extra_add}</button>
          </fieldset>

          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900 break-words">{text.deadline_note}</span>
            <CommitText label="downtime-deadline-note" multiline value={episode.deadline_note ?? ''} onCommit={(v) => save({ deadline_note: v.trim() === '' ? null : v })} />
          </label>
          <label className="flex items-start gap-3 min-h-11 text-sm text-slate-900">
            <input type="checkbox" aria-label="downtime-refused" className="mt-1 h-5 w-5 shrink-0" checked={episode.signature_refused} onChange={() => save({ signature_refused: !episode.signature_refused })} />
            <span className="min-w-0">
              <span className="block break-words">{text.refusal}</span>
              {episode.signature_refused && <span className="block text-xs text-amber-800 break-words">{text.refusal_hint}</span>}
            </span>
          </label>
          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900">{text.notes}</span>
            <CommitText label="downtime-notes" multiline value={episode.notes ?? ''} onCommit={(v) => save({ notes: v.trim() === '' ? null : v })} />
          </label>
          {gate(episode.blockers, 'protocol')}
        </div>
      )}

      {!open && error && <p role="alert" aria-label="downtime-error" className="text-sm text-red-700 break-words">{error}</p>}
      {!open && note && <p role="status" aria-label="downtime-note" className="text-sm text-emerald-800 break-words">{note}</p>}
    </article>
  );
}
