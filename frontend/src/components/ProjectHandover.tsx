import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchContractCatalog } from '../api/contractCatalog';
import { previewHandoverPdf } from '../api/documents';
import { abandonHandoverDraft, fetchHandovers, issueHandover, openHandoverDraft, updateHandover } from '../api/handovers';
import { ApiError } from '../api/http';
import { fetchRepresentatives } from '../api/representatives';
import { fetchRooms } from '../api/rooms';
import { useI18n } from '../hooks/useI18n';
import type { ContractCatalog, PremisesRequirement } from '../types/contractCatalog';
import type {
  Handover,
  HandoverBlocker,
  HandoverChange,
  HandoverDecision,
  MeasuredValue,
  RequirementState,
} from '../types/handover';
import type { ProjectRepresentative } from '../types/representative';
import { documentErrorText } from '../utils/documentErrors';
import { formatRequired, numberText, parseNumber } from '../utils/handover';
import { CommitText, FIELD } from './CommitText';

interface ProjectHandoverProps {
  projectId: string;
}

const BUTTON = 'min-h-11 px-3 text-sm font-semibold rounded-xl border transition disabled:opacity-60 break-words';
const STATES: RequirementState[] = ['YES', 'NO', 'CONDITIONAL', 'NOT_APPLICABLE'];
const DECISIONS: HandoverDecision[] = ['HANDED_OVER', 'CONDITIONAL', 'NOT_HANDED_OVER'];
const STATE_ON: Record<RequirementState, string> = {
  YES: 'bg-emerald-700 text-white border-emerald-700',
  NO: 'bg-red-700 text-white border-red-700',
  CONDITIONAL: 'bg-amber-600 text-white border-amber-600',
  NOT_APPLICABLE: 'bg-slate-700 text-white border-slate-700',
};
const OFF = 'bg-white text-slate-900 border-slate-300 hover:bg-slate-50';

function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * Stage 16F.3 — the protocol of handing over the premises, on the phone. The owner stands in the room and taps: a state per
 * requirement (four large buttons), "everything met" in one tap, the decision per room. Every tap is saved at once (one request at
 * a time, in order), so nothing is lost when the signal drops; the server answers with the whole protocol, its suggested decisions
 * and what is still missing. The numbers each requirement asks for are the contract's; the screen only shows them.
 */
export function ProjectHandover({ projectId }: ProjectHandoverProps) {
  const { t } = useI18n();
  const text = t.handover;
  const catalogText = t.contractCatalog;
  const [draft, setDraft] = useState<Handover | null>(null);
  const [latest, setLatest] = useState<Handover | null>(null);
  const [catalog, setCatalog] = useState<ContractCatalog | null>(null);
  const [people, setPeople] = useState<ProjectRepresentative[]>([]);
  const [rooms, setRooms] = useState<Array<{ id: string; name: string }>>([]);
  const [open, setOpen] = useState(false);
  const [openRoom, setOpenRoom] = useState<string | null>(null);
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
  const rangeTexts = useRef<Record<string, string>>({});  // a limit typed but not saved yet: a range is saved when both limits are there

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const requirements: PremisesRequirement[] = useMemo(() => catalog?.requirements.items ?? [], [catalog]);
  const unitText = (unit: string | null) => (unit ? catalogText.units[unit as keyof typeof catalogText.units] ?? unit : null);
  const roomName = (id: string) => rooms.find((r) => r.id === id)?.name ?? id;

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const list = await fetchHandovers(projectId);
      if (!alive.current) return;
      setDraft(list.items.find((h) => h.status === 'DRAFT') ?? null);
      setLatest(list.items.find((h) => h.status === 'ISSUED') ?? null);
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
    if (err instanceof ApiError && err.code === 'HANDOVER_INVALID') {
      const reason = (err.detail as { details?: { reason?: string } } | null)?.details?.reason ?? '';
      return text.errors[reason as keyof typeof text.errors] ?? text.errors.UNKNOWN;
    }
    if (err instanceof ApiError && err.code === 'HANDOVER_NOT_EDITABLE') return text.errors.NOT_EDITABLE;
    return text.errors.UNKNOWN;
  };

  /** One request at a time, in the order of the taps; the answer replaces the screen's copy of the protocol. */
  const save = (changes: HandoverChange, id?: string) => {
    const target = id ?? draft?.id;
    if (!target) return;
    queue.current = queue.current.then(async () => {
      if (!alive.current) return;
      setSaving((n) => n + 1);
      try {
        const next = await updateHandover(projectId, target, changes);
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
        openHandoverDraft(projectId),
        catalog ? Promise.resolve(catalog) : fetchContractCatalog(),
        fetchRepresentatives(projectId),
        fetchRooms(projectId),
      ]);
      if (!alive.current) return;
      setCatalog(loadedCatalog);
      setPeople(representatives.items.filter((p) => !p.is_archived));
      setRooms(roomList.items.map((r) => ({ id: r.id, name: r.name })));
      setDraft(protocol);
      setOpen(true);
      if (!protocol.held_on) save({ held_on: todayIso() }, protocol.id);  // the usual day: today
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
      await previewHandoverPdf(projectId);
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
      await issueHandover(projectId, draft.id);
      if (!alive.current) return;
      setOpen(false);
      setDraft(null);
      setNote(text.issue_note);
      await load();
    } catch (err) {
      if (!alive.current) return;
      const blockers = err instanceof ApiError && err.code === 'HANDOVER_GATE_BLOCKED'
        ? (err.detail as { details?: { blockers?: HandoverBlocker[] } } | null)?.details?.blockers
        : undefined;
      if (blockers && draft) setDraft({ ...draft, blockers });
      else setError(err instanceof ApiError && err.code === 'HANDOVER_NOT_EDITABLE' ? text.errors.NOT_EDITABLE : documentErrorText(t.documents.errors, err));
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
      await abandonHandoverDraft(projectId, draft.id);
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

  // --- the people present ------------------------------------------------------------------------------------------------------
  const presentIds = new Set((draft?.attendees ?? []).map((a) => a.person_id).filter((id): id is string => !!id));
  const strangers = (draft?.attendees ?? []).filter((a) => !a.person_id);
  const sendAttendees = (ids: string[], outsiders: Array<{ name: string; role: string | null }>) =>
    save({ attendees: [...ids.map((person_id) => ({ person_id })), ...outsiders.map((o) => ({ name: o.name, role: o.role }))] });
  const togglePerson = (id: string) =>
    sendAttendees(presentIds.has(id) ? [...presentIds].filter((x) => x !== id) : [...presentIds, id], strangers);
  const addExtra = () => {
    const [name, ...role] = extra.split(',');
    if (!name.trim()) return;
    sendAttendees([...presentIds], [...strangers, { name: name.trim(), role: role.join(',').trim() || null }]);
    setExtra('');
  };
  const removeExtra = (index: number) => sendAttendees([...presentIds], strangers.filter((_, i) => i !== index));

  // --- the rooms ----------------------------------------------------------------------------------------------------------------
  const setState = (roomId: string, key: string, state: RequirementState) =>
    save({ rooms: { [roomId]: { requirements: { [key]: { state } } } } });
  const allMet = (roomId: string) =>
    save({
      rooms: { [roomId]: { requirements: Object.fromEntries(requirements.map((r) => [r.key, { state: 'YES' as RequirementState }])), decision: 'HANDED_OVER' } },
    });
  const setValue = (roomId: string, key: string, value: MeasuredValue | null) =>
    save({ rooms: { [roomId]: { requirements: { [key]: { value } } } } });
  const setRequirementNote = (roomId: string, key: string, value: string) =>
    save({ rooms: { [roomId]: { requirements: { [key]: { note: value.trim() === '' ? null : value } } } } });

  const blockerText = (blocker: HandoverBlocker): string => {
    const sentence = text.gate[blocker.code];
    if (blocker.code === 'REQUIREMENTS_MISSING') {
      return sentence.replace('{rooms}', (blocker.details?.rooms ?? []).map((r) => `${roomName(r.room_id)} (${r.keys.length})`).join(', '));
    }
    if (blocker.code === 'DECISION_MISSING' || blocker.code === 'DECISION_TOO_FAVOURABLE') {
      return sentence.replace('{rooms}', (blocker.details?.room_ids ?? []).map(roomName).join(', '));
    }
    return sentence;
  };

  const renderRequirement = (roomId: string, requirement: PremisesRequirement) => {
    const entry = draft?.rooms[roomId]?.requirements?.[requirement.key] ?? {};
    const required = formatRequired(
      requirement,
      draft?.required_values[requirement.key],
      { yes: t.contract.yes, no: t.contract.no, from: text.range_min, to: text.range_max },
      unitText(requirement.unit),
    );
    const id = `${roomId}-${requirement.key}`;
    const measured = entry.value;
    return (
      <li key={requirement.key} className="space-y-2 border-t border-slate-200 pt-3">
        <p className="text-sm font-medium text-slate-900 break-words">{catalogText.requirements[requirement.key as keyof typeof catalogText.requirements] ?? requirement.key}</p>
        <p className="text-xs text-slate-600 break-words">{required ? text.required_value.replace('{value}', required) : text.required_none}</p>
        <div className="grid grid-cols-2 gap-2">
          {STATES.map((state) => (
            <button
              key={state}
              type="button"
              aria-label={`handover-state-${id}-${state}`}
              aria-pressed={entry.state === state}
              onClick={() => setState(roomId, requirement.key, state)}
              className={`${BUTTON} ${entry.state === state ? STATE_ON[state] : OFF}`}
            >
              {text.state[state]}
            </button>
          ))}
        </div>
        {requirement.value_kind === 'NUMBER' && (
          <label className="block space-y-1">
            <span className="block text-xs text-slate-700">{`${text.found}${unitText(requirement.unit) ? `, ${unitText(requirement.unit)}` : ''}`}</span>
            <CommitText
              label={`handover-value-${id}`}
              inputMode="decimal"
              value={numberText(measured)}
              onCommit={(v) => setValue(roomId, requirement.key, parseNumber(v))}
            />
          </label>
        )}
        {requirement.value_kind === 'NUMBER_RANGE' && (
          <div className="grid grid-cols-2 gap-2">
            {(['min', 'max'] as const).map((side) => (
              <label key={side} className="block space-y-1">
                <span className="block text-xs text-slate-700">{`${side === 'min' ? text.range_min : text.range_max}${unitText(requirement.unit) ? ` (${unitText(requirement.unit)})` : ''}`}</span>
                <CommitText
                  label={`handover-value-${id}-${side}`}
                  inputMode="decimal"
                  value={numberText(measured && typeof measured === 'object' ? measured[side] : undefined)}
                  onCommit={(v) => {
                    const otherSide = side === 'min' ? 'max' : 'min';
                    const saved = measured && typeof measured === 'object' ? measured : null;
                    rangeTexts.current[`${id}-${side}`] = v;
                    const own = parseNumber(v);
                    const other = parseNumber(rangeTexts.current[`${id}-${otherSide}`] ?? numberText(saved ? saved[otherSide] : undefined));
                    if (own === null && other === null) setValue(roomId, requirement.key, null);
                    else if (own !== null && other !== null) {
                      delete rangeTexts.current[`${id}-min`];
                      delete rangeTexts.current[`${id}-max`];
                      setValue(roomId, requirement.key, side === 'min' ? { min: own, max: other } : { min: other, max: own });
                    }
                  }}
                />
              </label>
            ))}
          </div>
        )}
        {(entry.state === 'NO' || entry.state === 'CONDITIONAL' || entry.note) && (
          <label className="block space-y-1">
            <span className="block text-xs text-slate-700">{text.note}</span>
            <CommitText label={`handover-note-${id}`} value={entry.note ?? ''} onCommit={(v) => setRequirementNote(roomId, requirement.key, v)} />
          </label>
        )}
      </li>
    );
  };

  const renderRoom = (room: { id: string; name: string }) => {
    const entry = draft?.rooms[room.id];
    const answered = requirements.filter((r) => entry?.requirements?.[r.key]?.state).length;
    const suggested = draft?.suggested[room.id] ?? null;
    const expanded = openRoom === room.id;
    return (
      <li key={room.id} className="border border-slate-200 rounded-xl p-3 space-y-3">
        <button
          type="button"
          aria-label={`handover-room-${room.id}`}
          aria-expanded={expanded}
          onClick={() => setOpenRoom(expanded ? null : room.id)}
          className="w-full min-h-11 text-left flex items-center justify-between gap-3"
        >
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-slate-900 break-words">{room.name}</span>
            <span className="block text-xs text-slate-600 break-words">
              {text.room_progress.replace('{done}', String(answered)).replace('{total}', String(requirements.length))}
              {entry?.decision ? ` · ${text.decision[entry.decision]}` : ''}
            </span>
          </span>
          <span className="shrink-0 text-xs font-semibold text-blue-700">{expanded ? text.room_close : text.room_open}</span>
        </button>
        {expanded && (
          <div className="space-y-3">
            <button type="button" aria-label={`handover-all-met-${room.id}`} onClick={() => allMet(room.id)} className={`w-full ${BUTTON} bg-emerald-700 text-white border-emerald-700 hover:bg-emerald-800`}>
              {text.all_met}
            </button>
            <ul className="space-y-3">{requirements.map((r) => renderRequirement(room.id, r))}</ul>
            <label className="block space-y-1 border-t border-slate-200 pt-3">
              <span className="block text-sm font-medium text-slate-900 break-words">{text.damages}</span>
              <CommitText label={`handover-damages-${room.id}`} multiline value={entry?.damages ?? ''} onCommit={(v) => save({ rooms: { [room.id]: { damages: v.trim() === '' ? null : v } } })} />
            </label>
            <div className="space-y-2 border-t border-slate-200 pt-3">
              <p className="text-sm font-medium text-slate-900">{text.decision_title}</p>
              <p className="text-xs text-slate-600 break-words">
                {suggested ? text.suggested.replace('{decision}', text.decision[suggested]) : text.suggested_unknown}
              </p>
              <div className="grid grid-cols-1 gap-2">
                {DECISIONS.map((decision) => {
                  const locked = decision === 'HANDED_OVER' && suggested !== 'HANDED_OVER';
                  return (
                    <button
                      key={decision}
                      type="button"
                      aria-label={`handover-decision-${room.id}-${decision}`}
                      aria-pressed={entry?.decision === decision}
                      disabled={locked}
                      onClick={() => save({ rooms: { [room.id]: { decision } } })}
                      className={`${BUTTON} ${entry?.decision === decision ? 'bg-slate-900 text-white border-slate-900' : OFF}`}
                    >
                      {text.decision[decision]}
                    </button>
                  );
                })}
              </div>
              {suggested !== 'HANDED_OVER' && <p className="text-xs text-slate-600 break-words">{text.handed_over_locked}</p>}
            </div>
          </div>
        )}
      </li>
    );
  };

  return (
    <article aria-label="project-handover" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
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
          <button type="button" aria-label="start-handover" disabled={busy} onClick={() => void start()} className={`w-full ${BUTTON} text-white bg-blue-600 border-blue-600 hover:bg-blue-700`}>
            {busy ? text.loading : draft ? text.continue : latest ? text.new : text.start}
          </button>
          <button type="button" aria-label="preview-handover" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>
            {text.preview}
          </button>
        </>
      )}

      {open && draft && catalog && (
        <div aria-label="handover-form" className="space-y-4">
          <div className="grid grid-cols-1 gap-3">
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_on}</span>
              <input type="date" aria-label="handover-held-on" value={draft.held_on ?? ''} onChange={(e) => save({ held_on: e.target.value || null })} className={FIELD} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_time}</span>
              <CommitText label="handover-held-time" type="time" value={draft.held_time ?? ''} onCommit={(v) => save({ held_time: v || null })} />
            </label>
          </div>

          <fieldset className="space-y-1">
            <legend className="text-sm font-semibold text-slate-900">{text.attendees}</legend>
            {people.length === 0 && <p className="text-xs text-slate-600 break-words">{text.attendees_none}</p>}
            {people.map((person) => (
              <label key={person.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                <input type="checkbox" aria-label={`handover-person-${person.id}`} className="h-5 w-5 shrink-0" checked={presentIds.has(person.id)} onChange={() => togglePerson(person.id)} />
                <span className="min-w-0 break-words">{person.name}{person.role_title ? ` · ${person.role_title}` : ''}</span>
              </label>
            ))}
            {strangers.map((a, index) => (
              <div key={`${a.name}-${index}`} className="flex items-center justify-between gap-3 min-h-11 text-sm text-slate-900">
                <span className="min-w-0 break-words">{a.name}{a.role ? ` · ${a.role}` : ''}</span>
                <button type="button" aria-label={`handover-extra-remove-${index}`} onClick={() => removeExtra(index)} className={`shrink-0 ${BUTTON} text-red-800 bg-white border-red-300`}>{text.extra_remove}</button>
              </div>
            ))}
            <label className="block space-y-1 pt-1">
              <span className="block text-xs text-slate-700 break-words">{text.extra_label}</span>
              <input aria-label="handover-extra" value={extra} onChange={(e) => setExtra(e.target.value)} className={FIELD} />
            </label>
            <button type="button" aria-label="handover-extra-add" disabled={!extra.trim()} onClick={addExtra} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300`}>{text.extra_add}</button>
          </fieldset>

          <section className="space-y-2">
            <h4 className="text-sm font-semibold text-slate-900">{text.rooms_title}</h4>
            {rooms.length === 0 ? <p className="text-xs text-slate-600 break-words">{text.rooms_none}</p> : <ul className="space-y-3">{rooms.map(renderRoom)}</ul>}
          </section>

          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900">{text.meters}</span>
            <CommitText label="handover-meters" multiline value={draft.meters ?? ''} onCommit={(v) => save({ meters: v.trim() === '' ? null : v })} />
          </label>
          <label className="block space-y-1">
            <span className="block text-sm font-medium text-slate-900">{text.notes}</span>
            <CommitText label="handover-notes" multiline value={draft.notes ?? ''} onCommit={(v) => save({ notes: v.trim() === '' ? null : v })} />
          </label>

          <section aria-label="handover-gate" className="space-y-2 border-t border-slate-200 pt-3">
            <h4 className="text-sm font-semibold text-slate-900 break-words">{text.gate_title}</h4>
            {draft.blockers.length === 0 ? (
              <p className="text-sm text-emerald-800 break-words">{text.gate_ready}</p>
            ) : (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-red-700 break-words">{text.gate_blocked}</p>
                <ul className="space-y-2">
                  {draft.blockers.map((blocker) => (
                    <li key={blocker.code} aria-label={`gate-${blocker.code}`} className="text-xs text-slate-800 break-words bg-red-50 border border-red-200 rounded-xl px-3 py-2">
                      {blockerText(blocker)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {saving > 0 && <p role="status" aria-label="handover-saving" className="text-xs text-slate-600">{text.saving}</p>}
          {error && <p role="alert" aria-label="handover-error" className="text-sm text-red-700 break-words">{error}</p>}
          {note && <p role="status" aria-label="handover-note" className="text-sm text-emerald-800 break-words">{note}</p>}
          <button type="button" aria-label="preview-handover" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>{text.preview}</button>
          <button type="button" aria-label="issue-handover" disabled={busy || draft.blockers.length > 0} onClick={() => void issue()} className={`w-full ${BUTTON} text-white bg-sky-700 border-sky-700 hover:bg-sky-800`}>{text.issue}</button>
          <button type="button" aria-label="close-handover-form" disabled={busy} onClick={() => setOpen(false)} className={`w-full ${BUTTON} text-slate-800 bg-white border-slate-300 hover:bg-slate-100`}>{text.close}</button>
          <button type="button" aria-label="abandon-handover-draft" disabled={busy} onClick={() => void abandon()} className={`w-full ${BUTTON} text-red-800 bg-white border-red-300 hover:bg-red-50`}>{confirmAbandon ? text.abandon_confirm : text.abandon}</button>
        </div>
      )}

      {!open && error && <p role="alert" aria-label="handover-error" className="text-sm text-red-700 break-words">{error}</p>}
      {!open && note && <p role="status" aria-label="handover-note" className="text-sm text-emerald-800 break-words">{note}</p>}
    </article>
  );
}
