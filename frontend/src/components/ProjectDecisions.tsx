import { useCallback, useEffect, useRef, useState } from 'react';
import { abandonDecisionDraft, fetchDecisions, issueDecision, openDecisionDraft, updateDecision } from '../api/decisions';
import { previewDecisionPdf } from '../api/documents';
import { ApiError } from '../api/http';
import { fetchRepresentatives } from '../api/representatives';
import { useI18n } from '../hooks/useI18n';
import type { Decision, DecisionBlocker, DecisionChange, DecisionChoice, DecisionItem, ExecutorAction, RiskSeverity } from '../types/decision';
import type { ProjectRepresentative } from '../types/representative';
import { documentErrorText } from '../utils/documentErrors';
import { newId } from '../utils/newId';
import { CommitText, FIELD } from './CommitText';

interface ProjectDecisionsProps {
  projectId: string;
}

const BUTTON = 'min-h-11 px-3 text-sm font-semibold rounded-xl border transition disabled:opacity-60 break-words';
const OFF = 'bg-white text-slate-900 border-slate-300 hover:bg-slate-50';
const ON = 'bg-slate-900 text-white border-slate-900';
const CHOICES: DecisionChoice[] = ['ACCEPTED', 'DECLINED', 'INSISTS'];
const ACTIONS: ExecutorAction[] = ['PERFORM', 'REFUSE'];
const SEVERITY: Record<RiskSeverity, 'severity_low' | 'severity_medium' | 'severity_high' | 'severity_critical'> = {
  LOW: 'severity_low', MEDIUM: 'severity_medium', HIGH: 'severity_high', CRITICAL: 'severity_critical',
};

interface OwnForm {
  title: string;
  recommendation: string;
  consequence: string;
  price: string;
  roomId: string;
}
const EMPTY_FORM: OwnForm = { title: '', recommendation: '', consequence: '', price: '', roomId: '' };

function nowParts(): { day: string; time: string } {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return { day: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`, time: `${pad(now.getHours())}:${pad(now.getMinutes())}` };
}

/**
 * Stage 16I.2 — the protocol of information and decisions of the customer, on the phone. When the customer gives up a recommendation or
 * demands the work against it, the owner writes it down on the spot: adds the risk the application found (one tap) or a recommendation
 * of his own, taps the customer's decision on each item — and, when the customer insists, his own answer —, ticks who was present and
 * the customer's declaration (or the refusal to sign). The words of a risk are the server's catalogue's and are only shown. Every tap is
 * saved at once (one request at a time, in order); the server answers with the whole protocol and what is still missing.
 */
export function ProjectDecisions({ projectId }: ProjectDecisionsProps) {
  const { t } = useI18n();
  const text = t.decisions;
  const [draft, setDraft] = useState<Decision | null>(null);
  const [latest, setLatest] = useState<Decision | null>(null);
  const [people, setPeople] = useState<ProjectRepresentative[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [extra, setExtra] = useState('');
  const [form, setForm] = useState<OwnForm | null>(null);
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
      const list = await fetchDecisions(projectId);
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
    if (err instanceof ApiError && err.code === 'DECISION_INVALID') {
      const reason = (err.detail as { details?: { reason?: string } } | null)?.details?.reason ?? '';
      return text.errors[reason as keyof typeof text.errors] ?? text.errors.UNKNOWN;
    }
    if (err instanceof ApiError && err.code === 'DECISION_NOT_EDITABLE') return text.errors.NOT_EDITABLE;
    return text.errors.UNKNOWN;
  };

  /** One request at a time, in the order of the taps; the answer replaces the screen's copy of the protocol. */
  const save = (changes: DecisionChange, id?: string) => {
    const target = id ?? draft?.id;
    if (!target) return;
    queue.current = queue.current.then(async () => {
      if (!alive.current) return;
      setSaving((n) => n + 1);
      try {
        const next = await updateDecision(projectId, target, changes);
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
      const [protocol, representatives] = await Promise.all([openDecisionDraft(projectId), fetchRepresentatives(projectId)]);
      if (!alive.current) return;
      setPeople(representatives.items.filter((p) => !p.is_archived));
      setDraft(protocol);
      setOpen(true);
      setForm(null);
      const { day, time } = nowParts();  // the usual day and hour: now
      const defaults: DecisionChange = {};
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
      await previewDecisionPdf(projectId);
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
      await issueDecision(projectId, draft.id);
      if (!alive.current) return;
      setOpen(false);
      setDraft(null);
      setForm(null);
      setNote(text.issue_note);
      await load();
    } catch (err) {
      if (!alive.current) return;
      const blockers = err instanceof ApiError && err.code === 'DECISION_GATE_BLOCKED'
        ? (err.detail as { details?: { blockers?: DecisionBlocker[] } } | null)?.details?.blockers
        : undefined;
      if (blockers && draft) setDraft({ ...draft, blockers });
      else setError(err instanceof ApiError && err.code === 'DECISION_NOT_EDITABLE' ? text.errors.NOT_EDITABLE : documentErrorText(t.documents.errors, err));
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
      await abandonDecisionDraft(projectId, draft.id);
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

  // --- the people present ------------------------------------------------------------------------------------------------------
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

  // --- the items ---------------------------------------------------------------------------------------------------------------
  const addRisk = (riskId: string) => save({ items: { [newId()]: { risk_id: riskId } } });
  const decide = (item: DecisionItem, decision: DecisionChoice) => save({ items: { [item.id]: { decision } } });
  const answer = (item: DecisionItem, executor_action: ExecutorAction) => save({ items: { [item.id]: { executor_action } } });
  const removeItem = (item: DecisionItem) => {
    if (confirmRemove !== item.id) {
      setConfirmRemove(item.id);
      return;
    }
    setConfirmRemove(null);
    save({ items: { [item.id]: null } });
  };
  const formReady = (f: OwnForm) => f.title.trim() !== '' && f.recommendation.trim() !== '' && f.consequence.trim() !== '';
  const saveOwn = () => {
    if (!form || !formReady(form)) return;
    save({
      items: {
        [newId()]: {
          title: form.title.trim(), recommendation: form.recommendation.trim(), consequence: form.consequence.trim(),
          ...(form.price.trim() ? { price: form.price.trim() } : {}), ...(form.roomId ? { room_id: form.roomId } : {}),
        },
      },
    });
    setForm(null);
  };
  const options = draft?.risk_options.filter((o) => !o.used) ?? [];

  return (
    <article aria-label="project-decisions" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
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
          <button type="button" aria-label="start-decision" disabled={busy} onClick={() => void start()} className={`w-full ${BUTTON} text-white bg-blue-600 border-blue-600 hover:bg-blue-700`}>
            {busy ? text.loading : draft ? text.continue : latest ? text.new : text.start}
          </button>
          <button type="button" aria-label="preview-decision" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>{text.preview}</button>
        </>
      )}

      {open && draft && (
        <div aria-label="decision-form" className="space-y-4">
          <div className="grid grid-cols-1 gap-3">
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_on}</span>
              <input type="date" aria-label="decision-held-on" value={draft.held_on ?? ''} onChange={(e) => save({ held_on: e.target.value || null })} className={FIELD} />
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.held_time}</span>
              <CommitText label="decision-held-time" type="time" value={draft.held_time ?? ''} onCommit={(v) => save({ held_time: v || null })} />
            </label>
          </div>

          <fieldset className="space-y-1">
            <legend className="text-sm font-semibold text-slate-900">{text.attendees}</legend>
            {people.length === 0 && <p className="text-xs text-slate-600 break-words">{text.attendees_none}</p>}
            {people.map((person) => (
              <label key={person.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                <input type="checkbox" aria-label={`decision-person-${person.id}`} className="h-5 w-5 shrink-0" checked={presentIds.has(person.id)} onChange={() => togglePerson(person.id)} />
                <span className="min-w-0 break-words">{person.name}{person.role_title ? ` · ${person.role_title}` : ''}</span>
              </label>
            ))}
            {strangers.map((a, index) => (
              <div key={`${a.name}-${index}`} className="flex items-center justify-between gap-3 min-h-11 text-sm text-slate-900">
                <span className="min-w-0 break-words">{a.name}{a.role ? ` · ${a.role}` : ''}</span>
                <button type="button" aria-label={`decision-extra-remove-${index}`} onClick={() => removeExtra(index)} className={`shrink-0 ${BUTTON} text-red-800 bg-white border-red-300`}>{text.extra_remove}</button>
              </div>
            ))}
            <label className="block space-y-1 pt-1">
              <span className="block text-xs text-slate-700 break-words">{text.extra_label}</span>
              <input aria-label="decision-extra" value={extra} onChange={(e) => setExtra(e.target.value)} className={FIELD} />
            </label>
            <button type="button" aria-label="decision-extra-add" disabled={!extra.trim()} onClick={addExtra} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300`}>{text.extra_add}</button>
          </fieldset>

          <section aria-label="decision-items" className="space-y-3">
            <h4 className="text-sm font-semibold text-slate-900">{text.items}</h4>
            {draft.items.length === 0 && <p className="text-xs text-slate-600 break-words">{text.items_none}</p>}
            {draft.items.map((item) => (
              <div key={item.id} aria-label={`decision-item-${item.id}`} className="border border-slate-200 rounded-xl p-3 space-y-2">
                <p className="text-sm font-semibold text-slate-900 break-words">
                  {item.title}
                  {(item.room_name || item.severity) && (
                    <span className="font-normal text-slate-600"> · {[item.room_name, item.severity ? t.risk[SEVERITY[item.severity]] : null].filter(Boolean).join(' · ')}</span>
                  )}
                </p>
                {!item.risk_active && <p className="text-xs font-semibold text-red-700 break-words">{text.risk_gone}</p>}
                {item.blocks_finishing && <p className="text-xs text-amber-800 break-words">{text.item_blocks}</p>}
                {item.state && <p className="text-xs text-slate-700 break-words"><span className="font-semibold">{text.item_state}:</span> {item.state}</p>}
                <p className="text-xs text-slate-700 break-words"><span className="font-semibold">{text.item_recommendation}:</span> {item.recommendation}</p>
                {item.price && <p className="text-xs text-slate-700 break-words">{text.item_price.replace('{price}', item.price)}</p>}
                <p className="text-xs text-slate-700 break-words"><span className="font-semibold">{text.item_consequence}:</span> {item.consequence}</p>

                <p className="text-sm font-semibold text-slate-900">{text.decision}</p>
                <div className="grid grid-cols-1 gap-2">
                  {CHOICES.map((choice) => (
                    <button key={choice} type="button" aria-label={`decision-choice-${item.id}-${choice}`} aria-pressed={item.decision === choice} onClick={() => decide(item, choice)} className={`${BUTTON} ${item.decision === choice ? ON : OFF}`}>
                      {text.decision_options[choice]}
                    </button>
                  ))}
                </div>
                {item.decision === 'ACCEPTED' && (
                  <label className="block space-y-1">
                    <span className="block text-sm font-medium text-slate-900">{text.order_ref}</span>
                    <CommitText label={`decision-order-${item.id}`} value={item.order_ref ?? ''} onCommit={(v) => save({ items: { [item.id]: { order_ref: v.trim() === '' ? null : v } } })} />
                  </label>
                )}
                {item.decision === 'INSISTS' && (
                  <div className="space-y-2">
                    <p className="text-sm font-semibold text-slate-900">{text.action}</p>
                    <div className="grid grid-cols-1 gap-2">
                      {ACTIONS.map((action) => (
                        <button key={action} type="button" aria-label={`decision-action-${item.id}-${action}`} aria-pressed={item.executor_action === action} onClick={() => answer(item, action)} className={`${BUTTON} ${item.executor_action === action ? ON : OFF}`}>
                          {text.action_options[action]}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <label className="block space-y-1">
                  <span className="block text-sm font-medium text-slate-900">{text.note}</span>
                  <CommitText label={`decision-note-${item.id}`} multiline value={item.note ?? ''} onCommit={(v) => save({ items: { [item.id]: { note: v.trim() === '' ? null : v } } })} />
                </label>
                <button type="button" aria-label={`decision-item-remove-${item.id}`} onClick={() => removeItem(item)} className={`w-full ${BUTTON} text-red-800 bg-white border-red-300 hover:bg-red-50`}>
                  {confirmRemove === item.id ? text.remove_confirm : text.remove_item}
                </button>
              </div>
            ))}

            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-900">{text.add_risk}</p>
              {options.length === 0 && <p className="text-xs text-slate-600 break-words">{text.add_risk_none}</p>}
              {options.map((option) => (
                <button key={option.id} type="button" aria-label={`decision-add-risk-${option.id}`} onClick={() => addRisk(option.id)} className={`w-full text-left ${BUTTON} ${OFF}`}>
                  {text.risk_row.replace('{title}', option.title).replace('{room}', option.room_name).replace('{severity}', t.risk[SEVERITY[option.severity]])}
                </button>
              ))}
            </div>

            {form ? (
              <div aria-label="decision-own-form" className="space-y-3 border border-slate-300 rounded-xl p-3">
                <label className="block space-y-1">
                  <span className="block text-sm font-medium text-slate-900">{text.own_title}</span>
                  <input aria-label="decision-own-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className={FIELD} />
                </label>
                <label className="block space-y-1">
                  <span className="block text-sm font-medium text-slate-900">{text.own_recommendation}</span>
                  <textarea aria-label="decision-own-recommendation" rows={2} value={form.recommendation} onChange={(e) => setForm({ ...form, recommendation: e.target.value })} className={FIELD} />
                </label>
                <label className="block space-y-1">
                  <span className="block text-sm font-medium text-slate-900">{text.own_consequence}</span>
                  <textarea aria-label="decision-own-consequence" rows={2} value={form.consequence} onChange={(e) => setForm({ ...form, consequence: e.target.value })} className={FIELD} />
                </label>
                <label className="block space-y-1">
                  <span className="block text-sm font-medium text-slate-900">{text.own_price}</span>
                  <input aria-label="decision-own-price" inputMode="decimal" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className={FIELD} />
                </label>
                <label className="block space-y-1">
                  <span className="block text-sm font-medium text-slate-900">{text.own_room}</span>
                  <select aria-label="decision-own-room" value={form.roomId} onChange={(e) => setForm({ ...form, roomId: e.target.value })} className={FIELD}>
                    <option value="">{text.own_room_none}</option>
                    {draft.rooms.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
                  </select>
                </label>
                <button type="button" aria-label="decision-own-save" disabled={!formReady(form)} onClick={saveOwn} className={`w-full ${BUTTON} text-white bg-blue-600 border-blue-600 hover:bg-blue-700`}>{text.own_save}</button>
                <button type="button" aria-label="decision-own-cancel" onClick={() => setForm(null)} className={`w-full ${BUTTON} text-slate-800 bg-white border-slate-300 hover:bg-slate-100`}>{text.own_cancel}</button>
              </div>
            ) : (
              <button type="button" aria-label="decision-own-open" onClick={() => setForm({ ...EMPTY_FORM })} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>{text.add_own}</button>
            )}
          </section>

          <section aria-label="decision-declaration" className="space-y-1">
            <label className="flex items-start gap-3 min-h-11 text-sm text-slate-900">
              <input type="checkbox" aria-label="decision-understood" className="mt-1 h-5 w-5 shrink-0" checked={draft.understood} onChange={() => save({ understood: !draft.understood })} />
              <span className="min-w-0 break-words">{text.declaration}</span>
            </label>
            <label className="flex items-start gap-3 min-h-11 text-sm text-slate-900">
              <input type="checkbox" aria-label="decision-refused" className="mt-1 h-5 w-5 shrink-0" checked={draft.signature_refused} onChange={() => save({ signature_refused: !draft.signature_refused })} />
              <span className="min-w-0">
                <span className="block break-words">{text.refusal}</span>
                {draft.signature_refused && <span className="block text-xs text-amber-800 break-words">{text.refusal_hint}</span>}
              </span>
            </label>
            <label className="block space-y-1">
              <span className="block text-sm font-medium text-slate-900">{text.notes}</span>
              <CommitText label="decision-notes" multiline value={draft.notes ?? ''} onCommit={(v) => save({ notes: v.trim() === '' ? null : v })} />
            </label>
          </section>

          <section aria-label="decision-gate" className="space-y-2 border-t border-slate-200 pt-3">
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

          {saving > 0 && <p role="status" aria-label="decision-saving" className="text-xs text-slate-600">{text.saving}</p>}
          {error && <p role="alert" aria-label="decision-error" className="text-sm text-red-700 break-words">{error}</p>}
          {note && <p role="status" aria-label="decision-note-message" className="text-sm text-emerald-800 break-words">{note}</p>}
          <button type="button" aria-label="preview-decision" disabled={busy} onClick={() => void preview()} className={`w-full ${BUTTON} text-slate-900 bg-slate-100 border-slate-300 hover:bg-slate-200`}>{text.preview}</button>
          <button type="button" aria-label="issue-decision" disabled={busy || draft.blockers.length > 0} onClick={() => void issue()} className={`w-full ${BUTTON} text-white bg-sky-700 border-sky-700 hover:bg-sky-800`}>{text.issue}</button>
          <button type="button" aria-label="close-decision-form" disabled={busy} onClick={() => setOpen(false)} className={`w-full ${BUTTON} text-slate-800 bg-white border-slate-300 hover:bg-slate-100`}>{text.close}</button>
          <button type="button" aria-label="abandon-decision-draft" disabled={busy} onClick={() => void abandon()} className={`w-full ${BUTTON} text-red-800 bg-white border-red-300 hover:bg-red-50`}>{confirmAbandon ? text.abandon_confirm : text.abandon}</button>
        </div>
      )}

      {!open && error && <p role="alert" aria-label="decision-error" className="text-sm text-red-700 break-words">{error}</p>}
      {!open && note && <p role="status" aria-label="decision-note-message" className="text-sm text-emerald-800 break-words">{note}</p>}
    </article>
  );
}
