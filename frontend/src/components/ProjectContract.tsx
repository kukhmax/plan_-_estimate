import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchContractCatalog } from '../api/contractCatalog';
import { abandonContractDraft, closeContract, fetchContractGate, fetchContracts, issueContract, openContractDraft, prefillContract, saveContractAnswers, signContract } from '../api/contracts';
import { previewContractPdf } from '../api/documents';
import { ApiError } from '../api/http';
import { documentErrorText } from '../utils/documentErrors';
import { fetchRepresentatives } from '../api/representatives';
import { useI18n } from '../hooks/useI18n';
import type { Contract, ContractAnswersChange, ContractGate, ContractPrefill, GateBlocker } from '../types/contract';
import type { ContractCatalog, ContractQuestion, PremisesRequirement, QuestionGroup } from '../types/contractCatalog';
import type { ProjectRepresentative } from '../types/representative';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';
import { FieldValue, sameAnswer, toAnswer, toField } from '../utils/contractAnswers';
import { ContractQuestionInput } from './ContractQuestionInput';
import { Ico } from './Ico';

interface ProjectContractProps {
  projectId: string;
}

const FIELD = 'w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-base pe-surface text-slate-900';

function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * Stage 16E.1 — "Compose the contract": the questionnaire the owner answers before the contract (16E.2) is made. The questions,
 * their kinds, which are required and the only two defaults come from the server's catalogue; this screen only draws them. An
 * OPEN question may stay empty — the document then prints a line to write in by hand. The draft is saved on demand, only what
 * changed is sent, and a refused answer is named by its question.
 */
export function ProjectContract({ projectId }: ProjectContractProps) {
  const { t } = useI18n();
  const text = t.contract;
  const catalogText = t.contractCatalog;
  const [draft, setDraft] = useState<Contract | null>(null);
  const [latest, setLatest] = useState<Contract | null>(null);
  const [catalog, setCatalog] = useState<ContractCatalog | null>(null);
  const [people, setPeople] = useState<ProjectRepresentative[]>([]);
  const [fields, setFields] = useState<Record<string, FieldValue>>({});
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [signedOn, setSignedOn] = useState(todayIso);
  const [confirmSign, setConfirmSign] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [gate, setGate] = useState<ContractGate | null>(null);
  const [gateFailed, setGateFailed] = useState(false);
  // B2: the questions filled by "Uzupełnij puste pola" in this visit, marked until the owner changes them
  const [prefilled, setPrefilled] = useState<Set<string>>(new Set());
  const [prefillNote, setPrefillNote] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const requirements: PremisesRequirement[] = useMemo(() => catalog?.requirements.items ?? [], [catalog]);

  const fill = useCallback(
    (contract: Contract, source: ContractCatalog) => {
      const next: Record<string, FieldValue> = {};
      for (const question of source.questionnaire.items) {
        next[question.key] = toField(question, contract.effective_answers[question.key], source.requirements.items);
      }
      setFields(next);
    },
    [],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const list = await fetchContracts(projectId);
      if (!alive.current) return;
      setDraft(list.items.find((c) => c.status === 'DRAFT') ?? null);
      setLatest(list.items.find((c) => c.status !== 'DRAFT' && c.status !== 'ARCHIVED') ?? null);
    } catch {
      if (alive.current) setLoadFailed(true);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadGate = useCallback(
    async (contractId: string) => {
      setGateFailed(false);
      try {
        const result = await fetchContractGate(projectId, contractId);
        if (alive.current) setGate(result);
      } catch {
        if (alive.current) setGateFailed(true);
      }
    },
    [projectId],
  );

  const start = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const [contract, loadedCatalog, representatives] = await Promise.all([
        openContractDraft(projectId),
        catalog ? Promise.resolve(catalog) : fetchContractCatalog(),
        fetchRepresentatives(projectId),
      ]);
      if (!alive.current) return;
      setCatalog(loadedCatalog);
      setPeople(representatives.items.filter((p) => !p.is_archived));
      setDraft(contract);
      fill(contract, loadedCatalog);
      setOpen(true);
      setPrefilled(new Set());
      setPrefillNote(null);
      // B2: a draft nobody has answered yet is filled at once with what is known (the owner sees and changes every field)
      if (Object.keys(contract.answers ?? {}).length === 0) {
        try {
          applyPrefill(await prefillContract(projectId, contract.id), loadedCatalog);
          const again = await fetchRepresentatives(projectId); // the client may have just become the person who accepts
          if (alive.current) setPeople(again.items.filter((p) => !p.is_archived));
        } catch {
          // the questionnaire stays as it was: "Uzupełnij puste pola" tries again
        }
      }
      void loadGate(contract.id);
    } catch {
      if (alive.current) setError(text.load_failed);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const questions: ContractQuestion[] = catalog?.questionnaire.items ?? [];

  const applyPrefill = (result: ContractPrefill, source: ContractCatalog) => {
    if (!alive.current) return;
    setDraft(result.contract);
    fill(result.contract, source);
    setPrefilled(new Set(result.filled));
    if (result.filled.length === 0) {
      setPrefillNote(text.prefill_nothing);
      return;
    }
    const parts = [text.prefill_done.replace('{n}', String(result.filled.length))];
    if (result.terms_from_profile) parts.push(text.prefill_terms_profile);
    if (result.terms_from) parts.push(text.prefill_terms_from.replace('{name}', result.terms_from));
    parts.push(text.prefill_check);
    setPrefillNote(parts.join(' '));
  };

  const changes = (): ContractAnswersChange => {
    const result: ContractAnswersChange = {};
    if (!draft) return result;
    for (const question of questions) {
      const answer = toAnswer(question, fields[question.key] ?? '', requirements);
      if (!sameAnswer(answer, draft.effective_answers[question.key] ?? null)) result[question.key] = answer;
    }
    return result;
  };

  const save = async () => {
    if (!draft || busy) return;
    const diff = changes();
    if (Object.keys(diff).length === 0) {
      setNote(text.nothing_to_save);
      return;
    }
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const saved = await saveContractAnswers(projectId, draft.id, diff);
      if (!alive.current || !catalog) return;
      setDraft(saved);
      fill(saved, catalog);
      setNote(text.saved);
      void loadGate(saved.id);
    } catch (err) {
      if (!alive.current) return;
      if (err instanceof ApiError && err.code === 'CONTRACT_ANSWER_INVALID') {
        const details = (err.detail as { details?: { key?: string; reason?: string } } | null)?.details;
        const label = details?.key ? catalogText.questions[details.key as keyof typeof catalogText.questions] ?? details.key : '';
        const reason = text.errors[(details?.reason ?? '') as keyof typeof text.errors] ?? text.errors.UNKNOWN;
        setError(`${label}: ${reason}`);
      } else if (err instanceof ApiError && err.code === 'CONTRACT_NOT_EDITABLE') {
        setError(text.errors.NOT_EDITABLE);
      } else {
        setError(text.errors.UNKNOWN);
      }
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const prefillNow = async () => {
    if (!draft || !catalog || busy) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const diff = changes();
      if (Object.keys(diff).length > 0) await saveContractAnswers(projectId, draft.id, diff); // what is typed is kept, then the rest is filled
      applyPrefill(await prefillContract(projectId, draft.id), catalog);
      const again = await fetchRepresentatives(projectId);
      if (alive.current) setPeople(again.items.filter((p) => !p.is_archived));
      void loadGate(draft.id);
    } catch (err) {
      if (!alive.current) return;
      if (err instanceof ApiError && err.code === 'CONTRACT_ANSWER_INVALID') {
        const details = (err.detail as { details?: { key?: string; reason?: string } } | null)?.details;
        const label = details?.key ? catalogText.questions[details.key as keyof typeof catalogText.questions] ?? details.key : '';
        setError(`${label}: ${text.errors[(details?.reason ?? '') as keyof typeof text.errors] ?? text.errors.UNKNOWN}`);
      } else {
        setError(err instanceof ApiError && err.code === 'CONTRACT_NOT_EDITABLE' ? text.errors.NOT_EDITABLE : text.errors.UNKNOWN);
      }
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
      await previewContractPdf(projectId);
      if (alive.current) setNote(text.preview_ok);
    } catch (err) {
      if (alive.current) setError(documentErrorText(t.documents.errors, err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const issue = async () => {
    if (!draft || busy || !gate?.ready) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await issueContract(projectId, draft.id);
      if (!alive.current) return;
      setOpen(false);
      setDraft(null);
      setGate(null);
      setNote(text.issue_note);
      await load();
    } catch (err) {
      if (!alive.current) return;
      const blockers = err instanceof ApiError && err.code === 'CONTRACT_GATE_BLOCKED'
        ? (err.detail as { details?: { blockers?: GateBlocker[] } } | null)?.details?.blockers
        : undefined;
      if (blockers) setGate({ ready: false, blockers });
      else setError(err instanceof ApiError && err.code === 'CONTRACT_NOT_EDITABLE' ? text.errors.NOT_EDITABLE : documentErrorText(t.documents.errors, err));
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
      await abandonContractDraft(projectId, draft.id);
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

  const sign = async () => {
    if (!latest || latest.status !== 'ISSUED' || busy || !signedOn) return;
    if (!confirmSign) {
      setConfirmSign(true);
      return;
    }
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await signContract(projectId, latest.id, signedOn);
      if (!alive.current) return;
      setConfirmSign(false);
      setNote(text.signed_note);
      await load();
    } catch (err) {
      if (!alive.current) return;
      setConfirmSign(false);
      const reason = err instanceof ApiError && err.code === 'CONTRACT_SIGN_REFUSED'
        ? (err.detail as { details?: { reason?: string } } | null)?.details?.reason
        : undefined;
      setError(text.sign_errors[(reason ?? 'UNKNOWN') as keyof typeof text.sign_errors] ?? text.sign_errors.UNKNOWN);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const closeLatest = async () => {
    if (!latest || busy) return;
    if (!confirmClose) {
      setConfirmClose(true);
      return;
    }
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await closeContract(projectId, latest.id);
      if (!alive.current) return;
      setConfirmClose(false);
      setNote(text.closed_note);
      await load();
    } catch {
      if (alive.current) {
        setConfirmClose(false);
        setError(text.sign_errors.UNKNOWN);
      }
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const setField = (key: string, value: FieldValue) => {
    setFields((current) => ({ ...current, [key]: value }));
    setPrefilled((current) => {
      if (!current.has(key)) return current;
      const next = new Set(current);
      next.delete(key);
      return next;
    });
  };

  const groups: QuestionGroup[] = [];
  for (const question of questions) if (!groups.includes(question.group)) groups.push(question.group);

  const requiredTotal = questions.filter((q) => q.requirement === 'REQUIRED').length;
  const requiredDone = draft ? requiredTotal - draft.missing_required.length : 0;
  const questionLabel = (key: string) => catalogText.questions[key as keyof typeof catalogText.questions] ?? key;
  const authorised = people.filter((p) => p.may_accept_and_sign);

  const surfaceLabels = { wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling };
  const blockerText = (blocker: GateBlocker): string => {
    const sentence = text.gate[blocker.code];
    const details = blocker.details;
    if (blocker.code === 'CLIENT_ADDRESS_INCOMPLETE') {
      return sentence.replace('{fields}', (details?.missing ?? []).map((f) => text.client_fields[f as keyof typeof text.client_fields] ?? f).join(', '));
    }
    if (blocker.code === 'ANSWERS_MISSING') {
      return sentence.replace('{fields}', (details?.keys ?? []).map(questionLabel).join(', '));
    }
    if (blocker.code === 'ESTIMATE_NOT_FINAL') {
      return sentence
        .replace('{version}', String(details?.version ?? ''))
        .replace('{status}', text.estimate_status[(details?.status ?? 'DRAFT') as keyof typeof text.estimate_status] ?? '');
    }
    return sentence;
  };

  return (
    <article aria-label="project-contract" className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{text.title}</h3>
      </div>
      <p className="text-xs text-slate-600 break-words">{text.intro}</p>

      {loading && <p role="status" className="text-sm text-slate-600">{text.loading}</p>}
      {loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-700 break-words">{text.load_failed}</p>
          <button type="button" onClick={() => void load()} className="w-full min-h-11 text-sm font-semibold text-slate-800 bg-slate-100 border border-slate-200 rounded-xl">
            <Ico>🔄</Ico>{text.retry}
          </button>
        </div>
      )}

      {!loading && !loadFailed && !open && (
        <>
          {latest && <p className="text-sm text-slate-700 break-words">{text.latest.replace('{n}', String(latest.version)).replace('{status}', text.status[latest.status])}</p>}
          {latest?.status === 'ISSUED' && (
            <section aria-label="contract-sign" className="space-y-2 border border-slate-200 rounded-xl p-3">
              <p className="text-xs text-slate-600 break-words">{text.sign_help}</p>
              <label className="block space-y-1">
                <span className="block text-sm font-medium text-slate-900 break-words">{text.signed_on}</span>
                <input
                  type="date"
                  aria-label="contract-signed-on"
                  value={signedOn}
                  max={todayIso()}
                  onChange={(e) => { setSignedOn(e.target.value); setConfirmSign(false); }}
                  className={FIELD}
                />
              </label>
              <button type="button" aria-label="sign-contract" disabled={busy || !signedOn} onClick={() => void sign()} className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-emerald-700 rounded-xl hover:bg-emerald-800 disabled:opacity-60 transition break-words">
                {confirmSign ? text.sign_confirm : text.sign}
              </button>
            </section>
          )}
          {latest && (latest.status === 'ISSUED' || latest.status === 'SIGNED') && (
            <>
              {latest.status === 'SIGNED' && latest.signed_on && (
                <p className="text-sm text-emerald-800 break-words">{text.signed_info.replace('{date}', latest.signed_on).replace('{version}', String(latest.estimate_version ?? ''))}</p>
              )}
              <button type="button" aria-label="close-contract" disabled={busy} onClick={() => void closeLatest()} className="w-full min-h-11 px-3 text-sm font-semibold text-red-800 pe-surface border border-red-300 rounded-xl hover:bg-red-50 disabled:opacity-60 transition break-words">
                {confirmClose ? text.close_confirm : latest.status === 'SIGNED' ? text.close_signed : text.close_issued}
              </button>
            </>
          )}
          {draft && (
            <p className="text-sm text-slate-700 break-words">
              {text.draft_summary.replace('{n}', String(draft.version)).replace('{missing}', String(draft.missing_required.length))}
            </p>
          )}
          <button
            type="button"
            aria-label="compose-contract"
            onClick={() => void start()}
            disabled={busy}
            className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-60 transition break-words"
          >
            {busy ? text.loading : draft ? text.continue : latest ? text.new_version : text.compose}
          </button>
        </>
      )}

      {open && draft && catalog && (
        <form aria-label="contract-form" onSubmit={(e) => { e.preventDefault(); void save(); }} className="space-y-4">
          <p className="text-sm text-slate-700 break-words" aria-label="contract-progress">
            {text.draft_progress.replace('{n}', String(draft.version)).replace('{done}', String(requiredDone)).replace('{total}', String(requiredTotal))}
          </p>
          {draft.missing_required.length > 0 && (
            <div aria-label="contract-missing" className="space-y-1">
              <p className="text-xs font-semibold text-slate-700 break-words">{text.missing_title}</p>
              <ul className="list-disc pl-5 text-xs text-slate-700">
                {draft.missing_required.map((key) => (
                  <li key={key} className="break-words">{questionLabel(key)}</li>
                ))}
              </ul>
            </div>
          )}
          <section aria-label="contract-prefill-box" className="space-y-1.5">
            <button type="button" aria-label="contract-prefill" disabled={busy} onClick={() => void prefillNow()} className="w-full min-h-11 px-3 text-sm font-semibold text-blue-700 border border-blue-300 rounded-xl hover:bg-blue-50 disabled:opacity-60 transition break-words">
              <Ico>✨</Ico>{text.prefill}
            </button>
            {prefillNote ? (
              <p role="status" aria-label="contract-prefill-note" className="text-xs text-emerald-800 break-words">{prefillNote}</p>
            ) : (
              <p className="text-xs text-slate-500 break-words">{text.prefill_hint}</p>
            )}
          </section>
          {groups.map((group) => (
            <fieldset key={group} className="space-y-3">
              <legend className="text-sm font-semibold text-slate-900 break-words">{catalogText.groups.questions[group]}</legend>
              {questions.filter((q) => q.group === group).map((question) => {
                const hint = question.hint_key ? catalogText.hints[question.key as keyof typeof catalogText.hints] : null;
                return (
                  <div key={question.key} className="space-y-1">
                    <span className="block text-sm font-medium text-slate-900 break-words">
                      {questionLabel(question.key)}
                      <span className={`ml-2 text-xs font-normal ${question.requirement === 'REQUIRED' ? 'text-red-700' : 'text-slate-500'}`}>
                        {question.requirement === 'REQUIRED' ? text.required : text.optional}
                      </span>
                      {prefilled.has(question.key) && (
                        <span aria-label={`contract-prefilled-${question.key}`} className="ml-2 inline-block rounded-md bg-emerald-50 border border-emerald-200 px-1.5 text-xs font-normal text-emerald-800">
                          {text.prefilled_badge}
                        </span>
                      )}
                    </span>
                    {hint && <span className="block text-xs text-slate-600 break-words">{hint}</span>}
                    <ContractQuestionInput question={question} value={fields[question.key]} requirements={requirements} authorised={authorised} onChange={(value) => setField(question.key, value)} />
                  </div>
                );
              })}
            </fieldset>
          ))}
          <p className="text-xs text-slate-500 break-words">{text.optional_note}</p>
          <section aria-label="contract-gate" className="space-y-2 border-t border-slate-200 pt-3">
            <h4 className="text-sm font-semibold text-slate-900 break-words">{text.gate_title}</h4>
            {gateFailed && <p role="alert" className="text-sm text-red-700 break-words">{text.gate_failed}</p>}
            {!gate && !gateFailed && <p role="status" className="text-sm text-slate-600">{text.gate_loading}</p>}
            {gate?.ready && <p className="text-sm text-emerald-800 break-words">{text.gate_ready}</p>}
            {gate && !gate.ready && (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-red-700 break-words">{text.gate_blocked}</p>
                <ul className="space-y-2">
                  {gate.blockers.map((blocker) => (
                    <li key={blocker.code} aria-label={`gate-${blocker.code}`} className="text-xs text-slate-800 break-words bg-red-50 border border-red-200 rounded-xl px-3 py-2 space-y-1">
                      <span className="block">{blockerText(blocker)}</span>
                      {blocker.code === 'SURFACE_INCOMPLETE' && (
                        <ul className="space-y-1">
                          {(blocker.details?.items ?? []).map((item) => (
                            <li key={`${item.room}-${item.surface}`} className="break-words">
                              <span className="font-semibold">
                                {item.room} › {getSurfaceDisplayName({ name: item.surface, surface_type: item.surface_type }, surfaceLabels)}
                              </span>
                              {': '}
                              {item.missing.map((m) => t.documents.tech_card_missing[m as keyof typeof t.documents.tech_card_missing] ?? m).join('; ')}
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
          {error && <p role="alert" aria-label="contract-error" className="text-sm text-red-700 break-words">{error}</p>}
          {note && <p role="status" aria-label="contract-note" className="text-sm text-emerald-800 break-words">{note}</p>}
          <button type="submit" aria-label="save-contract-answers" disabled={busy} className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-60 transition">
            <Ico>💾</Ico>{text.save}
          </button>
          <button type="button" aria-label="preview-contract" disabled={busy} onClick={() => void preview()} className="w-full min-h-11 px-3 text-sm font-semibold text-slate-900 bg-slate-100 border border-slate-300 rounded-xl hover:bg-slate-200 disabled:opacity-60 transition break-words">
            <Ico>👁️</Ico>{text.preview}
          </button>
          <button type="button" aria-label="issue-contract" disabled={busy || !gate?.ready} onClick={() => void issue()} className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-sky-700 rounded-xl hover:bg-sky-800 disabled:opacity-60 transition break-words">
            {text.issue}
          </button>
          <button type="button" aria-label="close-contract-form" disabled={busy} onClick={() => setOpen(false)} className="w-full min-h-11 px-3 text-sm font-semibold text-slate-800 pe-surface border border-slate-300 rounded-xl hover:bg-slate-100 disabled:opacity-60 transition">
            <Ico>✖️</Ico>{text.close}
          </button>
          <button type="button" aria-label="abandon-contract-draft" disabled={busy} onClick={() => void abandon()} className="w-full min-h-11 px-3 text-sm font-semibold text-red-800 pe-surface border border-red-300 rounded-xl hover:bg-red-50 disabled:opacity-60 transition break-words">
            {confirmAbandon ? text.abandon_confirm : text.abandon}
          </button>
        </form>
      )}

      {!open && error && <p role="alert" aria-label="contract-error" className="text-sm text-red-700 break-words">{error}</p>}
      {!open && note && <p role="status" aria-label="contract-note" className="text-sm text-emerald-800 break-words">{note}</p>}
    </article>
  );
}
