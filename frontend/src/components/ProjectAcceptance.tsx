import { useCallback, useEffect, useRef, useState } from 'react';
import { abandonAcceptanceDraft, fetchAcceptances, issueAcceptance, openAcceptanceDraft, updateAcceptance } from '../api/acceptances';
import { fetchContractCatalog } from '../api/contractCatalog';
import { previewAcceptancePdf } from '../api/documents';
import { ApiError } from '../api/http';
import { fetchRepresentatives } from '../api/representatives';
import { useI18n } from '../hooks/useI18n';
import type {
  Acceptance, AcceptanceBlocker, AcceptanceChange, AcceptancePhoto, AcceptanceResult, AcceptanceSurface, RemarkClass,
} from '../types/acceptance';
import type { ContractCatalog } from '../types/contractCatalog';
import type { ProjectRepresentative } from '../types/representative';
import { documentErrorText } from '../utils/documentErrors';
import { CommitText, FIELD } from './CommitText';

interface ProjectAcceptanceProps {
  projectId: string;
}

const BUTTON = 'min-h-11 px-3 text-sm font-semibold rounded-xl border transition disabled:opacity-60 break-words';
const OFF = 'bg-white text-slate-900 border-slate-300 hover:bg-slate-50';
const ON = 'bg-slate-900 text-white border-slate-900';
const CLASSES: RemarkClass[] = ['REMOVABLE', 'SIGNIFICANT'];
const BADGE: Record<AcceptanceResult, string> = {
  ACCEPTED: 'bg-emerald-50 border-emerald-300 text-emerald-900',
  ACCEPTED_WITH_REMARKS: 'bg-amber-50 border-amber-300 text-amber-900',
  NOT_ACCEPTED: 'bg-red-50 border-red-300 text-red-900',
};

/** The remark being written or changed on one surface. */
interface RemarkForm {
  surfaceId: string;
  id: string | null;
  place: string;
  description: string;
  classification: RemarkClass | '';
  deadline: string;
  photoIds: string[];
}

function nowParts(): { day: string; time: string } {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return { day: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`, time: `${pad(now.getHours())}:${pad(now.getMinutes())}` };
}

/** The key of a new remark is a UUID the server accepts as it is (a remark may be written offline later). */
function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/**
 * Stage 16H.3 — the final or partial acceptance of the work, on the phone. The owner stands in the room with the customer: ticks the
 * rooms he takes over (all of them = final), sees every surface with the state of its planned works, ticks it as checked and writes
 * the remarks (place, description, removable or significant, a deadline, the photos of the defect). **The result is never typed**: the
 * server derives it from the works and the remarks and the screen only shows it. Every tap is saved at once (one request at a time, in
 * order); the server answers with the whole protocol and what is still missing.
 */
export function ProjectAcceptance({ projectId }: ProjectAcceptanceProps) {
  const { t } = useI18n();
  const text = t.acceptance;
  const catalogText = t.contractCatalog;
  const [draft, setDraft] = useState<Acceptance | null>(null);
  const [latest, setLatest] = useState<Acceptance | null>(null);
  const [catalog, setCatalog] = useState<ContractCatalog | null>(null);
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
  const [form, setForm] = useState<RemarkForm | null>(null);
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
      const list = await fetchAcceptances(projectId);
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
    if (err instanceof ApiError && err.code === 'ACCEPTANCE_INVALID') {
      const reason = (err.detail as { details?: { reason?: string } } | null)?.details?.reason ?? '';
      return text.errors[reason as keyof typeof text.errors] ?? text.errors.UNKNOWN;
    }
    if (err instanceof ApiError && err.code === 'ACCEPTANCE_NOT_EDITABLE') return text.errors.NOT_EDITABLE;
    return text.errors.UNKNOWN;
  };

  /** One request at a time, in the order of the taps; the answer replaces the screen's copy of the protocol. */
  const save = (changes: AcceptanceChange, id?: string) => {
    const target = id ?? draft?.id;
    if (!target) return;
    queue.current = queue.current.then(async () => {
      if (!alive.current) return;
      setSaving((n) => n + 1);
      try {
        const next = await updateAcceptance(projectId, target, changes);
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
      const [protocol, loadedCatalog, representatives] = await Promise.all([
        openAcceptanceDraft(projectId),
        catalog ? Promise.resolve(catalog) : fetchContractCatalog(),
        fetchRepresentatives(projectId),
      ]);
      if (!alive.current) return;
      setCatalog(loadedCatalog);
      setPeople(representatives.items.filter((p) => !p.is_archived));
      setDraft(protocol);
      setOpen(true);
      setForm(null);
      const { day, time } = nowParts();  // the usual day and hour: now; the usual scope: every room that has planned works
      const defaults: AcceptanceChange = {};
      if (!protocol.held_on) defaults.held_on = day;
      if (!protocol.held_time) defaults.held_time = time;
      if (protocol.room_ids.length === 0 && protocol.rooms.length > 0) defaults.room_ids = protocol.rooms.map((r) => r.id);
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
      await previewAcceptancePdf(projectId);
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
      await issueAcceptance(projectId, draft.id);
      if (!alive.current) return;
      setOpen(false);
      setDraft(null);
      setForm(null);
      setNote(text.issue_note);
      await load();
    } catch (err) {
      if (!alive.current) return;
      const blockers = err instanceof ApiError && err.code === 'ACCEPTANCE_GATE_BLOCKED'
        ? (err.detail as { details?: { blockers?: AcceptanceBlocker[] } } | null)?.details?.blockers
        : undefined;
      if (blockers && draft) setDraft({ ...draft, blockers });
      else setError(err instanceof ApiError && err.code === 'ACCEPTANCE_NOT_EDITABLE' ? text.errors.NOT_EDITABLE : documentErrorText(t.documents.errors, err));
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
      await abandonAcceptanceDraft(projectId, draft.id);
      if (!alive.current) return;
      setDraft(null);
      setOpen(false);
      setForm(null);
      setConfirmAbandon(false);
      setNote(text.abandoned);
    } catch {
      if (alive.current) setError(text.errors.UNKNOWN);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  // --- the scope and the instruments ------------------------------------------------------------------------------------------
  const toggleRoom = (id: string) => {
    if (!draft) return;
    save({ room_ids: draft.room_ids.includes(id) ? draft.room_ids.filter((x) => x !== id) : [...draft.room_ids, id] });
  };
  const toggleInstrument = (key: string) => {
    if (!draft) return;
    save({ instrument_keys: draft.instrument_keys.includes(key) ? draft.instrument_keys.filter((x) => x !== key) : [...draft.instrument_keys, key] });
  };

  // --- the people present -----------------------------------------------------------------------------------------------------
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

  // --- surfaces and remarks ---------------------------------------------------------------------------------------------------
  const toggleAssessed = (surface: AcceptanceSurface) => save({ surfaces: { [surface.id]: { assessed: !surface.assessed } } });
  const removeRemark = (surface: AcceptanceSurface, remarkId: string) => save({ surfaces: { [surface.id]: { remarks: { [remarkId]: null } } } });
  const openForm = (surface: AcceptanceSurface, remarkId: string | null) => {
    const remark = surface.remarks.find((r) => r.id === remarkId);
    setForm({
      surfaceId: surface.id, id: remarkId, place: remark?.place ?? '', description: remark?.description ?? '',
      classification: remark?.classification ?? '', deadline: remark?.deadline ?? '', photoIds: remark?.photo_ids ?? [],
    });
  };
  const formReady = (f: RemarkForm) =>
    f.place.trim() !== '' && f.description.trim() !== '' && f.classification !== '' && (f.classification !== 'REMOVABLE' || f.deadline !== '');
  const saveForm = () => {
    if (!form || !formReady(form) || form.classification === '') return;
    // writing a remark means the surface was looked at: it is marked as checked in the same request
    save({
      surfaces: {
        [form.surfaceId]: {
          assessed: true,
          remarks: {
            [form.id ?? newId()]: {
              place: form.place.trim(), description: form.description.trim(), classification: form.classification,
              deadline: form.classification === 'REMOVABLE' ? form.deadline : null, photo_ids: form.photoIds,
            },
          },
        },
      },
    });
    setForm(null);
  };
  const toggleFormPhoto = (id: string) =>
    setForm((f) => (f ? { ...f, photoIds: f.photoIds.includes(id) ? f.photoIds.filter((x) => x !== id) : [...f.photoIds, id] } : f));

  const photoLabel = (photo: AcceptancePhoto): string => {
    const taken = photo.captured_at ? photo.captured_at.replace('T', ' ').slice(0, 16) : null;
    return [photo.caption ?? text.photo_untitled, taken].filter(Boolean).join(' · ');
  };
  const className = (key: string) => catalogText.defects[key as RemarkClass];
  const standardLabel = (key: string) => catalogText.evaluation[key as keyof typeof catalogText.evaluation] ?? key;

  return (
    <article aria-label="project-acceptance" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
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
          <button type="button" aria-label="start-acceptance" disabled={busy} onClick={() => void start()} className={`w-full ${BUTTON} text-white bg-blue-600 border-blue-600 hover:bg-blue-700`}>
            {busy ? text.loading : draft ? text.continue : latest ? text.new : text.start}
          </button>
          <button type="button" aria-label="preview-acceptance" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>{text.preview}</button>
        </>
      )}

      {open && draft && catalog && (
        <div aria-label="acceptance-form" className="space-y-4">
          <fieldset className="space-y-1">
            <legend className="text-sm font-semibold text-slate-900">{text.scope}</legend>
            <p className="text-xs text-slate-600 break-words">{text.scope_hint}</p>
            {draft.rooms.length === 0 && <p className="text-xs text-amber-800 break-words">{text.rooms_none}</p>}
            {draft.rooms.map((room) => (
              <label key={room.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                <input type="checkbox" aria-label={`acceptance-room-${room.id}`} className="h-5 w-5 shrink-0" checked={draft.room_ids.includes(room.id)} onChange={() => toggleRoom(room.id)} />
                <span className="min-w-0 break-words">{text.room_row.replace('{name}', room.name).replace('{n}', String(room.surfaces))}</span>
              </label>
            ))}
            {draft.scope_kind && <p aria-label="acceptance-scope-kind" className="text-sm font-semibold text-slate-900 break-words">{text.scope_kind[draft.scope_kind]}</p>}
          </fieldset>

          <div className="grid grid-cols-1 gap-3">
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_on}</span>
              <input type="date" aria-label="acceptance-held-on" value={draft.held_on ?? ''} onChange={(e) => save({ held_on: e.target.value || null })} className={FIELD} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_time}</span>
              <CommitText label="acceptance-held-time" type="time" value={draft.held_time ?? ''} onCommit={(v) => save({ held_time: v || null })} />
            </label>
          </div>

          <label className="flex items-start gap-3 min-h-11 text-sm text-slate-900">
            <input type="checkbox" aria-label="acceptance-absent" className="mt-1 h-5 w-5 shrink-0" checked={draft.customer_absent} onChange={() => save({ customer_absent: !draft.customer_absent })} />
            <span className="min-w-0">
              <span className="block font-medium break-words">{text.absent}</span>
              <span className="block text-xs text-slate-600 break-words">{text.absent_hint}</span>
            </span>
          </label>

          {draft.customer_absent ? (
            <div className="grid grid-cols-1 gap-3">
              <label className="block space-y-1">
                <span className="block text-sm font-medium text-slate-900 break-words">{text.notified_on}</span>
                <input type="date" aria-label="acceptance-notified-on" value={draft.notified_on ?? ''} onChange={(e) => save({ notified_on: e.target.value || null })} className={FIELD} />
              </label>
              <label className="block space-y-1">
                <span className="block text-sm font-medium text-slate-900 break-words">{text.renotified_on}</span>
                <input type="date" aria-label="acceptance-renotified-on" value={draft.renotified_on ?? ''} onChange={(e) => save({ renotified_on: e.target.value || null })} className={FIELD} />
              </label>
            </div>
          ) : (
            <fieldset className="space-y-1">
              <legend className="text-sm font-semibold text-slate-900">{text.attendees}</legend>
              {people.length === 0 && <p className="text-xs text-slate-600 break-words">{text.attendees_none}</p>}
              {people.map((person) => (
                <label key={person.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                  <input type="checkbox" aria-label={`acceptance-person-${person.id}`} className="h-5 w-5 shrink-0" checked={presentIds.has(person.id)} onChange={() => togglePerson(person.id)} />
                  <span className="min-w-0 break-words">{person.name}{person.role_title ? ` · ${person.role_title}` : ''}</span>
                </label>
              ))}
              {strangers.map((a, index) => (
                <div key={`${a.name}-${index}`} className="flex items-center justify-between gap-3 min-h-11 text-sm text-slate-900">
                  <span className="min-w-0 break-words">{a.name}{a.role ? ` · ${a.role}` : ''}</span>
                  <button type="button" aria-label={`acceptance-extra-remove-${index}`} onClick={() => removeExtra(index)} className={`shrink-0 ${BUTTON} text-red-800 bg-white border-red-300`}>{text.extra_remove}</button>
                </div>
              ))}
              <label className="block space-y-1 pt-1">
                <span className="block text-xs text-slate-700 break-words">{text.extra_label}</span>
                <input aria-label="acceptance-extra" value={extra} onChange={(e) => setExtra(e.target.value)} className={FIELD} />
              </label>
              <button type="button" aria-label="acceptance-extra-add" disabled={!extra.trim()} onClick={addExtra} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300`}>{text.extra_add}</button>
            </fieldset>
          )}

          {draft.conditions.length > 0 && (
            <section aria-label="acceptance-conditions" className="space-y-2">
              <h4 className="text-sm font-semibold text-slate-900">{text.conditions}</h4>
              {draft.conditions.map((condition) => (
                <div key={condition.key} className="text-xs text-slate-700 break-words space-y-1">
                  <p className="font-semibold text-slate-900">{standardLabel(condition.key)}</p>
                  <p>{condition.text_pl}</p>
                  {condition.requires_agreement && <p className="text-amber-800">{text.conditions_agreement}</p>}
                </div>
              ))}
              <label className="block space-y-1">
                <span className="block text-sm font-medium text-slate-900">{text.conditions_note}</span>
                <CommitText label="acceptance-conditions-note" multiline value={draft.conditions_note ?? ''} onCommit={(v) => save({ conditions_note: v.trim() === '' ? null : v })} />
              </label>
            </section>
          )}

          <details className="space-y-1">
            <summary className="min-h-11 flex items-center text-sm font-semibold text-slate-900 cursor-pointer">{text.instruments}</summary>
            {catalog.instruments.items.map((instrument) => (
              <label key={instrument.key} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                <input type="checkbox" aria-label={`acceptance-instrument-${instrument.key}`} className="h-5 w-5 shrink-0" checked={draft.instrument_keys.includes(instrument.key)} onChange={() => toggleInstrument(instrument.key)} />
                <span className="min-w-0 break-words">{catalogText.instruments[instrument.key as keyof typeof catalogText.instruments] ?? instrument.key}</span>
              </label>
            ))}
          </details>

          <section aria-label="acceptance-surfaces" className="space-y-3">
            <h4 className="text-sm font-semibold text-slate-900">{text.surfaces}</h4>
            {draft.surfaces.length === 0 && <p className="text-xs text-slate-600 break-words">{text.surfaces_none}</p>}
            {draft.surfaces.map((surface) => (
              <div key={surface.id} aria-label={`acceptance-surface-${surface.id}`} className="border border-slate-200 rounded-xl p-3 space-y-2">
                <p className="text-sm font-semibold text-slate-900 break-words">
                  {surface.room_name} — {surface.name}
                  {surface.quality_target && <span className="font-normal text-slate-600"> · {text.standard.replace('{key}', surface.quality_target)}</span>}
                </p>
                <ul className="space-y-1">
                  {surface.works.map((work, index) => (
                    <li key={`${work.name}-${index}`} className="flex items-start justify-between gap-3 text-xs text-slate-800">
                      <span className="min-w-0 break-words">{work.name}</span>
                      <span className={`shrink-0 font-semibold ${work.status === 'COMPLETED' ? 'text-emerald-800' : 'text-red-700'}`}>{text.work_state[work.status]}</span>
                    </li>
                  ))}
                </ul>
                {surface.incomplete > 0 && <p className="text-xs font-semibold text-red-700 break-words">{text.works_incomplete.replace('{n}', String(surface.incomplete))}</p>}

                <label className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                  <input type="checkbox" aria-label={`acceptance-assessed-${surface.id}`} className="h-5 w-5 shrink-0" checked={surface.assessed} onChange={() => toggleAssessed(surface)} />
                  <span className="min-w-0 break-words">{text.assessed}</span>
                </label>

                <p className="text-sm font-semibold text-slate-900">{text.remarks}</p>
                {surface.remarks.length === 0 && <p className="text-xs text-slate-600">{text.remarks_none}</p>}
                {surface.remarks.map((remark) => (
                  <div key={remark.id} aria-label={`acceptance-remark-${remark.id}`} className="bg-slate-50 border border-slate-200 rounded-lg p-2 space-y-1">
                    <p className="text-sm text-slate-900 break-words"><span className="font-semibold">{remark.place}</span> — {remark.description}</p>
                    <p className="text-xs text-slate-700 break-words">
                      {className(remark.classification)}
                      {remark.deadline ? ` · ${text.remark_deadline_row.replace('{date}', remark.deadline)}` : ''}
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      <button type="button" aria-label={`acceptance-remark-edit-${remark.id}`} onClick={() => openForm(surface, remark.id)} className={`${BUTTON} ${OFF}`}>{text.remark_edit}</button>
                      <button type="button" aria-label={`acceptance-remark-remove-${remark.id}`} onClick={() => removeRemark(surface, remark.id)} className={`${BUTTON} text-red-800 bg-white border-red-300`}>{text.remark_remove}</button>
                    </div>
                  </div>
                ))}

                {form && form.surfaceId === surface.id ? (
                  <div aria-label="acceptance-remark-form" className="space-y-3 border border-slate-300 rounded-xl p-3">
                    <label className="block space-y-1">
                      <span className="block text-sm font-medium text-slate-900">{text.remark_place}</span>
                      <input aria-label="acceptance-remark-place" value={form.place} onChange={(e) => setForm({ ...form, place: e.target.value })} className={FIELD} />
                    </label>
                    <label className="block space-y-1">
                      <span className="block text-sm font-medium text-slate-900">{text.remark_description}</span>
                      <textarea aria-label="acceptance-remark-description" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className={FIELD} />
                    </label>
                    <div className="space-y-2">
                      <p className="text-sm font-medium text-slate-900">{text.remark_class}</p>
                      <div className="grid grid-cols-1 gap-2">
                        {CLASSES.map((classification) => (
                          <button key={classification} type="button" aria-label={`acceptance-remark-class-${classification}`} aria-pressed={form.classification === classification} onClick={() => setForm({ ...form, classification })} className={`${BUTTON} ${form.classification === classification ? ON : OFF}`}>
                            {className(classification)}
                          </button>
                        ))}
                      </div>
                    </div>
                    {form.classification === 'REMOVABLE' && (
                      <label className="block space-y-1">
                        <span className="block text-sm font-medium text-slate-900">{text.remark_deadline}</span>
                        <input type="date" aria-label="acceptance-remark-deadline" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} className={FIELD} />
                      </label>
                    )}
                    <fieldset className="space-y-1">
                      <legend className="text-sm font-medium text-slate-900">{text.remark_photos}</legend>
                      {surface.photo_options.length === 0 && <p className="text-xs text-slate-600 break-words">{text.remark_photos_none}</p>}
                      {surface.photo_options.map((photo) => (
                        <label key={photo.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                          <input type="checkbox" aria-label={`acceptance-remark-photo-${photo.id}`} className="h-5 w-5 shrink-0" checked={form.photoIds.includes(photo.id)} onChange={() => toggleFormPhoto(photo.id)} />
                          <span className="min-w-0 break-words">{photoLabel(photo)}</span>
                        </label>
                      ))}
                    </fieldset>
                    <button type="button" aria-label="acceptance-remark-save" disabled={!formReady(form)} onClick={saveForm} className={`w-full ${BUTTON} text-white bg-blue-600 border-blue-600 hover:bg-blue-700`}>{text.remark_save}</button>
                    <button type="button" aria-label="acceptance-remark-cancel" onClick={() => setForm(null)} className={`w-full ${BUTTON} text-slate-800 bg-white border-slate-300 hover:bg-slate-100`}>{text.remark_cancel}</button>
                  </div>
                ) : (
                  <button type="button" aria-label={`acceptance-remark-add-${surface.id}`} onClick={() => openForm(surface, null)} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>{text.remark_add}</button>
                )}

                <p aria-label={`acceptance-surface-result-${surface.id}`} className={`text-sm font-semibold border rounded-lg px-3 py-2 break-words ${BADGE[surface.result]}`}>{text.surface_result[surface.result]}</p>
              </div>
            ))}
          </section>

          <section aria-label="acceptance-result" className="space-y-2">
            <h4 className="text-sm font-semibold text-slate-900">{text.result}</h4>
            {draft.result ? (
              <p className={`text-base font-semibold border rounded-xl px-3 py-3 break-words ${BADGE[draft.result]}`}>{text.surface_result[draft.result]}</p>
            ) : (
              <p className="text-xs text-slate-600 break-words">{text.result_none}</p>
            )}
            <p className="text-xs text-slate-600 break-words">{text.result_hint}</p>
          </section>

          <section aria-label="acceptance-settlement" className="space-y-3">
            <h4 className="text-sm font-semibold text-slate-900">{text.settlement}</h4>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900 break-words">{text.amount_due}</span>
              <CommitText label="acceptance-amount-due" inputMode="decimal" value={draft.amount_due ?? ''} onCommit={(v) => save({ amount_due: v.trim() === '' ? null : v.trim() })} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900 break-words">{text.amount_retained}</span>
              <CommitText label="acceptance-amount-retained" inputMode="decimal" value={draft.amount_retained ?? ''} onCommit={(v) => save({ amount_retained: v.trim() === '' ? null : v.trim() })} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900 break-words">{text.batches}</span>
              <CommitText label="acceptance-batches" value={draft.batches ?? ''} onCommit={(v) => save({ batches: v.trim() === '' ? null : v })} />
            </label>
            <label className="flex items-start gap-3 min-h-11 text-sm text-slate-900">
              <input type="checkbox" aria-label="acceptance-instructions" className="mt-1 h-5 w-5 shrink-0" checked={draft.instructions_given} onChange={() => save({ instructions_given: !draft.instructions_given })} />
              <span className="min-w-0 break-words">{text.instructions}</span>
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.notes}</span>
              <CommitText label="acceptance-notes" multiline value={draft.notes ?? ''} onCommit={(v) => save({ notes: v.trim() === '' ? null : v })} />
            </label>
          </section>

          <section aria-label="acceptance-gate" className="space-y-2 border-t border-slate-200 pt-3">
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

          {saving > 0 && <p role="status" aria-label="acceptance-saving" className="text-xs text-slate-600">{text.saving}</p>}
          {error && <p role="alert" aria-label="acceptance-error" className="text-sm text-red-700 break-words">{error}</p>}
          {note && <p role="status" aria-label="acceptance-note" className="text-sm text-emerald-800 break-words">{note}</p>}
          <button type="button" aria-label="preview-acceptance" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>{text.preview}</button>
          <button type="button" aria-label="issue-acceptance" disabled={busy || draft.blockers.length > 0} onClick={() => void issue()} className={`w-full ${BUTTON} text-white bg-sky-700 border-sky-700 hover:bg-sky-800`}>{text.issue}</button>
          <button type="button" aria-label="close-acceptance-form" disabled={busy} onClick={() => setOpen(false)} className={`w-full ${BUTTON} text-slate-800 bg-white border-slate-300 hover:bg-slate-100`}>{text.close}</button>
          <button type="button" aria-label="abandon-acceptance-draft" disabled={busy} onClick={() => void abandon()} className={`w-full ${BUTTON} text-red-800 bg-white border-red-300 hover:bg-red-50`}>{confirmAbandon ? text.abandon_confirm : text.abandon}</button>
        </div>
      )}

      {!open && error && <p role="alert" aria-label="acceptance-error" className="text-sm text-red-700 break-words">{error}</p>}
      {!open && note && <p role="status" aria-label="acceptance-note" className="text-sm text-emerald-800 break-words">{note}</p>}
    </article>
  );
}
