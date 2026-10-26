import { useCallback, useEffect, useRef, useState } from 'react';
import { previewPressureTestPdf } from '../api/documents';
import { ApiError } from '../api/http';
import { abandonPressureDraft, fetchPressureTests, issuePressure, openPressureDraft, updatePressure } from '../api/pressureTests';
import { fetchRepresentatives } from '../api/representatives';
import { useI18n } from '../hooks/useI18n';
import type { Pressure, PressureBlocker, PressureChange } from '../types/pressure';
import { MAX_PRESSURE_PHOTOS, PRESSURE_MEDIA, PRESSURE_RESULTS, PRESSURE_SYSTEMS } from '../types/pressure';
import type { ProjectRepresentative } from '../types/representative';
import { documentErrorText } from '../utils/documentErrors';
import { CommitText, FIELD } from './CommitText';
import { Ico } from './Ico';

interface ProjectPressureTestsProps {
  projectId: string;
}

const BUTTON = 'min-h-11 px-3 text-sm font-semibold rounded-xl border transition disabled:opacity-60 break-words';
const CHOICE = BUTTON.replace('px-3', 'px-2'); // two columns at 320 px: the long Russian name of a system must still fit on one line
const OFF = 'pe-surface text-slate-900 border-slate-300 hover:bg-slate-50';
const ON = 'bg-slate-900 text-white border-slate-900';

function nowParts(): { day: string; time: string } {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return { day: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`, time: `${pad(now.getHours())}:${pad(now.getMinutes())}` };
}

/** A pressure as the field shows it: "6.50" -> "6,5". */
function barField(value: string | null): string {
  if (value === null) return '';
  const [whole, fraction = ''] = value.split('.');
  const trimmed = fraction.replace(/0+$/, '');
  return trimmed === '' ? whole : `${whole},${trimmed}`;
}

/**
 * V2-12b — the protocol of a pressure test, on the phone. The owner stands at the pipes: chooses the system and the medium, types the test pressure, the time held and the drop, ticks the
 * photos of the manometer, taps the result. Every change is saved at once (one request at a time, in order); the server answers with the whole protocol and what is still missing. The result
 * is the owner's word: nothing here judges a number. When the customer did not come, one switch turns it into a one-sided protocol that asks for the day he was notified.
 */
export function ProjectPressureTests({ projectId }: ProjectPressureTestsProps) {
  const { t } = useI18n();
  const text = t.pressure;
  const [draft, setDraft] = useState<Pressure | null>(null);
  const [latest, setLatest] = useState<Pressure | null>(null);
  const [people, setPeople] = useState<ProjectRepresentative[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [extra, setExtra] = useState('');
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
      const list = await fetchPressureTests(projectId);
      if (!alive.current) return;
      setDraft(list.items.find((p) => p.status === 'DRAFT') ?? null);
      setLatest(list.items.find((p) => p.status === 'ISSUED') ?? null);
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
    if (err instanceof ApiError && err.code === 'PRESSURE_INVALID') {
      const reason = (err.detail as { details?: { reason?: string } } | null)?.details?.reason ?? '';
      return text.errors[reason as keyof typeof text.errors] ?? text.errors.UNKNOWN;
    }
    if (err instanceof ApiError && err.code === 'PRESSURE_NOT_EDITABLE') return text.errors.NOT_EDITABLE;
    return text.errors.UNKNOWN;
  };

  /** One request at a time, in the order of the taps; the answer replaces the screen's copy of the protocol. */
  const save = (changes: PressureChange, id?: string) => {
    const target = id ?? draft?.id;
    if (!target) return;
    queue.current = queue.current.then(async () => {
      if (!alive.current) return;
      setSaving((n) => n + 1);
      try {
        const next = await updatePressure(projectId, target, changes);
        if (alive.current) {
          setDraft(next);
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
      const [protocol, representatives] = await Promise.all([openPressureDraft(projectId), fetchRepresentatives(projectId)]);
      if (!alive.current) return;
      setPeople(representatives.items.filter((p) => !p.is_archived));
      setDraft(protocol);
      setOpen(true);
      const { day, time } = nowParts(); // the usual day and hour: now
      const defaults: PressureChange = {};
      if (!protocol.held_on) defaults.held_on = day;
      if (!protocol.held_time) defaults.held_time = time;
      if (Object.keys(defaults).length > 0) save(defaults, protocol.id);
    } catch {
      if (alive.current) setError(text.load_failed);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const preview = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await queue.current;
      await previewPressureTestPdf(projectId);
      if (alive.current) setNote(text.preview_ok);
    } catch (err) {
      if (alive.current) setError(documentErrorText(t.documents.errors, err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const issue = async () => {
    if (!draft || busy || draft.blockers.length > 0) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await queue.current;
      await issuePressure(projectId, draft.id);
      if (!alive.current) return;
      setOpen(false);
      setDraft(null);
      setNote(text.issue_note);
      await load();
    } catch (err) {
      if (!alive.current) return;
      const blockers = err instanceof ApiError && err.code === 'PRESSURE_GATE_BLOCKED'
        ? (err.detail as { details?: { blockers?: PressureBlocker[] } } | null)?.details?.blockers
        : undefined;
      if (blockers && draft) setDraft({ ...draft, blockers });
      else setError(err instanceof ApiError && err.code === 'PRESSURE_NOT_EDITABLE' ? text.errors.NOT_EDITABLE : documentErrorText(t.documents.errors, err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const abandon = async () => {
    if (!draft || busy) return;
    if (!confirmAbandon) {
      setConfirmAbandon(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await queue.current;
      await abandonPressureDraft(projectId, draft.id);
      if (!alive.current) return;
      setDraft(null);
      setOpen(false);
      setConfirmAbandon(false);
      setNote(text.abandoned);
    } catch {
      if (alive.current) setError(text.errors.UNKNOWN);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  // --- the people present --------------------------------------------------------------------------------------------------------
  const presentIds = new Set((draft?.attendees ?? []).map((a) => a.person_id).filter((id): id is string => !!id));
  const strangers = (draft?.attendees ?? []).filter((a) => !a.person_id);
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

  const togglePhoto = (id: string) => {
    if (!draft) return;
    save({ photo_ids: draft.photo_ids.includes(id) ? draft.photo_ids.filter((x) => x !== id) : [...draft.photo_ids, id] });
  };

  const photoLabel = (caption: string | null, place: string | null, takenAt: string | null): string => {
    const taken = takenAt ? takenAt.replace('T', ' ').slice(0, 16) : null;
    return [caption ?? text.photo_untitled, place, taken].filter(Boolean).join(' · ');
  };

  /** The duration is a whole number of minutes: anything else is refused here, with the sentence, before it is sent. */
  const commitDuration = (value: string) => {
    const trimmed = value.trim();
    if (trimmed === '') return save({ duration_min: null });
    if (!/^\d+$/.test(trimmed)) return setError(text.errors.WRONG_TYPE);
    const minutes = Number(trimmed);
    if (minutes < 1 || minutes > 1440) return setError(text.errors.OUT_OF_RANGE);
    return save({ duration_min: minutes });
  };
  const commitBar = (field: 'test_pressure_bar' | 'pressure_drop_bar', value: string) => save({ [field]: value.trim() === '' ? null : value.trim() });

  const atLimit = (draft?.photo_ids.length ?? 0) >= MAX_PRESSURE_PHOTOS;

  return (
    <article aria-label="project-pressure" className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{text.title}</h3>
      <p className="text-xs text-slate-600 break-words">{text.intro}</p>

      {loading && <p role="status" className="text-sm text-slate-600">{text.loading}</p>}
      {loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-700 break-words">{text.load_failed}</p>
          <button type="button" onClick={() => void load()} className={`w-full ${BUTTON} text-slate-800 bg-slate-100 border-slate-200`}><Ico>🔄</Ico>{text.retry}</button>
        </div>
      )}

      {!loading && !loadFailed && !open && (
        <>
          {latest && <p className="text-sm text-slate-700 break-words">{text.latest.replace('{n}', String(latest.sequence)).replace('{status}', text.status[latest.status])}</p>}
          <button type="button" aria-label="start-pressure" disabled={busy} onClick={() => void start()} className={`w-full ${BUTTON} text-white bg-blue-600 border-blue-600 hover:bg-blue-700`}>
            {busy ? text.loading : draft ? text.continue : latest ? text.new : text.start}
          </button>
          <button type="button" aria-label="preview-pressure" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}><Ico>👁️</Ico>{text.preview}</button>
        </>
      )}

      {open && draft && (
        <div aria-label="pressure-form" className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-900">{text.system_label}</p>
            <div className="grid grid-cols-2 gap-2">
              {PRESSURE_SYSTEMS.map((system) => (
                <button key={system} type="button" aria-label={`pressure-system-${system}`} aria-pressed={draft.system === system} onClick={() => save({ system })} className={`${CHOICE} ${draft.system === system ? ON : OFF}`}>
                  {text.systems[system]}
                </button>
              ))}
            </div>
          </div>
          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900 break-words">{text.section}</span>
            <CommitText label="pressure-section" value={draft.section ?? ''} onCommit={(v) => save({ section: v.trim() === '' ? null : v })} />
            <span className="block text-xs text-slate-600 break-words">{text.section_hint}</span>
          </label>

          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-900">{text.medium_label}</p>
            <div className="grid grid-cols-2 gap-2">
              {PRESSURE_MEDIA.map((medium) => (
                <button key={medium} type="button" aria-label={`pressure-medium-${medium}`} aria-pressed={draft.medium === medium} onClick={() => save({ medium })} className={`${CHOICE} ${draft.medium === medium ? ON : OFF}`}>
                  {text.media[medium]}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.pressure}</span>
              <CommitText label="pressure-test-pressure" inputMode="decimal" value={barField(draft.test_pressure_bar)} onCommit={(v) => commitBar('test_pressure_bar', v)} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.duration}</span>
              <CommitText label="pressure-duration" inputMode="numeric" value={draft.duration_min === null ? '' : String(draft.duration_min)} onCommit={commitDuration} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.drop}</span>
              <CommitText label="pressure-drop" inputMode="decimal" value={barField(draft.pressure_drop_bar)} onCommit={(v) => commitBar('pressure_drop_bar', v)} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_on}</span>
              <input type="date" aria-label="pressure-held-on" value={draft.held_on ?? ''} onChange={(e) => save({ held_on: e.target.value || null })} className={FIELD} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_time}</span>
              <CommitText label="pressure-held-time" type="time" value={draft.held_time ?? ''} onCommit={(v) => save({ held_time: v || null })} />
            </label>
          </div>

          <fieldset className="space-y-1">
            <legend className="text-sm font-semibold text-slate-900">{text.photos}</legend>
            <p className="text-xs text-slate-600 break-words">{text.photos_hint.replace('{max}', String(MAX_PRESSURE_PHOTOS))}</p>
            {draft.photo_options.length === 0 && <p className="text-xs text-amber-800 break-words">{text.photos_none}</p>}
            {atLimit && <p className="text-xs text-slate-600 break-words">{text.photos_limit.replace('{max}', String(MAX_PRESSURE_PHOTOS))}</p>}
            {draft.photo_options.map((photo) => {
              const chosen = draft.photo_ids.includes(photo.id);
              return (
                <label key={photo.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                  <input type="checkbox" aria-label={`pressure-photo-${photo.id}`} className="h-5 w-5 shrink-0" checked={chosen} disabled={!chosen && atLimit} onChange={() => togglePhoto(photo.id)} />
                  <span className="min-w-0 break-words">{photoLabel(photo.caption, photo.place, photo.captured_at ?? photo.created_at)}</span>
                </label>
              );
            })}
          </fieldset>

          <label className="flex items-start gap-3 min-h-11 text-sm text-slate-900">
            <input type="checkbox" aria-label="pressure-absent" className="mt-1 h-5 w-5 shrink-0" checked={draft.customer_absent} onChange={() => save({ customer_absent: !draft.customer_absent })} />
            <span className="min-w-0">
              <span className="block font-medium break-words">{text.absent}</span>
              <span className="block text-xs text-slate-600 break-words">{text.absent_hint}</span>
            </span>
          </label>

          {draft.customer_absent ? (
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.notified_on}</span>
              <input type="date" aria-label="pressure-notified-on" value={draft.notified_on ?? ''} onChange={(e) => save({ notified_on: e.target.value || null })} className={FIELD} />
            </label>
          ) : (
            <fieldset className="space-y-1">
              <legend className="text-sm font-semibold text-slate-900">{text.attendees}</legend>
              {people.length === 0 && <p className="text-xs text-slate-600 break-words">{text.attendees_none}</p>}
              {people.map((person) => (
                <label key={person.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                  <input type="checkbox" aria-label={`pressure-person-${person.id}`} className="h-5 w-5 shrink-0" checked={presentIds.has(person.id)} onChange={() => togglePerson(person.id)} />
                  <span className="min-w-0 break-words">{person.name}{person.role_title ? ` · ${person.role_title}` : ''}</span>
                </label>
              ))}
              {strangers.map((a, index) => (
                <div key={`${a.name}-${index}`} className="flex items-center justify-between gap-3 min-h-11 text-sm text-slate-900">
                  <span className="min-w-0 break-words">{a.name}{a.role ? ` · ${a.role}` : ''}</span>
                  <button type="button" aria-label={`pressure-extra-remove-${index}`} onClick={() => removeExtra(index)} className={`shrink-0 ${BUTTON} text-red-800 pe-surface border-red-300`}><Ico>🗑️</Ico>{text.extra_remove}</button>
                </div>
              ))}
              <label className="block space-y-1 pt-1">
                <span className="block text-xs text-slate-700 break-words">{text.extra_label}</span>
                <input aria-label="pressure-extra" value={extra} onChange={(e) => setExtra(e.target.value)} className={FIELD} />
              </label>
              <button type="button" aria-label="pressure-extra-add" disabled={!extra.trim()} onClick={addExtra} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300`}><Ico>➕</Ico>{text.extra_add}</button>
            </fieldset>
          )}

          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-900">{text.result}</p>
            <p className="text-xs text-slate-600 break-words">{text.result_hint}</p>
            <div className="grid grid-cols-1 gap-2">
              {PRESSURE_RESULTS.map((result) => (
                <button key={result} type="button" aria-label={`pressure-result-${result}`} aria-pressed={draft.result === result} onClick={() => save({ result })} className={`${BUTTON} ${draft.result === result ? ON : OFF}`}>
                  {text.result_options[result]}
                </button>
              ))}
            </div>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{draft.result === 'NEGATIVE' ? text.remarks_required : text.remarks}</span>
              <CommitText label="pressure-remarks" multiline value={draft.remarks ?? ''} onCommit={(v) => save({ remarks: v.trim() === '' ? null : v })} />
            </label>
          </div>

          <section aria-label="pressure-gate" className="space-y-2 border-t border-slate-200 pt-3">
            <h4 className="text-sm font-semibold text-slate-900 break-words">{text.gate_title}</h4>
            {draft.blockers.length === 0 ? (
              <p className="text-sm text-emerald-800 break-words">{text.gate_ready}</p>
            ) : (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-red-700 break-words">{text.gate_blocked}</p>
                <ul className="space-y-2">
                  {draft.blockers.map((blocker) => (
                    <li key={blocker.code} aria-label={`gate-${blocker.code}`} className="text-xs text-slate-800 break-words bg-red-50 border border-red-200 rounded-xl px-3 py-2">
                      {text.gate[blocker.code]}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {saving > 0 && <p role="status" aria-label="pressure-saving" className="text-xs text-slate-600">{text.saving}</p>}
          {error && <p role="alert" aria-label="pressure-error" className="text-sm text-red-700 break-words">{error}</p>}
          {note && <p role="status" aria-label="pressure-note" className="text-sm text-emerald-800 break-words">{note}</p>}
          <button type="button" aria-label="preview-pressure" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}><Ico>👁️</Ico>{text.preview}</button>
          <button type="button" aria-label="issue-pressure" disabled={busy || draft.blockers.length > 0} onClick={() => void issue()} className={`w-full ${BUTTON} text-white bg-sky-700 border-sky-700 hover:bg-sky-800`}>{text.issue}</button>
          <button type="button" aria-label="close-pressure-form" disabled={busy} onClick={() => setOpen(false)} className={`w-full ${BUTTON} text-slate-800 pe-surface border-slate-300 hover:bg-slate-100`}><Ico>✖️</Ico>{text.close}</button>
          <button type="button" aria-label="abandon-pressure-draft" disabled={busy} onClick={() => void abandon()} className={`w-full ${BUTTON} text-red-800 pe-surface border-red-300 hover:bg-red-50`}>{confirmAbandon ? text.abandon_confirm : text.abandon}</button>
        </div>
      )}

      {!open && error && <p role="alert" aria-label="pressure-error" className="text-sm text-red-700 break-words">{error}</p>}
      {!open && note && <p role="status" aria-label="pressure-note" className="text-sm text-emerald-800 break-words">{note}</p>}
    </article>
  );
}
