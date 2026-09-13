import { useEffect, useMemo, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { resolveKey } from '../utils/i18nKeys';
import {
  answeredQuestionCount,
  qualityLevelsForSubstrate,
} from '../utils/inspectionFindings';
import { ApiError } from '../api/http';
import { fetchChecklistTemplate, fetchChecklistTemplates } from '../api/checklists';
import {
  completeInspection,
  createInspection,
  fetchInspection,
  fetchInspectionFindings,
  putInspectionAnswers,
  reopenInspection,
} from '../api/inspections';
import {
  ChecklistOption,
  ChecklistQuestion,
  ChecklistTemplate,
  QualityLevelValue,
  SubstrateValue,
} from '../types/checklist';
import {
  Inspection,
  InspectionAnswerPayload,
  InspectionCreatePayload,
  InspectionDetail,
  InspectionFinding,
  InspectionTarget,
} from '../types/inspection';
import { formatMetric } from '../utils/format';
import { RiskPanel } from './RiskPanel';
import { CommunicationPanel } from './CommunicationPanel';

export interface InspectionFlowProps {
  projectId: string;
  roomId: string;
  target: InspectionTarget;
  inspectionId: string | null;
  onExit: () => void;
  onCreated: (inspectionId: string) => void;
}

type Step = 'substrate' | 'quality' | 'active' | 'review';

const SUBSTRATES: SubstrateValue[] = [
  'CONCRETE',
  'GYPSUM_PLASTER',
  'CEMENT_LIME_PLASTER',
  'GYPSUM_BOARD',
  'PAINTED',
  'OTHER',
];

function substrateLabel(
  t: ReturnType<typeof useI18n>['t'],
  substrate: SubstrateValue,
): string {
  const key = `substrate_${substrate.toLowerCase()}` as keyof typeof t.inspections;
  return String(t.inspections[key] ?? substrate);
}

function targetLabel(
  t: ReturnType<typeof useI18n>['t'],
  target: InspectionTarget,
): string {
  if (target.kind === 'surface') {
    return target.surfaceName ?? t.inspections.inspect_wall;
  }
  if (target.kind === 'plane') {
    return target.plane === 'FLOOR'
      ? t.inspections.inspect_floor
      : t.inspections.inspect_ceiling;
  }
  return t.inspections.inspect_room;
}

/** Normalize a raw NUMBER answer string for the backend Decimal contract:
 * trim whitespace and accept a comma as the decimal separator (PL/RU input
 * habit). Returns null when the field was cleared (an unanswered question).
 * This NEVER truncates or rounds — an over-precision value is the user's
 * responsibility to correct, never silently changed by the app. */
function normalizeNumberInput(raw: string): string | null {
  const cleaned = raw.trim().replace(',', '.');
  return cleaned === '' ? null : cleaned;
}

/** A normalized NUMBER value is submittable when it parses to a finite number
 * AND has at most 3 decimal places (backend decimal_places=3 / Numeric(10,3)).
 * Values with 4+ fractional digits are INVALID: silently capping them would
 * corrupt the user's measurement, so they block save/complete instead. */
function isValidNumberInput(cleaned: string): boolean {
  if (!Number.isFinite(Number(cleaned))) return false;
  const dot = cleaned.indexOf('.');
  return dot === -1 || cleaned.length - dot - 1 <= 3;
}

/** An answer row whose only fields are null is an unanswered question. The
 * backend contract represents "unanswered" as an ABSENT row (a NUMBER row with
 * value_number null 422s), so such rows must not be sent. An explicit
 * option_keys: [] remains a legitimate "none selected" answer and is kept. */
function isAnswered(answer: InspectionAnswerPayload): boolean {
  return (
    answer.value_bool != null ||
    answer.value_number != null ||
    (answer.value_text != null && answer.value_text !== '') ||
    answer.option_key != null ||
    answer.option_keys != null
  );
}

// Single canonical API->form mapper: every answer list (normal Draft load and
// reopen-after-COMPLETED) becomes the editable answer state with this shape.
function seedAnswersFromDetail(
  detail: InspectionDetail,
): Record<string, InspectionAnswerPayload> {
  const seeded: Record<string, InspectionAnswerPayload> = {};
  for (const answer of detail.answers) {
    seeded[answer.question_id] = {
      question_id: answer.question_id,
      value_bool: answer.value_bool,
      value_number:
        answer.value_number === null || answer.value_number === undefined
          ? null
          : String(answer.value_number),
      value_text: answer.value_text,
      option_key: answer.option_key,
      option_keys: answer.option_keys,
    };
  }
  return seeded;
}

export function InspectionFlow({
  projectId,
  roomId,
  target,
  inspectionId,
  onExit,
  onCreated,
}: InspectionFlowProps) {
  const { t } = useI18n();
  const [step, setStep] = useState<Step>(inspectionId === null ? 'substrate' : 'active');
  const [substrate, setSubstrate] = useState<SubstrateValue | null>(null);
  const [quality, setQuality] = useState<QualityLevelValue | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [template, setTemplate] = useState<ChecklistTemplate | null>(null);
  const [answers, setAnswers] = useState<Record<string, InspectionAnswerPayload>>({});
  const [findings, setFindings] = useState<InspectionFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [numberErrors, setNumberErrors] = useState<Record<string, string>>({});

  const isCompleted = inspection?.status === 'COMPLETED';

  useEffect(() => {
    // Only load from the backend when a real inspection is requested. For a new
    // inspection the id arrives later (onCreated) after the DRAFT already exists
    // in local state, so we must not reload or we would clobber draft answers.
    if (inspectionId === null || inspection !== null) {
      setLoading(false);
      return;
    }
    const targetId = inspectionId;
    let cancelled = false;
    async function loadExisting() {
      setLoading(true);
      setError(null);
      try {
        const detail = await fetchInspection(projectId, roomId, targetId);
        const tpl = await fetchChecklistTemplate(detail.template_id);
        if (cancelled) return;
        const seeded = seedAnswersFromDetail(detail);
        setInspection(detail);
        setTemplate(tpl);
        setSubstrate(detail.substrate);
        setQuality(detail.quality_target);
        setAnswers(seeded);
        if (detail.status === 'COMPLETED') {
          const findingsResult = await fetchInspectionFindings(
            projectId,
            roomId,
            targetId,
            true,
          );
          if (!cancelled) setFindings(findingsResult.items);
        }
        setStep(detail.status === 'COMPLETED' ? 'review' : 'active');
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t.inspections.error_load);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadExisting();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, roomId, inspectionId]);

  const questions = useMemo(() => {
    const entries: { question: ChecklistQuestion; options: ChecklistOption[] }[] = [];
    if (!template) return entries;
    for (const section of template.sections) {
      for (const question of section.questions) {
        entries.push({ question, options: question.options });
      }
    }
    return entries;
  }, [template]);

  const answeredCount = useMemo(
    () =>
      answeredQuestionCount(
        questions.map(({ question }) => answers[question.id]).filter(Boolean) as InspectionAnswerPayload[],
      ),
    [questions, answers],
  );

  const qualityLevels = substrate ? qualityLevelsForSubstrate(substrate) : undefined;
  const shownQualityLevels =
    qualityLevels ?? (['Q1', 'Q2', 'Q3', 'Q4', 'S1', 'S2', 'S3', 'S4'] as QualityLevelValue[]);

  function setAnswer(
    questionId: string,
    patch: Partial<InspectionAnswerPayload>,
  ): void {
    setAnswers((prev) => {
      const current = prev[questionId] ?? { question_id: questionId };
      return { ...prev, [questionId]: { ...current, ...patch, question_id: questionId } };
    });
    // Editing a question clears its precision error; the corrected value is
    // re-validated on blur and again at submission.
    setNumberErrors((prev) => {
      if (!(questionId in prev)) return prev;
      const next = { ...prev };
      delete next[questionId];
      return next;
    });
    setNotice(null);
  }

  /** Normalize a NUMBER answer when its field loses focus: comma → dot, then
   * flag it invalid (localized inline error) if it exceeds the 3-decimal-place
   * contract. The typed value is always preserved — never rewritten to fit. */
  function handleBlurNumber(questionId: string, raw: string): void {
    const normalized = normalizeNumberInput(raw);
    const message =
      normalized !== null && !isValidNumberInput(normalized)
        ? t.inspections.error_number_precision
        : null;
    setAnswers((prev) => {
      const current = prev[questionId] ?? { question_id: questionId };
      return {
        ...prev,
        [questionId]: { ...current, value_number: normalized, question_id: questionId },
      };
    });
    setNumberErrors((prev) => {
      if (message === null) {
        if (!(questionId in prev)) return prev;
        const next = { ...prev };
        delete next[questionId];
        return next;
      }
      return { ...prev, [questionId]: message };
    });
    if (message === null) {
      // Resolving the field clears the precision banner immediately, so the
      // user gets positive feedback while fixing — not only on the next save.
      setError((prev) =>
        prev === t.inspections.error_number_precision ? null : prev,
      );
    }
  }

  /** Build the outgoing answers payload. Every NUMBER answer is normalized
   * (comma→dot) and precision-checked against the backend Decimal(10,3)
   * contract; over-precision values are reported per-field and BLOCK
   * submission instead of being truncated. Cleared NUMBER fields stay
   * unanswered (absent rows), per the 8C.1 contract. */
  function prepareAnswersForSubmit(): {
    payload: InspectionAnswerPayload[];
    errors: Record<string, string>;
  } {
    const payload: InspectionAnswerPayload[] = [];
    const errors: Record<string, string> = {};
    for (const { question } of questions) {
      const answer = answers[question.id];
      if (!answer) continue;
      if (question.answer_type === 'NUMBER') {
        const normalized = normalizeNumberInput(String(answer.value_number ?? ''));
        if (normalized === null) continue; // cleared → unanswered → absent row
        if (!isValidNumberInput(normalized)) {
          errors[question.id] = t.inspections.error_number_precision;
          continue;
        }
        payload.push({ ...answer, value_number: normalized });
      } else if (isAnswered(answer)) {
        payload.push(answer);
      }
    }
    return { payload, errors };
  }

  /** Shared save/complete validation gate. Runs SYNCHRONOUSLY — before the
   * saving spinner toggles — so an over-precision NUMBER answer blocks the
   * submission with its localized per-field error WITHOUT leaving the save
   * button stuck disabled. Returns the normalized payload when valid. */
  function prepareForSubmit():
    | { ok: false }
    | { ok: true; payload: InspectionAnswerPayload[] } {
    const { payload, errors } = prepareAnswersForSubmit();
    if (Object.keys(errors).length > 0) {
      setNumberErrors(errors);
      setError(t.inspections.error_number_precision);
      return { ok: false };
    }
    setNumberErrors({});
    return { ok: true, payload };
  }

  async function beginInspection(): Promise<void> {
    if (!substrate) return;
    setSaving(true);
    setError(null);
    try {
      const list = await fetchChecklistTemplates(substrate);
      const tpl = list.items.find((candidate) => candidate.active) ?? list.items[0];
      if (!tpl) {
        setError(t.inspections.error_start);
        return;
      }
      const payload: InspectionCreatePayload = {
        template_id: tpl.id,
        substrate,
        quality_target: quality,
        surface_id: target.kind === 'surface' ? target.surfaceId : null,
        plane: target.kind === 'plane' ? target.plane : null,
      };
      const created = await createInspection(projectId, roomId, payload);
      // The list endpoint returns bare templates without sections. Hydrate the exact
      // template by id so the checklist renders immediately — a reload/re-enter must
      // not be required for the questions to appear after Start.
      const tplDetail = await fetchChecklistTemplate(created.template_id);
      setTemplate(tplDetail);
      setInspection(created);
      setAnswers({});
      setStep('active');
      onCreated(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.inspections.error_start);
    } finally {
      setSaving(false);
    }
  }

  async function saveDraft(): Promise<void> {
    if (!inspection) return;
    setError(null);
    const prepared = prepareForSubmit();
    if (!prepared.ok) return;
    setAnswers((prev) => {
      const merged = { ...prev };
      for (const answer of prepared.payload) merged[answer.question_id] = answer;
      return merged;
    });
    setSaving(true);
    try {
      await putInspectionAnswers(projectId, roomId, inspection.id, {
        answers: prepared.payload,
      });
      setNotice(t.inspections.saved);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 422
          ? t.inspections.error_validation
          : err instanceof Error
            ? err.message
            : t.inspections.error_validation,
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleComplete(): Promise<void> {
    if (!inspection) return;
    setError(null);
    const prepared = prepareForSubmit();
    if (!prepared.ok) return;
    setAnswers((prev) => {
      const merged = { ...prev };
      for (const answer of prepared.payload) merged[answer.question_id] = answer;
      return merged;
    });
    setSaving(true);
    try {
      await putInspectionAnswers(projectId, roomId, inspection.id, {
        answers: prepared.payload,
      });
      const completed = await completeInspection(projectId, roomId, inspection.id);
      const findingsResult = await fetchInspectionFindings(
        projectId,
        roomId,
        inspection.id,
        true,
      );
      setInspection(completed);
      setFindings(findingsResult.items);
      setStep('review');
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 422
          ? t.inspections.error_validation
          : err instanceof Error
            ? err.message
            : t.inspections.error_validation,
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleReopen(): Promise<void> {
    if (!inspection) return;
    setSaving(true);
    setError(null);
    try {
      const reopened = await reopenInspection(projectId, roomId, inspection.id);
      // The reopen response carries no answers. Rebuild the editable DRAFT answer
      // state from the backend with the same canonical mapper as a normal load so
      // no stale COMPLETED representation leaks into the resumed form.
      const detail = await fetchInspection(projectId, roomId, inspection.id);
      setInspection(reopened);
      setAnswers(seedAnswersFromDetail(detail));
      setFindings([]);
      setStep('active');
    } catch (err) {
      setError(err instanceof Error ? err.message : t.inspections.error_state);
    } finally {
      setSaving(false);
    }
  }

  function handleBack(): void {
    if (step === 'quality') {
      setStep('substrate');
      return;
    }
    if (step === 'review' && !isCompleted) {
      setStep('active');
      return;
    }
    onExit();
  }

  if (loading) {
    return <p className="p-4 text-sm text-neutral-500">{t.inspections.loading}</p>;
  }

  return (
    <section
      aria-label={
        inspectionId === null ? t.inspections.title : `${t.inspections.title} — ${targetLabel(t, target)}`
      }
      className="flex flex-col gap-3 rounded-lg border border-neutral-200 bg-neutral-50 p-3"
    >
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label={t.common.back}
          className="min-h-10 rounded-lg border border-neutral-300 px-3 text-neutral-700"
          onClick={handleBack}
        >
          ←
        </button>
        <h3 className="min-w-0 flex-1 truncate text-base font-semibold text-neutral-900">
          {step === 'substrate'
            ? t.inspections.select_substrate
            : step === 'quality'
              ? t.inspections.select_quality
              : step === 'active'
                ? t.inspections.review
                : isCompleted
                  ? t.inspections.findings_title
                  : t.inspections.review_summary}
        </h3>
      </div>

      {error ? (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm text-green-700">{notice}</p> : null}

      {step === 'substrate' ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-neutral-600">{targetLabel(t, target)}</p>
          <div className="grid grid-cols-2 gap-2">
            {SUBSTRATES.map((value) => (
              <button
                key={value}
                type="button"
                aria-label={substrateLabel(t, value)}
                className={`min-h-14 rounded-lg border px-3 text-sm font-medium ${
                  substrate === value
                    ? 'border-blue-600 bg-blue-50 text-blue-800'
                    : 'border-neutral-300 bg-white text-neutral-800'
                }`}
                onClick={() => setSubstrate(value)}
              >
                {substrateLabel(t, value)}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="min-h-11 flex-1 rounded-lg border border-neutral-300 bg-white px-3 font-medium text-neutral-700"
              onClick={() => setStep('substrate')}
            >
              {t.common.cancel}
            </button>
            <button
              type="button"
              aria-label={t.inspections.next}
              className="min-h-11 flex-1 rounded-lg bg-blue-600 px-3 font-medium text-white disabled:opacity-50"
              disabled={substrate === null}
              onClick={() => setStep('quality')}
            >
              {t.inspections.next}
            </button>
          </div>
        </div>
      ) : null}

      {step === 'quality' ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-neutral-600">{t.inspections.quality_hint}</p>
          {qualityLevels === undefined ? (
            <p className="rounded-md bg-neutral-100 px-3 py-2 text-xs text-neutral-600">
              {t.inspections.quality_optional_hint}
            </p>
          ) : null}
          <div className="grid grid-cols-4 gap-2">
            {shownQualityLevels.map((level) => (
              <button
                key={level}
                type="button"
                aria-label={level}
                className={`min-h-11 rounded-lg border text-sm font-semibold ${
                  quality === level
                    ? 'border-blue-600 bg-blue-50 text-blue-800'
                    : 'border-neutral-300 bg-white text-neutral-800'
                }`}
                onClick={() => setQuality(level)}
              >
                {level}
              </button>
            ))}
          </div>
          <button
            type="button"
            aria-label={t.inspections.skip}
            className="min-h-10 self-start rounded-lg text-sm text-neutral-600 underline"
            onClick={() => setQuality(null)}
          >
            {t.inspections.skip}
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              className="min-h-11 flex-1 rounded-lg border border-neutral-300 bg-white px-3 font-medium text-neutral-700"
              onClick={() => setStep('substrate')}
            >
              {t.common.back}
            </button>
            <button
              type="button"
              aria-label={t.inspections.start}
              className="min-h-11 flex-1 rounded-lg bg-blue-600 px-3 font-medium text-white disabled:opacity-50"
              disabled={saving}
              onClick={() => void beginInspection()}
            >
              {t.inspections.start}
            </button>
          </div>
        </div>
      ) : null}

      {step === 'active' ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-neutral-600">
            {t.inspections.answered_count
              .replace('{answered}', String(answeredCount))
              .replace('{total}', String(questions.length))}
          </p>
          {questions.length === 0 ? (
            <p className="text-sm text-neutral-500">{t.inspections.empty}</p>
          ) : (
            questions.map(({ question, options }) => (
              <QuestionField
                key={question.id}
                question={question}
                options={options}
                answer={answers[question.id]}
                readOnly={false}
                error={numberErrors[question.id]}
                onNumberBlur={handleBlurNumber}
                onChange={(patch) => setAnswer(question.id, patch)}
                t={t}
              />
            ))
          )}
          <div className="flex flex-col gap-2">
            <button
              type="button"
              aria-label={t.inspections.save_draft}
              className="min-h-11 rounded-lg border border-blue-600 px-3 font-medium text-blue-700 disabled:opacity-50"
              disabled={saving || inspection === null}
              onClick={() => void saveDraft()}
            >
              {t.inspections.save_draft}
            </button>
            <button
              type="button"
              aria-label={t.inspections.review}
              className="min-h-11 rounded-lg bg-blue-600 px-3 font-medium text-white"
              onClick={() => setStep('review')}
            >
              {t.inspections.review}
            </button>
          </div>
        </div>
      ) : null}

      {step === 'review' ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-neutral-700">
            {t.inspections.substrate}: {substrate && substrateLabel(t, substrate)} ·{' '}
            {t.inspections.quality_target}: {quality ?? '—'} ·{' '}
            {t.inspections.answered_count
              .replace('{answered}', String(answeredCount))
              .replace('{total}', String(questions.length))}
          </p>

          <div>
            <h4 className="text-sm font-semibold text-neutral-900">
              {isCompleted ? t.inspections.findings_title : t.inspections.review_title}
            </h4>
            {isCompleted ? (
              findings.length === 0 ? (
                <p className="text-sm text-neutral-500">{t.inspections.no_findings}</p>
              ) : (
                <ul className="mt-2 flex flex-col gap-2">
                  {findings.map((finding) => (
                    <FindingRow key={finding.id} finding={finding} t={t} />
                  ))}
                </ul>
              )
            ) : questions.length === 0 ? (
              <p className="text-sm text-neutral-500">{t.inspections.empty}</p>
            ) : (
              <div className="mt-2 flex flex-col gap-2">
                {questions.map(({ question, options }) => (
                  <QuestionField
                    key={question.id}
                    question={question}
                    options={options}
                    answer={answers[question.id]}
                    readOnly
                    onChange={() => undefined}
                    t={t}
                  />
                ))}
              </div>
            )}
          </div>

          {!isCompleted ? (
            <div className="flex flex-col gap-2">
              <p className="text-xs text-neutral-500">{t.inspections.unanswered_note}</p>
              <button
                type="button"
                aria-label={t.inspections.complete}
                className="min-h-11 rounded-lg bg-green-700 px-3 font-medium text-white disabled:opacity-50"
                disabled={saving}
                onClick={() => void handleComplete()}
              >
                {t.inspections.complete}
              </button>
            </div>
          ) : (
            <>
              <RiskPanel
                projectId={projectId}
                roomId={roomId}
                inspectionId={inspection.id}
              />
              <CommunicationPanel
                projectId={projectId}
                roomId={roomId}
                inspectionId={inspection.id}
              />
              <button
                type="button"
                aria-label={t.inspections.reopen}
                className="min-h-11 rounded-lg border border-blue-600 px-3 font-medium text-blue-700 disabled:opacity-50"
                disabled={saving}
                onClick={() => void handleReopen()}
              >
                {t.inspections.reopen}
              </button>
            </>
          )}
        </div>
      ) : null}
    </section>
  );
}

function QuestionField({
  question,
  options,
  answer,
  readOnly,
  onChange,
  onNumberBlur,
  error,
  t,
}: {
  question: ChecklistQuestion;
  options: ChecklistOption[];
  answer: InspectionAnswerPayload | undefined;
  readOnly: boolean;
  onChange: (patch: Partial<InspectionAnswerPayload>) => void;
  onNumberBlur?: (questionId: string, raw: string) => void;
  error?: string;
  t: ReturnType<typeof useI18n>['t'];
}) {
  const label = resolveKey(t, question.text_key);
  const hint = question.hint_key ? resolveKey(t, question.hint_key) : null;
  const unit = question.unit_key ? resolveKey(t, question.unit_key) : null;

  return (
    <fieldset className="rounded-lg border border-neutral-200 bg-white p-3">
      <legend className="px-1 text-sm font-medium text-neutral-900">{label}</legend>
      {hint ? <p className="mb-2 text-xs text-neutral-500">{hint}</p> : null}

      {question.answer_type === 'BOOLEAN' ? (
        readOnly ? (
          <p className="text-sm text-neutral-700">
            {answer?.value_bool === true
              ? t.inspections.yes
              : answer?.value_bool === false
                ? t.inspections.no
                : '—'}
          </p>
        ) : (
          <div className="flex gap-2">
            <button
              type="button"
              aria-label={t.inspections.yes}
              className={`min-h-11 flex-1 rounded-lg border text-sm font-medium ${
                answer?.value_bool === true
                  ? 'border-blue-600 bg-blue-50 text-blue-800'
                  : 'border-neutral-300 text-neutral-800'
              }`}
              onClick={() => onChange({ value_bool: true })}
            >
              {t.inspections.yes}
            </button>
            <button
              type="button"
              aria-label={t.inspections.no}
              className={`min-h-11 flex-1 rounded-lg border text-sm font-medium ${
                answer?.value_bool === false
                  ? 'border-blue-600 bg-blue-50 text-blue-800'
                  : 'border-neutral-300 text-neutral-800'
              }`}
              onClick={() => onChange({ value_bool: false })}
            >
              {t.inspections.no}
            </button>
          </div>
        )
      ) : null}

      {question.answer_type === 'SINGLE_CHOICE' ? (
        readOnly ? (
          <ReadOnlyChoice labelKey={options.find((o) => o.key === answer?.option_key)?.label_key} t={t} />
        ) : (
          <div className="flex flex-wrap gap-2">
            {options.map((option) => (
              <button
                key={option.id}
                type="button"
                aria-label={resolveKey(t, option.label_key)}
                className={`min-h-11 rounded-lg border px-3 text-sm font-medium ${
                  answer?.option_key === option.key
                    ? 'border-blue-600 bg-blue-50 text-blue-800'
                    : 'border-neutral-300 bg-white text-neutral-800'
                }`}
                onClick={() => onChange({ option_key: option.key })}
              >
                {resolveKey(t, option.label_key)}
              </button>
            ))}
          </div>
        )
      ) : null}

      {question.answer_type === 'MULTI_CHOICE' ? (
        readOnly ? (
          <ReadOnlyMulti labelKeys={options.filter((o) => (answer?.option_keys ?? []).includes(o.key)).map((o) => o.label_key)} t={t} />
        ) : (
          <div className="flex flex-wrap gap-2">
            {options.map((option) => {
              const selected = (answer?.option_keys ?? []).includes(option.key);
              return (
                <button
                  key={option.id}
                  type="button"
                  aria-label={resolveKey(t, option.label_key)}
                  className={`min-h-10 rounded-full border px-3 text-sm font-medium ${
                    selected
                      ? 'border-blue-600 bg-blue-50 text-blue-800'
                      : 'border-neutral-300 bg-white text-neutral-800'
                  }`}
                  onClick={() => {
                    const current = answer?.option_keys ?? [];
                    // Tapping a chip inverts it: selecting adds, deselecting
                    // removes. Deselecting the last chip yields an explicit
                    // option_keys: [] ("none selected") which the backend
                    // persists as a legitimate zero-choice answer. It is never
                    // degraded to null, so the question stays answerable and
                    // all chips remain hydrated on reopen.
                    const next = selected
                      ? current.filter((key) => key !== option.key)
                      : [...current, option.key];
                    onChange({ option_keys: next });
                  }}
                >
                  {resolveKey(t, option.label_key)}
                </button>
              );
            })}
          </div>
        )
      ) : null}

      {question.answer_type === 'NUMBER' ? (
        readOnly ? (
          <p className="text-sm text-neutral-700">
            {answer?.value_number !== null && answer?.value_number !== undefined
              ? `${answer.value_number}${unit ? ` ${unit}` : ''}`
              : '—'}
          </p>
        ) : (
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <input
                type="text"
                inputMode="decimal"
                aria-label={label}
                className={`min-h-11 w-full rounded-lg border px-3 text-sm ${
                  error ? 'border-red-500' : 'border-neutral-300'
                }`}
                placeholder="0,0"
                value={answer?.value_number != null ? String(answer.value_number) : ''}
                onChange={(event) => onChange({ value_number: event.target.value })}
                onBlur={(event) => onNumberBlur?.(question.id, event.target.value)}
              />
              {unit ? <span className="shrink-0 text-sm text-neutral-600">{unit}</span> : null}
            </div>
            {error ? (
              <p className="text-xs text-red-600" role="alert">
                {error}
              </p>
            ) : null}
          </div>
        )
      ) : null}

      {question.answer_type === 'TEXT' ? (
        readOnly ? (
          <p className="whitespace-pre-wrap text-sm text-neutral-700">
            {answer?.value_text || '—'}
          </p>
        ) : (
          <textarea
            aria-label={label}
            className="min-h-20 w-full rounded-lg border border-neutral-300 px-3 py-2 text-sm"
            value={answer?.value_text ?? ''}
            onChange={(event) => onChange({ value_text: event.target.value })}
          />
        )
      ) : null}
    </fieldset>
  );
}

function ReadOnlyChoice({ labelKey, t }: { labelKey?: string; t: ReturnType<typeof useI18n>['t'] }) {
  return (
    <p className="text-sm text-neutral-700">
      {labelKey ? resolveKey(t, labelKey) : '—'}
    </p>
  );
}

function ReadOnlyMulti({ labelKeys, t }: { labelKeys: string[]; t: ReturnType<typeof useI18n>['t'] }) {
  return (
    <p className="text-sm text-neutral-700">
      {labelKeys.length === 0 ? '—' : labelKeys.map((key) => resolveKey(t, key)).join(', ')}
    </p>
  );
}

export function FindingRow({
  finding,
  t,
}: {
  finding: InspectionFinding;
  t: ReturnType<typeof useI18n>['t'];
}) {
  const label = finding.label_key ? resolveKey(t, finding.label_key) : finding.finding_key;
  const value = finding.value_snapshot;
  let detail = '';
  if (value) {
    if ('number' in value && typeof value.number === 'string') {
      detail = `${formatMetric(value.number)} ${t.inspections.unit_mm}`;
    } else if ('text' in value && typeof value.text === 'string') {
      detail = value.text;
    } else if ('bool' in value) {
      detail = t.inspections.yes;
    }
  }
  const isActive = finding.is_active;
  return (
    <li
      className={`rounded-md border px-3 py-2 text-sm ${
        isActive
          ? 'border-neutral-200 bg-white text-neutral-900'
          : 'border-neutral-200 bg-neutral-100 text-neutral-500 line-through'
      }`}
    >
      {label}
      {detail ? ` — ${detail}` : ''}
    </li>
  );
}