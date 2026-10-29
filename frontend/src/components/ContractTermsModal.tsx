import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { fetchContractCatalog } from '../api/contractCatalog';
import { fetchContractTerms, saveContractTerms } from '../api/contractTerms';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import type { AnswerValue } from '../types/contract';
import type { ContractCatalog, ContractQuestion, QuestionGroup } from '../types/contractCatalog';
import type { ContractTerms } from '../types/contractTerms';
import { FieldValue, toAnswer, toField } from '../utils/contractAnswers';
import { ContractQuestionInput } from './ContractQuestionInput';
import { Ico } from './Ico';

interface ContractTermsModalProps {
  onClose: () => void;
}

/**
 * UX walk B2 — "Moje standardowe warunki umowy": the answers of the contract's questionnaire that are the same for every order
 * (warranty, advance, payment, penalties, downtime, acceptance, premises). A new contract draft takes them first; a term left empty
 * here comes from the latest contract. The questions and their kinds are the server's catalogue, the same as in the contract.
 */
export function ContractTermsModal({ onClose }: ContractTermsModalProps) {
  const { t } = useI18n();
  const text = t.contract_terms;
  const catalogText = t.contractCatalog;
  const [catalog, setCatalog] = useState<ContractCatalog | null>(null);
  const [terms, setTerms] = useState<ContractTerms | null>(null);
  const [fields, setFields] = useState<Record<string, FieldValue>>({});
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useTelegramBackButton(true, onClose);

  const questions: ContractQuestion[] = useMemo(
    () => (catalog && terms ? catalog.questionnaire.items.filter((q) => terms.keys.includes(q.key)) : []),
    [catalog, terms],
  );
  const requirements = catalog?.requirements.items ?? [];

  const fillFrom = useCallback(
    (answers: Record<string, AnswerValue>, source: ContractCatalog, keys: string[]) => {
      const next: Record<string, FieldValue> = {};
      for (const question of source.questionnaire.items) {
        if (keys.includes(question.key)) next[question.key] = toField(question, answers[question.key], source.requirements.items);
      }
      setFields(next);
    },
    [],
  );

  const load = useCallback(async () => {
    setLoadFailed(false);
    try {
      const [loadedCatalog, loadedTerms] = await Promise.all([fetchContractCatalog(), fetchContractTerms()]);
      setCatalog(loadedCatalog);
      setTerms(loadedTerms);
      fillFrom(loadedTerms.answers, loadedCatalog, loadedTerms.keys);
    } catch {
      setLoadFailed(true);
    }
  }, [fillFrom]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!catalog || !terms || saving) return;
    const answers: Record<string, AnswerValue> = {};
    for (const question of questions) {
      const answer = toAnswer(question, fields[question.key] ?? '', requirements);
      if (answer !== null) answers[question.key] = answer;
    }
    setSaving(true);
    setError(null);
    setNote(null);
    try {
      const saved = await saveContractTerms(answers);
      setTerms(saved);
      fillFrom(saved.answers, catalog, saved.keys);
      setNote(text.saved.replace('{n}', String(Object.keys(saved.answers).length)));
    } catch (err) {
      if (err instanceof ApiError && err.code === 'CONTRACT_ANSWER_INVALID') {
        const details = (err.detail as { details?: { key?: string; reason?: string } } | null)?.details;
        const label = details?.key ? catalogText.questions[details.key as keyof typeof catalogText.questions] ?? details.key : '';
        setError(`${label}: ${t.contract.errors[(details?.reason ?? '') as keyof typeof t.contract.errors] ?? t.contract.errors.UNKNOWN}`);
      } else {
        setError(text.save_failed);
      }
    } finally {
      setSaving(false);
    }
  };

  const groups: QuestionGroup[] = [];
  for (const question of questions) if (!groups.includes(question.group)) groups.push(question.group);
  const empty = terms !== null && Object.keys(terms.answers).length === 0;
  const latest = terms?.latest ?? null;

  return (
    <div
      className="fixed inset-0 z-[60] overflow-y-auto"
      style={{ backgroundColor: 'var(--tg-theme-bg-color)', color: 'var(--tg-theme-text-color)' }}
      role="dialog"
      aria-modal="true"
      aria-label={text.title}
    >
      <div className="mx-auto w-full max-w-md px-4 py-4 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <h2 className="min-w-0 text-lg font-bold break-words">{text.title}</h2>
          <button
            type="button"
            aria-label="close-contract-terms"
            onClick={onClose}
            className="min-h-11 min-w-11 shrink-0 flex items-center justify-center rounded-xl border text-xl font-semibold"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              color: 'var(--tg-theme-hint-color)',
              borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))',
            }}
          >
            ×
          </button>
        </div>
        <p className="text-sm break-words" style={{ color: 'var(--tg-theme-hint-color)' }}>{text.intro}</p>

        {loadFailed && (
          <div className="space-y-2">
            <p role="alert" className="text-sm text-red-700 break-words">{text.load_failed}</p>
            <button type="button" onClick={() => void load()} className="w-full min-h-11 text-sm font-semibold rounded-xl border border-slate-200 pe-surface text-slate-800">
              <Ico>🔄</Ico>{t.contract.retry}
            </button>
          </div>
        )}
        {!loadFailed && (!catalog || !terms) && <p role="status" className="text-sm text-slate-600">{t.contract.loading}</p>}

        {catalog && terms && (
          <form aria-label="contract-terms-form" onSubmit={(event) => void save(event)} className="space-y-4">
            {empty && (
              <p aria-label="contract-terms-empty" className="text-sm text-amber-800 break-words">
                {latest ? text.empty_latest.replace('{name}', latest.project_name ?? '—') : text.empty_none}
              </p>
            )}
            {latest && (
              <button
                type="button"
                aria-label="contract-terms-from-latest"
                onClick={() => {
                  fillFrom({ ...latest.answers }, catalog, terms.keys);
                  setNote(text.from_latest_done);
                  setError(null);
                }}
                className="w-full min-h-11 px-3 text-sm font-semibold text-blue-700 border border-blue-300 rounded-xl hover:bg-blue-50 break-words"
              >
                <Ico>📋</Ico>{text.from_latest.replace('{name}', latest.project_name ?? '—')}
              </button>
            )}
            {groups.map((group) => (
              <fieldset key={group} className="space-y-3">
                <legend className="text-sm font-semibold break-words">{catalogText.groups.questions[group]}</legend>
                {questions.filter((q) => q.group === group).map((question) => {
                  const hint = question.hint_key ? catalogText.hints[question.key as keyof typeof catalogText.hints] : null;
                  return (
                    <div key={question.key} className="space-y-1">
                      <span className="block text-sm font-medium break-words">{catalogText.questions[question.key as keyof typeof catalogText.questions] ?? question.key}</span>
                      {hint && <span className="block text-xs text-slate-600 break-words">{hint}</span>}
                      <ContractQuestionInput
                        question={question}
                        value={fields[question.key]}
                        requirements={requirements}
                        onChange={(value) => setFields((current) => ({ ...current, [question.key]: value }))}
                      />
                    </div>
                  );
                })}
              </fieldset>
            ))}
            {error && <p role="alert" aria-label="contract-terms-error" className="text-sm text-red-700 break-words">{error}</p>}
            {note && <p role="status" aria-label="contract-terms-note" className="text-sm text-emerald-800 break-words">{note}</p>}
            <button type="submit" aria-label="save-contract-terms" disabled={saving} className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-60 transition">
              <Ico>💾</Ico>{saving ? t.common.saving : text.save}
            </button>
            <button type="button" aria-label="close-contract-terms-bottom" onClick={onClose} className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-slate-300 pe-surface text-slate-800">
              <Ico>✖️</Ico>{t.common.close}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
