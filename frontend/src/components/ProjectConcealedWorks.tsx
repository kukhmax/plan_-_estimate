import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchContractCatalog } from '../api/contractCatalog';
import { abandonConcealedDraft, fetchConcealedWorks, issueConcealed, openConcealedDraft, updateConcealed } from '../api/concealedWorks';
import { previewConcealedPdf } from '../api/documents';
import { ApiError } from '../api/http';
import { fetchRepresentatives } from '../api/representatives';
import { fetchRooms } from '../api/rooms';
import { fetchSurfaces } from '../api/surfaces';
import { useI18n } from '../hooks/useI18n';
import type { Concealed, ConcealedBlocker, ConcealedChange, ConcealedResult, CoverConsent } from '../types/concealed';
import type { ContractCatalog } from '../types/contractCatalog';
import type { ProjectRepresentative } from '../types/representative';
import { documentErrorText } from '../utils/documentErrors';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';
import { CommitText, FIELD } from './CommitText';

interface ProjectConcealedWorksProps {
  projectId: string;
}

const BUTTON = 'min-h-11 px-3 text-sm font-semibold rounded-xl border transition disabled:opacity-60 break-words';
const OFF = 'bg-white text-slate-900 border-slate-300 hover:bg-slate-50';
const ON = 'bg-slate-900 text-white border-slate-900';
const RESULTS: ConcealedResult[] = ['ACCEPTED', 'WITH_REMARKS'];
const CONSENTS: CoverConsent[] = ['GIVEN', 'WITHHELD'];

interface SurfaceChoice {
  id: string;
  label: string;
  room: string;
}

function nowParts(): { day: string; time: string } {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return { day: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`, time: `${pad(now.getHours())}:${pad(now.getMinutes())}` };
}

/**
 * Stage 16G.2 — the protocol of acceptance of concealed works, on the phone. The owner stands at the wall before the next layer goes
 * on: chooses the surface and the kind of work, ticks the photos that are the evidence, taps the result and the consent. Every tap is
 * saved at once (one request at a time, in order); the server answers with the whole protocol and what is still missing. When the
 * customer did not come, one switch turns it into a one-sided protocol that asks for the day he was notified instead of people.
 */
export function ProjectConcealedWorks({ projectId }: ProjectConcealedWorksProps) {
  const { t } = useI18n();
  const text = t.concealed;
  const catalogText = t.contractCatalog;
  const [draft, setDraft] = useState<Concealed | null>(null);
  const [latest, setLatest] = useState<Concealed | null>(null);
  const [catalog, setCatalog] = useState<ContractCatalog | null>(null);
  const [people, setPeople] = useState<ProjectRepresentative[]>([]);
  const [surfaces, setSurfaces] = useState<SurfaceChoice[]>([]);
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
      const list = await fetchConcealedWorks(projectId);
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
    if (err instanceof ApiError && err.code === 'CONCEALED_INVALID') {
      const reason = (err.detail as { details?: { reason?: string } } | null)?.details?.reason ?? '';
      return text.errors[reason as keyof typeof text.errors] ?? text.errors.UNKNOWN;
    }
    if (err instanceof ApiError && err.code === 'CONCEALED_NOT_EDITABLE') return text.errors.NOT_EDITABLE;
    return text.errors.UNKNOWN;
  };

  /** One request at a time, in the order of the taps; the answer replaces the screen's copy of the protocol. */
  const save = (changes: ConcealedChange, id?: string) => {
    const target = id ?? draft?.id;
    if (!target) return;
    queue.current = queue.current.then(async () => {
      if (!alive.current) return;
      setSaving((n) => n + 1);
      try {
        const next = await updateConcealed(projectId, target, changes);
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
      const [protocol, loadedCatalog, representatives, roomList] = await Promise.all([
        openConcealedDraft(projectId),
        catalog ? Promise.resolve(catalog) : fetchContractCatalog(),
        fetchRepresentatives(projectId),
        fetchRooms(projectId),
      ]);
      const perRoom = await Promise.all(roomList.items.map((room) => fetchSurfaces(projectId, room.id)));
      if (!alive.current) return;
      const labels = { wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling };
      setSurfaces(
        roomList.items.flatMap((room, index) =>
          perRoom[index].items.map((surface) => ({ id: surface.id, room: room.name, label: getSurfaceDisplayName(surface, labels) })),
        ),
      );
      setCatalog(loadedCatalog);
      setPeople(representatives.items.filter((p) => !p.is_archived));
      setDraft(protocol);
      setOpen(true);
      const { day, time } = nowParts();  // the usual day and hour: now
      const defaults: ConcealedChange = {};
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
      await previewConcealedPdf(projectId);
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
      await issueConcealed(projectId, draft.id);
      if (!alive.current) return;
      setOpen(false);
      setDraft(null);
      setNote(text.issue_note);
      await load();
    } catch (err) {
      if (!alive.current) return;
      const blockers = err instanceof ApiError && err.code === 'CONCEALED_GATE_BLOCKED'
        ? (err.detail as { details?: { blockers?: ConcealedBlocker[] } } | null)?.details?.blockers
        : undefined;
      if (blockers && draft) setDraft({ ...draft, blockers });
      else setError(err instanceof ApiError && err.code === 'CONCEALED_NOT_EDITABLE' ? text.errors.NOT_EDITABLE : documentErrorText(t.documents.errors, err));
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
      await abandonConcealedDraft(projectId, draft.id);
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

  const photoLabel = (caption: string | null, capturedAt: string | null): string => {
    const taken = capturedAt ? capturedAt.replace('T', ' ').slice(0, 16) : null;
    return [caption ?? text.photo_untitled, taken].filter(Boolean).join(' · ');
  };

  const kinds = catalog?.work_kinds.items ?? [];
  const rooms = Array.from(new Set(surfaces.map((s) => s.room)));

  return (
    <article aria-label="project-concealed" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
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
          <button type="button" aria-label="start-concealed" disabled={busy} onClick={() => void start()} className={`w-full ${BUTTON} text-white bg-blue-600 border-blue-600 hover:bg-blue-700`}>
            {busy ? text.loading : draft ? text.continue : latest ? text.new : text.start}
          </button>
          <button type="button" aria-label="preview-concealed" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>{text.preview}</button>
        </>
      )}

      {open && draft && catalog && (
        <div aria-label="concealed-form" className="space-y-4">
          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900">{text.surface}</span>
            <select aria-label="concealed-surface" value={draft.surface?.id ?? ''} onChange={(e) => save({ surface_id: e.target.value || null })} className={FIELD}>
              <option value="">{text.surface_none}</option>
              {rooms.map((room) => (
                <optgroup key={room} label={room}>
                  {surfaces.filter((s) => s.room === room).map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </optgroup>
              ))}
            </select>
            {surfaces.length === 0 && <span className="block text-xs text-slate-600 break-words">{text.surfaces_none}</span>}
          </label>

          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900">{text.work_kind}</span>
            <select aria-label="concealed-work-kind" value={draft.work_kind ?? ''} onChange={(e) => save({ work_kind: e.target.value || null })} className={FIELD}>
              <option value="">{text.work_kind_none}</option>
              {kinds.map((kind) => (
                <option key={kind.key} value={kind.key}>{catalogText.work_kinds[kind.key as keyof typeof catalogText.work_kinds] ?? kind.key}</option>
              ))}
            </select>
          </label>
          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900 break-words">{text.work_note}</span>
            <CommitText label="concealed-work-note" multiline value={draft.work_note ?? ''} onCommit={(v) => save({ work_note: v.trim() === '' ? null : v })} />
          </label>

          <div className="grid grid-cols-1 gap-3">
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_on}</span>
              <input type="date" aria-label="concealed-held-on" value={draft.held_on ?? ''} onChange={(e) => save({ held_on: e.target.value || null })} className={FIELD} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_time}</span>
              <CommitText label="concealed-held-time" type="time" value={draft.held_time ?? ''} onCommit={(v) => save({ held_time: v || null })} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.material}</span>
              <CommitText label="concealed-material" value={draft.material ?? ''} onCommit={(v) => save({ material: v.trim() === '' ? null : v })} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.batch}</span>
              <CommitText label="concealed-batch" value={draft.batch ?? ''} onCommit={(v) => save({ batch: v.trim() === '' ? null : v })} />
            </label>
          </div>

          <fieldset className="space-y-1">
            <legend className="text-sm font-semibold text-slate-900">{text.photos}</legend>
            <p className="text-xs text-slate-600 break-words">{text.photos_hint}</p>
            {!draft.surface && <p className="text-xs text-slate-600 break-words">{text.photos_pick_surface}</p>}
            {draft.surface && draft.photo_options.length === 0 && <p className="text-xs text-amber-800 break-words">{text.photos_none}</p>}
            {draft.photo_options.map((photo) => (
              <label key={photo.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                <input type="checkbox" aria-label={`concealed-photo-${photo.id}`} className="h-5 w-5 shrink-0" checked={draft.photo_ids.includes(photo.id)} onChange={() => togglePhoto(photo.id)} />
                <span className="min-w-0 break-words">{photoLabel(photo.caption, photo.captured_at)}</span>
              </label>
            ))}
          </fieldset>

          <label className="flex items-start gap-3 min-h-11 text-sm text-slate-900">
            <input type="checkbox" aria-label="concealed-absent" className="mt-1 h-5 w-5 shrink-0" checked={draft.customer_absent} onChange={() => save({ customer_absent: !draft.customer_absent })} />
            <span className="min-w-0">
              <span className="block font-medium break-words">{text.absent}</span>
              <span className="block text-xs text-slate-600 break-words">{text.absent_hint}</span>
            </span>
          </label>

          {draft.customer_absent ? (
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.notified_on}</span>
              <input type="date" aria-label="concealed-notified-on" value={draft.notified_on ?? ''} onChange={(e) => save({ notified_on: e.target.value || null })} className={FIELD} />
            </label>
          ) : (
            <fieldset className="space-y-1">
              <legend className="text-sm font-semibold text-slate-900">{text.attendees}</legend>
              {people.length === 0 && <p className="text-xs text-slate-600 break-words">{text.attendees_none}</p>}
              {people.map((person) => (
                <label key={person.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                  <input type="checkbox" aria-label={`concealed-person-${person.id}`} className="h-5 w-5 shrink-0" checked={presentIds.has(person.id)} onChange={() => togglePerson(person.id)} />
                  <span className="min-w-0 break-words">{person.name}{person.role_title ? ` · ${person.role_title}` : ''}</span>
                </label>
              ))}
              {strangers.map((a, index) => (
                <div key={`${a.name}-${index}`} className="flex items-center justify-between gap-3 min-h-11 text-sm text-slate-900">
                  <span className="min-w-0 break-words">{a.name}{a.role ? ` · ${a.role}` : ''}</span>
                  <button type="button" aria-label={`concealed-extra-remove-${index}`} onClick={() => removeExtra(index)} className={`shrink-0 ${BUTTON} text-red-800 bg-white border-red-300`}>{text.extra_remove}</button>
                </div>
              ))}
              <label className="block space-y-1 pt-1">
                <span className="block text-xs text-slate-700 break-words">{text.extra_label}</span>
                <input aria-label="concealed-extra" value={extra} onChange={(e) => setExtra(e.target.value)} className={FIELD} />
              </label>
              <button type="button" aria-label="concealed-extra-add" disabled={!extra.trim()} onClick={addExtra} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300`}>{text.extra_add}</button>
            </fieldset>
          )}

          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-900">{text.result}</p>
            <div className="grid grid-cols-1 gap-2">
              {RESULTS.map((result) => (
                <button key={result} type="button" aria-label={`concealed-result-${result}`} aria-pressed={draft.result === result} onClick={() => save({ result })} className={`${BUTTON} ${draft.result === result ? ON : OFF}`}>
                  {text.result_options[result]}
                </button>
              ))}
            </div>
            {draft.result === 'WITH_REMARKS' && (
              <label className="block space-y-1">
                <span className="block text-sm font-medium text-slate-900">{text.remarks}</span>
                <CommitText label="concealed-remarks" multiline value={draft.remarks ?? ''} onCommit={(v) => save({ remarks: v.trim() === '' ? null : v })} />
              </label>
            )}
          </div>

          {!draft.customer_absent && (
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-900">{text.consent}</p>
              <div className="grid grid-cols-1 gap-2">
                {CONSENTS.map((consent) => (
                  <button key={consent} type="button" aria-label={`concealed-consent-${consent}`} aria-pressed={draft.cover_consent === consent} onClick={() => save({ cover_consent: consent })} className={`${BUTTON} ${draft.cover_consent === consent ? ON : OFF}`}>
                    {text.consent_options[consent]}
                  </button>
                ))}
              </div>
            </div>
          )}

          <section aria-label="concealed-gate" className="space-y-2 border-t border-slate-200 pt-3">
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

          {saving > 0 && <p role="status" aria-label="concealed-saving" className="text-xs text-slate-600">{text.saving}</p>}
          {error && <p role="alert" aria-label="concealed-error" className="text-sm text-red-700 break-words">{error}</p>}
          {note && <p role="status" aria-label="concealed-note" className="text-sm text-emerald-800 break-words">{note}</p>}
          <button type="button" aria-label="preview-concealed" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>{text.preview}</button>
          <button type="button" aria-label="issue-concealed" disabled={busy || draft.blockers.length > 0} onClick={() => void issue()} className={`w-full ${BUTTON} text-white bg-sky-700 border-sky-700 hover:bg-sky-800`}>{text.issue}</button>
          <button type="button" aria-label="close-concealed-form" disabled={busy} onClick={() => setOpen(false)} className={`w-full ${BUTTON} text-slate-800 bg-white border-slate-300 hover:bg-slate-100`}>{text.close}</button>
          <button type="button" aria-label="abandon-concealed-draft" disabled={busy} onClick={() => void abandon()} className={`w-full ${BUTTON} text-red-800 bg-white border-red-300 hover:bg-red-50`}>{confirmAbandon ? text.abandon_confirm : text.abandon}</button>
        </div>
      )}

      {!open && error && <p role="alert" aria-label="concealed-error" className="text-sm text-red-700 break-words">{error}</p>}
      {!open && note && <p role="status" aria-label="concealed-note" className="text-sm text-emerald-800 break-words">{note}</p>}
    </article>
  );
}
