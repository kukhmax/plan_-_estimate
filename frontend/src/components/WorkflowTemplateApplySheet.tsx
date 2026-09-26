import { useEffect, useMemo, useRef, useState } from 'react';
import {
  applyTemplateToWorkPlan,
  classifyApplyTemplateError,
  fetchCompatibleTemplates,
  fetchWorkflowTemplate,
} from '../api/workflowTemplates';
import { useI18n } from '../hooks/useI18n';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { SurfaceTypeValue } from '../types/surface';
import { SurfacePriceItemSummaryRead, SurfaceWorkPlanRead } from '../types/workPlan';
import {
  ApplyTemplateRequest,
  TemplateApplicationMode,
  WorkflowTemplateRead,
} from '../types/workflowTemplate';
import { localizeApiError } from '../utils/apiErrors';
import { resolveKey } from '../utils/i18nKeys';

/**
 * Stage 13E.4 — technological workflow picker / preview / apply sheet.
 *
 * The preview is a read-only snapshot of the server template; the apply call
 * (Stage 13E.3) materializes it server-side on the CURRENT plan. The parent
 * only opens this sheet for a saved plan without unsaved changes, so the
 * occurrence keys passed in are the server's current composition.
 */
interface WorkflowTemplateApplySheetProps {
  projectId: string;
  roomId: string;
  surfaceId: string;
  surfaceType?: SurfaceTypeValue;
  substrate: SubstrateValue;
  qualityTarget: QualityLevelValue;
  /** Ordered occurrence keys of the loaded plan; null = a row without a key. */
  occurrenceKeys: (string | null)[];
  /** price_item_id of every current occurrence (same order). Used ONLY for
   * the "already in the plan" hint of the final APPEND review -- never for
   * provenance, occurrence identity or deduplication. */
  planPriceItemIds: string[];
  coefficientAssignmentCount: number;
  onApplied: (plan: SurfaceWorkPlanRead) => void;
  /** Reload the work plan (stale-plan recovery); the sheet is closed by the parent. */
  onReloadPlan: () => void;
  onClose: () => void;
}

type ListState = 'loading' | 'ready' | 'error';
type ApplyError =
  | { kind: 'stale_template' | 'stale_plan' | 'template_unavailable' | 'transport' }
  | { kind: 'error'; detail: string };

interface Attempt {
  applicationId: string;
  signature: string;
}

function newApplicationId(): string {
  return crypto.randomUUID();
}

export function WorkflowTemplateApplySheet({
  projectId,
  roomId,
  surfaceId,
  surfaceType,
  substrate,
  qualityTarget,
  occurrenceKeys,
  planPriceItemIds,
  coefficientAssignmentCount,
  onApplied,
  onReloadPlan,
  onClose,
}: WorkflowTemplateApplySheetProps) {
  const { t, locale } = useI18n();
  const [listState, setListState] = useState<ListState>('loading');
  const [listAttempt, setListAttempt] = useState(0);
  const [templates, setTemplates] = useState<WorkflowTemplateRead[]>([]);
  const [selected, setSelected] = useState<WorkflowTemplateRead | null>(null);
  const [optionalOn, setOptionalOn] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<TemplateApplicationMode>('APPEND');
  const [confirming, setConfirming] = useState(false);
  // Final APPEND review (13E.5B-FIX.4): the exact candidate occurrences, each
  // individually confirmable, before anything is sent to the server.
  const [reviewing, setReviewing] = useState(false);
  const [reviewOn, setReviewOn] = useState<Set<string>>(new Set());
  const [applying, setApplying] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ApplyError | null>(null);
  // One logical Apply command keeps its application_id across transport
  // retries; any semantic change produces a new id on the next Apply.
  const attempt = useRef<Attempt | null>(null);
  // Synchronous double-submit guard (state updates are async).
  const inFlight = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setListState('loading');
    void fetchCompatibleTemplates({ substrate, quality_target: qualityTarget, surface_type: surfaceType })
      .then((resp) => {
        if (cancelled) return;
        setTemplates(resp.items);
        setListState('ready');
      })
      .catch(() => {
        if (!cancelled) setListState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [listAttempt, substrate, qualityTarget, surfaceType]);

  const templateName = (tpl: WorkflowTemplateRead): string => {
    if (tpl.display_name) return tpl.display_name;
    if (tpl.name_key) {
      const localized = resolveKey(t, tpl.name_key);
      if (localized !== tpl.name_key) return localized;
    }
    return tpl.code;
  };

  const itemName = (item: SurfacePriceItemSummaryRead | null): string => {
    if (!item) return t.work_plan.unavailable_item;
    if (item.display_name) return item.display_name;
    if (item.name_key) {
      const localized = resolveKey(t, item.name_key);
      if (localized !== item.name_key) return localized;
    }
    return t.work_plan.unavailable_item;
  };

  const selectTemplate = (tpl: WorkflowTemplateRead) => {
    setSelected(tpl);
    setOptionalOn(new Set()); // optional steps always start OFF
    setMode('APPEND');
    setConfirming(false);
    setReviewing(false);
    setError(null);
  };

  const backToList = () => {
    setSelected(null);
    setOptionalOn(new Set());
    setConfirming(false);
    setReviewing(false);
    setError(null);
  };

  const toggleOptional = (stepId: string) => {
    setOptionalOn((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) next.delete(stepId);
      else next.add(stepId);
      return next;
    });
    setConfirming(false);
    setError(null);
  };

  const steps = selected?.steps ?? [];
  const chosen = steps.filter((s) => !s.is_optional || optionalOn.has(s.id));
  const requiredArchived = steps.some((s) => !s.is_optional && (!s.price_item || s.price_item.is_archived));
  const missingKeys = occurrenceKeys.some((k) => k === null);
  const replaceBlocked = mode === 'REPLACE' && missingKeys;
  const canApply = !!selected && chosen.length > 0 && !requiredArchived && !replaceBlocked && !applying;
  const chosenRequired = chosen.filter((s) => !s.is_optional).length;
  const chosenOptional = chosen.length - chosenRequired;
  // Live pre-apply summary: required steps always count, optional ones only
  // when checked. Mirrors what the server will materialize (never sent).
  type PluralForms = { one: string; few: string; many: string; other: string };
  const plural = (forms: PluralForms, count: number): string => {
    const category = new Intl.PluralRules(locale).select(count) as keyof PluralForms;
    return (forms[category] ?? forms.other).replace('{count}', String(count));
  };
  const summaryHeadline = plural(
    mode === 'REPLACE' ? t.work_plan.tpl_summary_replace : t.work_plan.tpl_summary_add,
    chosen.length,
  );
  const summaryBreakdown = [
    steps.some((s) => !s.is_optional) ? plural(t.work_plan.tpl_summary_required, chosenRequired) : null,
    steps.some((s) => s.is_optional) ? plural(t.work_plan.tpl_summary_optional, chosenOptional) : null,
  ]
    .filter((part): part is string => part !== null)
    .join(' + ');

  // Current-state fact only: how many occurrences of the same PriceItem the
  // plan already holds. Not provenance -- an existing row may be manual.
  const inPlanCount = (priceItemId: string): number =>
    planPriceItemIds.filter((id) => id === priceItemId).length;
  const duplicatesInChosen = chosen.filter((s) => inPlanCount(s.price_item_id) > 0).length;
  const reviewChosen = chosen.filter((s) => reviewOn.has(s.id));
  const reviewRequired = reviewChosen.filter((s) => !s.is_optional).length;
  const reviewSkipped = chosen.length - reviewChosen.length;
  const reviewHeadline = plural(t.work_plan.tpl_summary_add, reviewChosen.length);
  const reviewBreakdown = [
    chosen.some((s) => !s.is_optional) ? plural(t.work_plan.tpl_summary_required, reviewRequired) : null,
    chosen.some((s) => s.is_optional)
      ? plural(t.work_plan.tpl_summary_optional, reviewChosen.length - reviewRequired)
      : null,
  ]
    .filter((part): part is string => part !== null)
    .join(' + ');

  const openReview = () => {
    // New candidates start checked; a candidate whose PriceItem is already in
    // the plan starts SKIPPED so nothing is duplicated by accident.
    setReviewOn(new Set(chosen.filter((s) => inPlanCount(s.price_item_id) === 0).map((s) => s.id)));
    setReviewing(true);
    setError(null);
  };

  const toggleReview = (stepId: string) => {
    setReviewOn((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) next.delete(stepId);
      else next.add(stepId);
      return next;
    });
    setError(null);
  };

  const buildRequest = (): ApplyTemplateRequest | null => {
    if (!selected) return null;
    const semantic = {
      template_id: selected.id,
      mode,
      // Server authority: PriceItems, order, notes and waits come from the
      // template. APPEND sends the reviewed step ids; REPLACE keeps the 13E.3
      // rule (all required + the explicit optional choices).
      ...(mode === 'REPLACE'
        ? {
          selected_optional_step_ids: steps.filter((s) => s.is_optional && optionalOn.has(s.id)).map((s) => s.id),
          expected_step_ids: steps.map((s) => s.id),
          expected_occurrence_keys: occurrenceKeys as string[],
          replace_confirmed: true,
        }
        : {
          selected_optional_step_ids: [],
          selected_step_ids: reviewChosen.map((s) => s.id),
          expected_step_ids: steps.map((s) => s.id),
        }),
    };
    // The client-side signature also covers the current plan composition,
    // so a reloaded/changed plan is a new command even for APPEND.
    const signature = JSON.stringify({ ...semantic, plan: occurrenceKeys });
    if (!attempt.current || attempt.current.signature !== signature) {
      attempt.current = { applicationId: newApplicationId(), signature };
    }
    return { application_id: attempt.current.applicationId, ...semantic };
  };

  const submit = async () => {
    const ready = reviewing ? reviewChosen.length > 0 && !applying : canApply;
    if (!ready || inFlight.current) return;
    const request = buildRequest();
    if (!request) return;
    inFlight.current = true;
    setApplying(true);
    setError(null);
    try {
      const plan = await applyTemplateToWorkPlan(projectId, roomId, surfaceId, request);
      attempt.current = null;
      onApplied(plan);
    } catch (err) {
      const kind = classifyApplyTemplateError(err);
      if (kind === 'transport') {
        setError({ kind: 'transport' }); // same id on retry
      } else if (kind === 'stale_template' || kind === 'stale_plan') {
        setConfirming(false);
        setReviewing(false);
        setError({ kind });
      } else if (kind === 'template_unavailable') {
        setError({ kind });
        setSelected(null);
        setConfirming(false);
        setReviewing(false);
        setListAttempt((n) => n + 1); // reload the list; never retry automatically
      } else {
        setConfirming(false);
        setError({ kind: 'error', detail: localizeApiError(err, t) });
      }
    } finally {
      inFlight.current = false;
      setApplying(false);
    }
  };

  const handleApplyClick = () => {
    if (!canApply) return;
    if (mode === 'REPLACE') {
      setConfirming(true); // destructive action needs a second, explicit step
      return;
    }
    // APPEND never mutates straight from the preview: the final review shows
    // every candidate occurrence first. No "already applied" gate from
    // template_applications -- that is history, not current state (FIX.3).
    openReview();
  };

  const refreshTemplate = async () => {
    if (!selected) return;
    setRefreshing(true);
    try {
      const fresh = await fetchWorkflowTemplate(selected.id);
      setError(null);
      if (fresh.is_archived) {
        setError({ kind: 'template_unavailable' });
        setSelected(null);
        setListAttempt((n) => n + 1);
      } else {
        selectTemplate(fresh);
      }
    } catch (err) {
      if (classifyApplyTemplateError(err) === 'template_unavailable') {
        setError({ kind: 'template_unavailable' });
        setSelected(null);
        setListAttempt((n) => n + 1);
      } else {
        setError({ kind: 'error', detail: localizeApiError(err, t) });
      }
    } finally {
      setRefreshing(false);
    }
  };

  const optionalCount = (tpl: WorkflowTemplateRead) => tpl.steps.filter((s) => s.is_optional).length;

  const errorBlock = useMemo(() => {
    if (!error) return null;
    const text =
      error.kind === 'stale_template' ? t.work_plan.tpl_stale_template
        : error.kind === 'stale_plan' ? t.work_plan.tpl_stale_plan
          : error.kind === 'template_unavailable' ? t.work_plan.tpl_unavailable
            : error.kind === 'transport' ? t.work_plan.tpl_transport_error
              : t.work_plan.tpl_error;
    return { text, detail: error.kind === 'error' ? error.detail : null };
  }, [error, t]);

  const btnSecondary =
    'w-full min-h-11 px-3 rounded-xl border border-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-color)] font-semibold text-sm disabled:opacity-60';
  const btnPrimary =
    'w-full min-h-11 px-3 rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] font-semibold text-sm disabled:opacity-60';

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={`template-sheet-title-${surfaceId}`}
    >
      <div
        aria-label={`template-sheet-${surfaceId}`}
        className="w-full max-w-lg bg-[var(--tg-theme-bg-color,#ffffff)] rounded-t-2xl sm:rounded-2xl shadow-xl flex flex-col max-h-[90vh] overflow-hidden"
      >
        <div className="p-4 border-b border-slate-200 flex items-start justify-between gap-2">
          <h2
            id={`template-sheet-title-${surfaceId}`}
            className="flex-1 min-w-0 text-lg font-semibold text-[var(--tg-theme-text-color,#0f172a)] break-words"
          >
            {selected ? templateName(selected) : t.work_plan.tpl_title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={applying}
            aria-label={t.common.close}
            className="shrink-0 min-h-[44px] min-w-[44px] flex items-center justify-center text-slate-400 rounded-lg disabled:opacity-60"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          {!selected && listState === 'loading' && (
            <p role="status" className="text-sm text-[var(--tg-theme-hint-color)]">{t.work_plan.tpl_loading}</p>
          )}
          {!selected && listState === 'error' && (
            <div role="alert" className="space-y-2">
              <p className="text-sm text-[var(--tg-theme-destructive-text-color)]">{t.work_plan.tpl_load_error}</p>
              <button type="button" className={btnSecondary} onClick={() => setListAttempt((n) => n + 1)}>
                {t.work_plan.retry}
              </button>
            </div>
          )}
          {!selected && listState === 'ready' && templates.length === 0 && (
            <p aria-label={`template-empty-${surfaceId}`} className="text-sm text-[var(--tg-theme-hint-color)] break-words">
              {t.work_plan.tpl_empty}
            </p>
          )}
          {!selected && listState === 'ready' && templates.length > 0 && (
            <ul aria-label={`template-list-${surfaceId}`} className="space-y-2">
              {templates.map((tpl) => (
                <li key={tpl.id}>
                  <button
                    type="button"
                    aria-label={`template-option-${tpl.id}`}
                    onClick={() => selectTemplate(tpl)}
                    className="w-full min-h-11 text-left rounded-xl border border-[var(--tg-control-border-color)] p-3 space-y-1"
                  >
                    <span className="block text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">
                      {templateName(tpl)}
                    </span>
                    <span className="block text-xs text-[var(--tg-theme-hint-color)] break-words">
                      {t.work_plan.tpl_steps_count.replace('{count}', String(tpl.steps.length))}
                      {optionalCount(tpl) > 0 &&
                        ` · ${t.work_plan.tpl_optional_count.replace('{count}', String(optionalCount(tpl)))}`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {selected && !reviewing && (
            <>
              <button type="button" className={btnSecondary} onClick={backToList} disabled={applying}>
                {t.work_plan.tpl_back}
              </button>
              {selected.description && (
                <p className="text-xs text-[var(--tg-theme-hint-color)] whitespace-pre-line break-words">
                  {selected.description}
                </p>
              )}
              <ol aria-label={`template-steps-${surfaceId}`} className="space-y-2">
                {steps.map((step, index) => {
                  const archived = !step.price_item || step.price_item.is_archived;
                  const on = !step.is_optional || optionalOn.has(step.id);
                  return (
                    <li
                      key={step.id}
                      aria-label={`template-step-${step.id}`}
                      className="rounded-xl border border-[var(--tg-control-border-color)] p-3 space-y-1"
                    >
                      <div className="flex items-start gap-2">
                        <span className="shrink-0 text-sm font-semibold text-[var(--tg-theme-hint-color)]">{index + 1}.</span>
                        <span className="flex-1 min-w-0 text-sm font-medium text-[var(--tg-theme-text-color)] break-words">
                          {itemName(step.price_item)}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span
                          className={
                            step.is_optional
                              ? 'px-2 py-0.5 rounded-full bg-slate-100 text-slate-700'
                              : 'px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium'
                          }
                        >
                          {step.is_optional ? t.work_plan.tpl_optional : t.work_plan.tpl_required}
                        </span>
                        {step.wait_after_hours !== null && (
                          <span className="text-[var(--tg-theme-hint-color)] break-words">
                            {t.work_plan.tpl_wait.replace('{hours}', String(step.wait_after_hours))}
                          </span>
                        )}
                        {archived && (
                          <span className="text-[var(--tg-theme-destructive-text-color)] break-words">
                            {t.work_plan.tpl_archived_item}
                          </span>
                        )}
                      </div>
                      {step.note && (
                        <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{step.note}</p>
                      )}
                      {step.is_optional && (
                        <label className="flex items-center gap-3 min-h-11 cursor-pointer">
                          <input
                            type="checkbox"
                            aria-label={`template-optional-${step.id}`}
                            checked={on}
                            disabled={archived || applying}
                            onChange={() => toggleOptional(step.id)}
                            className="h-6 w-6 shrink-0"
                          />
                          <span className="text-sm text-[var(--tg-theme-text-color)]">{t.work_plan.tpl_include}</span>
                        </label>
                      )}
                    </li>
                  );
                })}
              </ol>
              {requiredArchived && (
                <p role="alert" className="text-sm text-[var(--tg-theme-destructive-text-color)] break-words">
                  {t.work_plan.tpl_required_archived}
                </p>
              )}
              {!requiredArchived && chosen.length === 0 && (
                <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{t.work_plan.tpl_no_steps}</p>
              )}

              <fieldset className="space-y-2" aria-label={`template-mode-${surfaceId}`}>
                <legend className="text-sm font-semibold text-[var(--tg-theme-text-color)]">{t.work_plan.tpl_mode_label}</legend>
                {(['APPEND', 'REPLACE'] as const).map((value) => (
                  <label
                    key={value}
                    className="flex items-center gap-3 min-h-11 rounded-xl border border-[var(--tg-control-border-color)] px-3 cursor-pointer"
                  >
                    <input
                      type="radio"
                      name={`template-mode-${surfaceId}`}
                      aria-label={`template-mode-${value}`}
                      checked={mode === value}
                      disabled={applying}
                      onChange={() => {
                        setMode(value);
                        setConfirming(false);
                        setError(null);
                      }}
                      className="h-5 w-5 shrink-0"
                    />
                    <span className="text-sm text-[var(--tg-theme-text-color)] break-words">
                      {value === 'APPEND' ? t.work_plan.tpl_mode_append : t.work_plan.tpl_mode_replace}
                    </span>
                  </label>
                ))}
                <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">
                  {mode === 'APPEND' ? t.work_plan.tpl_append_info : t.work_plan.tpl_replace_info}
                </p>
                {mode === 'REPLACE' && (
                  <div aria-label={`template-replace-impact-${surfaceId}`} className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900 space-y-1">
                    <p className="font-semibold">{t.work_plan.tpl_impact_title}</p>
                    <p>{t.work_plan.tpl_impact_works.replace('{count}', String(occurrenceKeys.length))}</p>
                    <p>{t.work_plan.tpl_impact_coefficients.replace('{count}', String(coefficientAssignmentCount))}</p>
                    <p className="pt-1">{t.work_plan.tpl_estimate_note}</p>
                  </div>
                )}
                {replaceBlocked && (
                  <p role="alert" className="text-sm text-[var(--tg-theme-destructive-text-color)] break-words">
                    {t.work_plan.tpl_missing_keys}
                  </p>
                )}
              </fieldset>
            </>
          )}

          {selected && reviewing && (
            <div className="space-y-2">
              <h3 className="text-base font-semibold text-[var(--tg-theme-text-color)] break-words">
                {t.work_plan.tpl_review_title}
              </h3>
              <ol aria-label={`template-review-${surfaceId}`} className="space-y-2">
                {chosen.map((step, index) => {
                  const on = reviewOn.has(step.id);
                  const inPlan = inPlanCount(step.price_item_id);
                  // Earlier CHECKED candidates of this same batch with the same PriceItem.
                  const earlierInBatch = chosen
                    .slice(0, index)
                    .filter((s) => s.price_item_id === step.price_item_id && reviewOn.has(s.id)).length;
                  const flagged = inPlan > 0 || earlierInBatch > 0;
                  return (
                    <li
                      key={step.id}
                      aria-label={`template-review-step-${step.id}`}
                      className={`rounded-xl border p-3 space-y-1 ${
                        flagged ? 'border-amber-300 bg-amber-50/60' : 'border-[var(--tg-control-border-color)]'
                      }`}
                    >
                      <label className="flex items-start gap-3 min-h-11 cursor-pointer">
                        <input
                          type="checkbox"
                          aria-label={`template-review-toggle-${step.id}`}
                          checked={on}
                          disabled={applying}
                          onChange={() => toggleReview(step.id)}
                          className="h-6 w-6 shrink-0 mt-0.5"
                        />
                        <span className="flex-1 min-w-0 text-sm font-medium text-[var(--tg-theme-text-color)] break-words">
                          {itemName(step.price_item)}
                        </span>
                      </label>
                      <div className="flex flex-wrap items-center gap-2 text-xs pl-9">
                        <span
                          className={
                            step.is_optional
                              ? 'px-2 py-0.5 rounded-full bg-slate-100 text-slate-700'
                              : 'px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium'
                          }
                        >
                          {step.is_optional ? t.work_plan.tpl_optional : t.work_plan.tpl_required}
                        </span>
                        {inPlan > 0 && (
                          <span
                            aria-label={`template-review-in-plan-${step.id}`}
                            className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 font-medium break-words"
                          >
                            <span aria-hidden="true">⚠ </span>{t.work_plan.tpl_review_in_plan.replace('{count}', String(inPlan))}
                          </span>
                        )}
                        {earlierInBatch > 0 && (
                          <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 break-words">
                            {t.work_plan.tpl_review_in_batch.replace('{count}', String(earlierInBatch))}
                          </span>
                        )}
                        <span
                          aria-label={`template-review-status-${step.id}`}
                          className={on ? 'text-green-700 font-medium' : 'text-[var(--tg-theme-hint-color)]'}
                        >
                          {on ? t.work_plan.tpl_review_will_add : t.work_plan.tpl_review_skipped}
                        </span>
                      </div>
                      {inPlan > 0 && (
                        <p className="text-xs text-amber-900 break-words pl-9">{t.work_plan.tpl_review_in_plan_hint}</p>
                      )}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}

          {errorBlock && (
            <div role="alert" aria-label={`template-apply-error-${surfaceId}`} className="space-y-2">
              <p className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">{errorBlock.text}</p>
              {errorBlock.detail && errorBlock.detail !== errorBlock.text && (
                <p className="text-xs text-[var(--tg-theme-destructive-text-color)] break-words">{errorBlock.detail}</p>
              )}
              {error?.kind === 'transport' && (
                <button type="button" className={btnSecondary} onClick={() => void submit()} disabled={applying}>
                  {t.work_plan.tpl_retry}
                </button>
              )}
              {selected && (error?.kind === 'stale_template' || error?.kind === 'error') && (
                <button
                  type="button"
                  aria-label={`template-refresh-${surfaceId}`}
                  className={btnSecondary}
                  onClick={() => void refreshTemplate()}
                  disabled={refreshing || applying}
                >
                  {t.work_plan.tpl_refresh_template}
                </button>
              )}
              {error?.kind === 'stale_plan' && (
                <button
                  type="button"
                  aria-label={`template-reload-plan-${surfaceId}`}
                  className={btnSecondary}
                  onClick={onReloadPlan}
                >
                  {t.work_plan.reload_plan}
                </button>
              )}
            </div>
          )}
        </div>

        {selected && (
          <div className="p-4 border-t border-slate-200 space-y-2">
            {/* Pinned above the Apply action so the result is visible without scrolling. */}
            {!reviewing && chosen.length > 0 && !requiredArchived && (
              <div
                aria-label={`template-summary-${surfaceId}`}
                aria-live="polite"
                className={
                  mode === 'REPLACE'
                    ? 'rounded-xl bg-amber-50 text-amber-900 p-3 space-y-0.5'
                    : 'rounded-xl bg-blue-50 text-blue-900 p-3 space-y-0.5'
                }
              >
                <p className="text-sm font-semibold break-words">{summaryHeadline}</p>
                {summaryBreakdown && <p className="text-xs break-words">{summaryBreakdown}</p>}
                {mode === 'REPLACE' && (
                  <p className="text-xs font-medium break-words">
                    {t.work_plan.tpl_summary_replace_existing.replace('{count}', String(occurrenceKeys.length))}
                  </p>
                )}
                {mode === 'APPEND' && duplicatesInChosen > 0 && (
                  <p className="text-xs font-medium break-words">
                    {t.work_plan.tpl_summary_in_plan_note.replace('{count}', String(duplicatesInChosen))}
                  </p>
                )}
              </div>
            )}
            {reviewing ? (
              <div className="space-y-2">
                <div
                  aria-label={`template-review-summary-${surfaceId}`}
                  aria-live="polite"
                  className="rounded-xl bg-blue-50 text-blue-900 p-3 space-y-0.5"
                >
                  <p className="text-sm font-semibold break-words">{reviewHeadline}</p>
                  {reviewChosen.length > 0 && reviewBreakdown && <p className="text-xs break-words">{reviewBreakdown}</p>}
                  {reviewSkipped > 0 && (
                    <p className="text-xs break-words">
                      {t.work_plan.tpl_review_skipped_count.replace('{count}', String(reviewSkipped))}
                    </p>
                  )}
                </div>
                {reviewChosen.length === 0 && (
                  <p role="alert" className="text-sm text-[var(--tg-theme-destructive-text-color)] break-words">
                    {t.work_plan.tpl_review_none}
                  </p>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    className={btnSecondary}
                    onClick={() => {
                      setReviewing(false);
                      setError(null);
                    }}
                    disabled={applying}
                  >
                    {t.work_plan.tpl_review_back}
                  </button>
                  <button
                    type="button"
                    aria-label={`template-review-confirm-${surfaceId}`}
                    className={btnPrimary}
                    onClick={() => void submit()}
                    disabled={applying || reviewChosen.length === 0}
                  >
                    {applying ? t.work_plan.tpl_applying : t.work_plan.tpl_review_confirm}
                  </button>
                </div>
              </div>
            ) : confirming ? (
              <div role="alertdialog" aria-label={`template-replace-confirm-${surfaceId}`} className="space-y-2">
                <p className="text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">{t.work_plan.tpl_confirm_title}</p>
                <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{t.work_plan.tpl_confirm_body}</p>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" className={btnSecondary} onClick={() => setConfirming(false)} disabled={applying}>
                    {t.work_plan.tpl_confirm_cancel}
                  </button>
                  <button
                    type="button"
                    aria-label={`template-replace-confirm-yes-${surfaceId}`}
                    onClick={() => void submit()}
                    disabled={applying}
                    className="w-full min-h-11 px-3 rounded-xl bg-red-600 text-white font-semibold text-sm disabled:opacity-60"
                  >
                    {applying ? t.work_plan.tpl_applying : t.work_plan.tpl_confirm_replace}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                aria-label={`template-apply-${surfaceId}`}
                className={btnPrimary}
                onClick={handleApplyClick}
                disabled={!canApply}
              >
                {applying ? t.work_plan.tpl_applying : t.work_plan.tpl_apply}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
