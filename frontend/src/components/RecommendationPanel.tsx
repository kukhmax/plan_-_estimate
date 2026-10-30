import { useEffect, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { resolveKey } from '../utils/i18nKeys';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';
import { formatPrice } from '../utils/priceFormat';
import { quantityOf } from '../utils/format';
import { ApiError } from '../api/http';
import {
  acceptWorkRecommendation,
  dismissWorkRecommendation,
  evaluateWorkRecommendations,
  fetchWorkRecommendations,
  reconsiderWorkRecommendation,
} from '../api/workRecommendations';
import {
  WorkRecommendationActivityValue,
  WorkRecommendationRead,
  WorkRecommendationStatusValue,
} from '../types/workRecommendation';
import { RecommendationPriceItemPicker } from './RecommendationPriceItemPicker';
import { Ico } from './Ico';

export interface RecommendationPanelProps {
  projectId: string;
  roomId: string;
  inspectionId: string;
  /** UX walk B6: the inspection flow evaluated the recommendations right after "Zakończ" (an empty list then says "none found"). */
  evaluated?: boolean;
}

const ACTIVITY_VALUES: WorkRecommendationActivityValue[] = ['active', 'resolved', 'all'];

const STATUS_LABEL_KEY: Record<
  WorkRecommendationStatusValue,
  'status_pending' | 'status_accepted' | 'status_dismissed'
> = {
  PENDING: 'status_pending',
  ACCEPTED: 'status_accepted',
  DISMISSED: 'status_dismissed',
};

function localizedServiceError(
  t: ReturnType<typeof useI18n>['t'],
  err: unknown,
  fallback: string,
): string {
  const message = err instanceof Error ? err.message : '';
  if (message.includes('COMPLETED') || message.includes('completed')) {
    return t.recommendations.error_not_completed;
  }
  if (message.includes('not found') || message.includes('Not found')) {
    return t.recommendations.error_not_found;
  }
  if (message.includes('already-accepted')) {
    return t.recommendations.error_conflict;
  }
  return fallback;
}

function localizedAcceptError(
  t: ReturnType<typeof useI18n>['t'],
  err: unknown,
  fallback: string,
): string {
  if (err instanceof ApiError) {
    if (err.status === 404 && err.message === 'Target surface has no work plan yet') {
      return t.recommendations.missing_work_plan;
    }
    if (err.status === 404) {
      return t.recommendations.error_not_found;
    }
    if (err.status === 409) {
      return t.recommendations.error_conflict;
    }
    if (err.status === 422) {
      return t.recommendations.error_invalid_selection;
    }
  }
  return fallback;
}

function activityLabel(
  t: ReturnType<typeof useI18n>['t'],
  value: WorkRecommendationActivityValue,
): string {
  if (value === 'resolved') return t.recommendations.status_resolved;
  if (value === 'all') return t.recommendations.status_all;
  return t.recommendations.status_active;
}

function recommendationTitle(
  t: ReturnType<typeof useI18n>['t'],
  recommendation: WorkRecommendationRead,
): string {
  const summary = recommendation.current_price_item;
  if (summary?.display_name) return summary.display_name;
  if (summary?.name_key) {
    const localized = resolveKey(t, summary.name_key);
    if (localized !== summary.name_key) return localized;
  }
  return recommendation.recommended_work_code;
}

export function RecommendationPanel({ projectId, roomId, inspectionId, evaluated = false }: RecommendationPanelProps) {
  const { t } = useI18n();
  const [activity, setActivity] = useState<WorkRecommendationActivityValue>('active');
  const [items, setItems] = useState<WorkRecommendationRead[]>([]);
  const [optionsOpen, setOptionsOpen] = useState<string[]>([]);
  const [pending, setPending] = useState<string[]>([]);
  const [fallbackOpen, setFallbackOpen] = useState<string[]>([]);
  const [accepting, setAccepting] = useState<string[]>([]);
  const [justAccepted, setJustAccepted] = useState<string[]>([]);
  const [confirmAgain, setConfirmAgain] = useState<string[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // UX walk A5: "Dodaj wszystkie do prac" -- every card that can go into a plan, one per work and wall, nothing that is already in the plan
  const [allBusy, setAllBusy] = useState(false);
  const [allDone, setAllDone] = useState<string | null>(null);
  // Session-local only (never persisted): distinguishes "never evaluated
  // yet" from "evaluated successfully and found zero" so the primary action
  // doesn't look like it silently did nothing. Reset on remount (a fresh
  // inspection panel), not carried across inspections.
  const [hasEvaluated, setHasEvaluated] = useState(evaluated);

  function forThisInspection(all: WorkRecommendationRead[]): WorkRecommendationRead[] {
    return all.filter((item) => item.inspection_id === inspectionId);
  }

  useEffect(() => {
    let cancelled = false;
    async function loadInitial(): Promise<void> {
      setListLoading(true);
      setError(null);
      try {
        // Ordinary render/list only ever GETs -- it never triggers evaluation.
        const response = await fetchWorkRecommendations(projectId, roomId, {
          activity: 'active',
        });
        if (cancelled) return;
        setItems(forThisInspection(response.items));
        setActivity('active');
      } catch (err) {
        if (!cancelled) setError(localizedServiceError(t, err, t.recommendations.error_load));
      } finally {
        if (!cancelled) setListLoading(false);
      }
    }
    void loadInitial();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, roomId, inspectionId]);

  async function switchActivity(next: WorkRecommendationActivityValue): Promise<void> {
    if (next === activity) return;
    setActivity(next);
    setListLoading(true);
    setError(null);
    try {
      const response = await fetchWorkRecommendations(projectId, roomId, { activity: next });
      setItems(forThisInspection(response.items));
    } catch (err) {
      setError(localizedServiceError(t, err, t.recommendations.error_load));
    } finally {
      setListLoading(false);
    }
  }

  async function handleEvaluate(): Promise<void> {
    setEvaluating(true);
    setError(null);
    try {
      const response = await evaluateWorkRecommendations(projectId, roomId);
      setItems(forThisInspection(response.items));
      setActivity('active');
      setHasEvaluated(true);
    } catch (err) {
      setError(localizedServiceError(t, err, t.recommendations.error_evaluate));
    } finally {
      setEvaluating(false);
    }
  }

  function toggleOptions(id: string): void {
    setOptionsOpen((prev) =>
      prev.includes(id) ? prev.filter((entry) => entry !== id) : [...prev, id],
    );
  }

  async function handleDismiss(id: string): Promise<void> {
    setPending((prev) => [...prev, id]);
    setError(null);
    try {
      const updated = await dismissWorkRecommendation(projectId, id);
      setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
    } catch (err) {
      setError(localizedServiceError(t, err, t.recommendations.error_dismiss));
    } finally {
      setPending((prev) => prev.filter((entry) => entry !== id));
    }
  }

  async function handleReconsider(id: string): Promise<void> {
    setPending((prev) => [...prev, id]);
    setError(null);
    try {
      const updated = await reconsiderWorkRecommendation(projectId, id);
      setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
    } catch (err) {
      setError(localizedServiceError(t, err, t.recommendations.error_reconsider));
    } finally {
      setPending((prev) => prev.filter((entry) => entry !== id));
    }
  }

  async function handleAccept(id: string, priceItemId?: string, quantity?: string): Promise<void> {
    setPending((prev) => [...prev, id]);
    setAccepting((prev) => [...prev, id]);
    setError(null);
    try {
      // Backend owns the atomic WorkPlan append; the frontend never fetches
      // or mutates the SurfaceWorkPlan itself, only submits the recommendation
      // id and (optionally) the owner's manual PriceItem selection.
      const updated = await acceptWorkRecommendation(projectId, id, {
        ...(priceItemId ? { price_item_id: priceItemId } : {}),
        ...(quantity ? { quantity } : {}),
      });
      setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
      setJustAccepted((prev) => [...prev, id]);
      setFallbackOpen((prev) => prev.filter((entry) => entry !== id));
      setConfirmAgain((prev) => prev.filter((entry) => entry !== id));
      // the other cards of the same wall now know that the work is in its plan (Stage 15H.2)
      try {
        const refreshed = await fetchWorkRecommendations(projectId, roomId, { activity });
        setItems(forThisInspection(refreshed.items));
      } catch {
        // the accepted card is already updated; the next list load refreshes the rest
      }
    } catch (err) {
      setError(localizedAcceptError(t, err, t.recommendations.error_accept));
    } finally {
      setPending((prev) => prev.filter((entry) => entry !== id));
      setAccepting((prev) => prev.filter((entry) => entry !== id));
    }
  }

  function askConfirmAgain(id: string): void {
    setConfirmAgain((prev) => (prev.includes(id) ? prev : [...prev, id]));
  }

  function cancelConfirmAgain(id: string): void {
    setConfirmAgain((prev) => prev.filter((entry) => entry !== id));
  }

  function openFallback(id: string): void {
    setFallbackOpen((prev) => (prev.includes(id) ? prev : [...prev, id]));
  }

  function closeFallback(id: string): void {
    setFallbackOpen((prev) => prev.filter((entry) => entry !== id));
  }

  const addable = (() => {
    const seen = new Set<string>();
    return items.filter((item) => {
      const summary = item.current_price_item;
      const ok =
        item.status === 'PENDING' &&
        item.target_kind !== 'ROOM' &&
        item.surface_id !== null &&
        item.in_plan_count === 0 &&
        summary !== null &&
        !summary.is_archived &&
        summary.category !== 'REVEAL';
      const key = `${item.surface_id}:${item.recommended_work_code}`;
      if (!ok || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  })();

  // owner 2026-10-30: the works the area does not measure (metres, pieces) ask for their quantity before "Dodaj wszystkie"
  const needingQuantity = addable.filter((item) => needsQuantity(item));
  const [allAsk, setAllAsk] = useState(false);
  const [allQuantities, setAllQuantities] = useState<Record<string, string>>({});
  const allQuantityInvalid = needingQuantity.some((item) => quantityOf(allQuantities[item.id] ?? '') === null);

  async function handleAcceptAll(): Promise<void> {
    if (allBusy || addable.length === 0) return;
    if (needingQuantity.length > 0 && !allAsk) {
      setAllAsk(true);
      return;
    }
    if (allQuantityInvalid) return;
    setAllAsk(false);
    const ids = addable.map((item) => item.id);
    setAllBusy(true);
    setAllDone(null);
    setError(null);
    setPending((prev) => [...prev, ...ids]);
    let done = 0;
    try {
      for (const id of ids) {
        const quantity = quantityOf(allQuantities[id] ?? '');
        const updated = await acceptWorkRecommendation(projectId, id, quantity ? { quantity } : {});
        setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
        setJustAccepted((prev) => [...prev, id]);
        done += 1;
      }
    } catch (err) {
      setError(localizedAcceptError(t, err, t.recommendations.error_accept));
    } finally {
      setPending((prev) => prev.filter((entry) => !ids.includes(entry)));
      setAllBusy(false);
      if (done > 0) setAllDone(t.recommendations.accept_all_done.replace('{n}', String(done)));
      try {
        const refreshed = await fetchWorkRecommendations(projectId, roomId, { activity });
        setItems(forThisInspection(refreshed.items));
      } catch {
        // the accepted cards are already updated; the next list load refreshes the rest
      }
    }
  }

  const anyActive = items.some((item) => item.is_active);

  return (
    <div
      aria-label={t.recommendations.section_title}
      className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-neutral-50 p-3"
    >
      <h4 className="text-sm font-semibold text-neutral-900">
        {t.recommendations.section_title}
      </h4>
      <p className="text-xs text-neutral-600">{t.recommendations.evaluate_hint}</p>

      {error ? (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        aria-label={t.recommendations.evaluate}
        className="min-h-11 rounded-lg bg-blue-600 px-3 font-medium text-white disabled:opacity-50"
        disabled={evaluating}
        onClick={() => void handleEvaluate()}
      >
        {evaluating
          ? t.recommendations.evaluating
          : anyActive
            ? t.recommendations.reevaluate
            : t.recommendations.evaluate}
      </button>

      <div className="flex gap-2" role="group" aria-label={t.recommendations.section_title}>
        {ACTIVITY_VALUES.map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={activity === value}
            className={`min-h-11 flex-1 rounded-lg border px-1 text-sm font-medium ${
              activity === value
                ? 'border-blue-600 bg-blue-50 text-blue-800'
                : 'border-neutral-300 pe-surface text-neutral-700'
            }`}
            onClick={() => void switchActivity(value)}
          >
            {activityLabel(t, value)}
          </button>
        ))}
      </div>

      {listLoading ? (
        <p className="text-sm text-neutral-500">{t.recommendations.loading}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-neutral-500">
          {hasEvaluated && activity === 'active'
            ? t.recommendations.no_recommendations_after_evaluate
            : t.recommendations.no_recommendations}
        </p>
      ) : (
        <>
        {addable.length >= 2 && (
          <button
            type="button"
            aria-label="recommendations-accept-all"
            className="min-h-11 rounded-lg bg-emerald-600 px-3 font-medium text-white disabled:opacity-50"
            disabled={allBusy || allAsk}
            onClick={() => void handleAcceptAll()}
          >
            {allBusy ? t.common.saving : t.recommendations.accept_all.replace('{n}', String(addable.length))}
          </button>
        )}
        {allAsk && needingQuantity.length > 0 && (
          <div aria-label="recommendations-accept-all-quantities" className="flex flex-col gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3">
            <p className="text-sm text-neutral-800 break-words">{t.recommendations.quantity_all_title}</p>
            {needingQuantity.map((item) => (
              <QuantityField
                key={item.id}
                id={`recommendation-all-quantity-${item.id}`}
                label={`${recommendationTitle(t, item)}${item.surface_name ? ` — ${item.surface_name}` : ''}`}
                unit={item.current_price_item?.unit ?? null}
                value={allQuantities[item.id] ?? ''}
                onChange={(value) => setAllQuantities((current) => ({ ...current, [item.id]: value }))}
                t={t}
              />
            ))}
            <p className="text-xs text-neutral-600 break-words">{t.recommendations.quantity_hint}</p>
            {allQuantityInvalid && <p role="alert" className="text-xs text-red-600 break-words">{t.recommendations.quantity_invalid}</p>}
            <button
              type="button"
              aria-label="recommendations-accept-all-confirm"
              className="min-h-11 rounded-lg bg-emerald-600 px-3 font-medium text-white disabled:opacity-50"
              disabled={allBusy || allQuantityInvalid}
              onClick={() => void handleAcceptAll()}
            >
              {t.recommendations.accept_all.replace('{n}', String(addable.length))}
            </button>
            <button
              type="button"
              aria-label="recommendations-accept-all-cancel"
              className="min-h-11 rounded-lg border border-neutral-300 pe-surface px-3 font-medium text-neutral-700"
              onClick={() => setAllAsk(false)}
            >
              {t.common.cancel}
            </button>
          </div>
        )}
        {allDone && <p role="status" className="text-sm text-emerald-700 break-words">{allDone}</p>}
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <RecommendationCard
              key={item.id}
              recommendation={item}
              optionsOpen={optionsOpen.includes(item.id)}
              pending={pending.includes(item.id)}
              accepting={accepting.includes(item.id)}
              fallbackOpen={fallbackOpen.includes(item.id)}
              justAccepted={justAccepted.includes(item.id)}
              confirmAgain={confirmAgain.includes(item.id)}
              onAskConfirmAgain={askConfirmAgain}
              onCancelConfirmAgain={cancelConfirmAgain}
              onToggleOptions={toggleOptions}
              onDismiss={handleDismiss}
              onReconsider={handleReconsider}
              onAccept={handleAccept}
              onOpenFallback={openFallback}
              onCloseFallback={closeFallback}
              t={t}
            />
          ))}
        </ul>
        </>
      )}
    </div>
  );
}

/** A work the area of the surface does not measure (metres, pieces): its quantity is asked when it is added (owner 2026-10-30). */
function needsQuantity(recommendation: WorkRecommendationRead): boolean {
  const unit = recommendation.current_price_item?.unit;
  return unit !== undefined && unit !== 'M2';
}

function QuantityField({ id, label, unit, value, onChange, autoFocus, t }: {
  id: string;
  label: string;
  unit: string | null;
  value: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
  t: ReturnType<typeof useI18n>['t'];
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-sm text-neutral-800">
      <span className="break-words">{label}</span>
      <span className="flex items-center gap-2">
        <input
          id={id}
          aria-label={id}
          inputMode="decimal"
          autoComplete="off"
          autoFocus={autoFocus}
          value={value}
          placeholder="0"
          onChange={(event) => onChange(event.target.value)}
          className="min-h-11 w-28 shrink-0 rounded-lg border border-neutral-300 pe-surface px-3 text-base"
        />
        <span className="text-sm text-neutral-600">{unit ? (t.pricebook.units as Record<string, string>)[unit] ?? unit : ''}</span>
      </span>
    </label>
  );
}

function RecommendationCard({
  recommendation,
  optionsOpen,
  pending,
  accepting,
  fallbackOpen,
  justAccepted,
  confirmAgain,
  onAskConfirmAgain,
  onCancelConfirmAgain,
  onToggleOptions,
  onDismiss,
  onReconsider,
  onAccept,
  onOpenFallback,
  onCloseFallback,
  t,
}: {
  recommendation: WorkRecommendationRead;
  optionsOpen: boolean;
  pending: boolean;
  accepting: boolean;
  fallbackOpen: boolean;
  justAccepted: boolean;
  confirmAgain: boolean;
  onAskConfirmAgain: (id: string) => void;
  onCancelConfirmAgain: (id: string) => void;
  onToggleOptions: (id: string) => void;
  onDismiss: (id: string) => void;
  onReconsider: (id: string) => void;
  onAccept: (id: string, priceItemId?: string, quantity?: string) => void;
  onOpenFallback: (id: string) => void;
  onCloseFallback: (id: string) => void;
  t: ReturnType<typeof useI18n>['t'];
}) {
  const isRoomAdvisory = recommendation.target_kind === 'ROOM';
  const title = recommendationTitle(t, recommendation);
  const summary = recommendation.current_price_item;
  // owner 2026-10-30: a work in metres / pieces asks for its quantity before it goes to the plan (empty = to be set later)
  const askQuantity = needsQuantity(recommendation);
  const [quantityOpen, setQuantityOpen] = useState(false);
  const [quantity, setQuantity] = useState('');
  const quantityInvalid = quantityOf(quantity) === null;
  const statusLabel = t.recommendations[STATUS_LABEL_KEY[recommendation.status]];
  const inactiveSince = recommendation.resolved_at
    ? t.recommendations.inactive_since.replace('{date}', recommendation.resolved_at.slice(0, 10))
    : null;
  const hasLifecycleAction =
    recommendation.status === 'PENDING' || recommendation.status === 'DISMISSED';

  const surfaceLabel = recommendation.surface_name
    ? getSurfaceDisplayName(
        { name: recommendation.surface_name, surface_type: recommendation.surface_type },
        { wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling },
      )
    : null;
  const reasonResolved = recommendation.reason_key ? resolveKey(t, recommendation.reason_key) : null;
  const reasonLabel = reasonResolved && reasonResolved !== recommendation.reason_key ? reasonResolved : null;
  const isPending = recommendation.status === 'PENDING';
  const isActionableTarget = !isRoomAdvisory;
  const canAcceptNormally =
    isPending &&
    isActionableTarget &&
    summary !== null &&
    !summary.is_archived &&
    summary.category !== 'REVEAL';
  const needsFallback = isPending && isActionableTarget && !canAcceptNormally;

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-neutral-200 pe-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center rounded-full border border-neutral-300 bg-neutral-100 px-2 py-0.5 text-xs font-semibold text-neutral-700">
          {statusLabel}
        </span>
        {!recommendation.is_active ? (
          <span className="inline-flex items-center rounded-full border border-neutral-300 bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-600">
            {t.recommendations.inactive_badge}
          </span>
        ) : null}
        {isRoomAdvisory ? (
          <span className="inline-flex items-center rounded-full border border-blue-300 bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-800">
            {t.recommendations.room_advisory_badge}
          </span>
        ) : null}
        {summary?.is_archived ? (
          <span className="inline-flex items-center rounded-full border border-orange-300 bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
            {t.pricebook.archived_badge}
          </span>
        ) : null}
      </div>

      <p className="font-semibold text-neutral-900 break-words">{title}</p>

      {surfaceLabel ? (
        <p className="text-xs text-neutral-700 break-words">
          {t.recommendations.context_surface.replace('{name}', surfaceLabel)}
        </p>
      ) : null}
      {reasonLabel ? (
        <p className="text-xs text-neutral-700 break-words">
          {t.recommendations.context_reason.replace('{reason}', reasonLabel)}
        </p>
      ) : null}

      {isRoomAdvisory ? (
        <p className="text-xs text-neutral-600">{t.recommendations.room_advisory_hint}</p>
      ) : null}

      {summary ? (
        <p className="text-xs text-neutral-700">
          {summary.price === null
            ? t.pricebook.price_not_set
            : `${formatPrice(summary.price)} ${
                summary.currency === 'PLN' ? t.pricebook.currency_symbol : summary.currency
              }`}
          {' / '}
          {t.pricebook.units[summary.unit]}
        </p>
      ) : (
        <p className="text-xs text-neutral-500">{t.recommendations.price_item_missing}</p>
      )}

      {inactiveSince ? (
        <p className="text-xs text-neutral-500">{inactiveSince}</p>
      ) : null}

      {needsFallback && summary !== null ? (
        <p className="text-xs text-neutral-500">{t.recommendations.action_unavailable}</p>
      ) : null}

      {recommendation.status === 'ACCEPTED' && justAccepted ? (
        <p className="text-xs text-green-700">{t.recommendations.accept_success}</p>
      ) : null}

      {isPending && recommendation.in_plan_count > 0 ? (
        <p role="note" className="rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-900 break-words">
          {t.recommendations.note_already_in_plan.replace('{count}', String(recommendation.in_plan_count))}
        </p>
      ) : null}
      {isPending && recommendation.in_plan_count === 0 && recommendation.same_work_other_cards > 0 ? (
        <p role="note" className="rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-900 break-words">
          {t.recommendations.note_same_work_elsewhere}
        </p>
      ) : null}
      {recommendation.status === 'ACCEPTED' && recommendation.in_plan_count > 1 ? (
        <p role="note" className="rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-900 break-words">
          {t.recommendations.note_already_in_plan.replace('{count}', String(recommendation.in_plan_count))}
        </p>
      ) : null}

      {canAcceptNormally && confirmAgain ? (
        <div role="alertdialog" aria-label={`${title} — ${t.recommendations.confirm_again_question}`} className="flex flex-col gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3">
          <p className="text-sm text-amber-900 break-words">{t.recommendations.confirm_again_question}</p>
          <button
            type="button"
            aria-label={`${title} — ${t.recommendations.confirm_again_yes}`}
            className="min-h-11 rounded-lg bg-blue-600 px-3 font-medium text-white disabled:opacity-50"
            disabled={pending}
            onClick={() => (askQuantity ? setQuantityOpen(true) : onAccept(recommendation.id))}
          >
            {accepting ? t.recommendations.accepting : t.recommendations.confirm_again_yes}
          </button>
          <button
            type="button"
            aria-label={`${title} — ${t.recommendations.confirm_again_no}`}
            className="min-h-11 rounded-lg border border-neutral-300 pe-surface px-3 font-medium text-neutral-700 disabled:opacity-50"
            disabled={pending}
            onClick={() => onCancelConfirmAgain(recommendation.id)}
          >
            <Ico>✅</Ico>{t.recommendations.confirm_again_no}
          </button>
        </div>
      ) : null}

      {canAcceptNormally && quantityOpen ? (
        <div aria-label={`recommendation-quantity-${recommendation.id}`} className="flex flex-col gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3">
          <QuantityField
            id={`recommendation-quantity-input-${recommendation.id}`}
            label={t.recommendations.quantity_label}
            unit={summary?.unit ?? null}
            value={quantity}
            onChange={setQuantity}
            autoFocus
            t={t}
          />
          <p className="text-xs text-neutral-600 break-words">{t.recommendations.quantity_hint}</p>
          {quantityInvalid && <p role="alert" className="text-xs text-red-600 break-words">{t.recommendations.quantity_invalid}</p>}
          <button
            type="button"
            aria-label={`recommendation-quantity-confirm-${recommendation.id}`}
            className="min-h-11 rounded-lg bg-blue-600 px-3 font-medium text-white disabled:opacity-50"
            disabled={pending || quantityInvalid}
            onClick={() => onAccept(recommendation.id, undefined, quantityOf(quantity) || undefined)}
          >
            {accepting ? t.recommendations.accepting : t.recommendations.accept}
          </button>
          <button
            type="button"
            aria-label={`recommendation-quantity-cancel-${recommendation.id}`}
            className="min-h-11 rounded-lg border border-neutral-300 pe-surface px-3 font-medium text-neutral-700"
            disabled={pending}
            onClick={() => setQuantityOpen(false)}
          >
            {t.common.cancel}
          </button>
        </div>
      ) : null}

      {canAcceptNormally && !confirmAgain && !quantityOpen ? (
        <button
          type="button"
          aria-label={`${title} — ${t.recommendations.accept}`}
          className="min-h-11 rounded-lg bg-blue-600 px-3 font-medium text-white disabled:opacity-50"
          disabled={pending}
          onClick={() =>
            recommendation.in_plan_count > 0
              ? onAskConfirmAgain(recommendation.id)
              : askQuantity
                ? setQuantityOpen(true)
                : onAccept(recommendation.id)
          }
        >
          {accepting ? t.recommendations.accepting : t.recommendations.accept}
        </button>
      ) : null}

      {needsFallback ? (
        fallbackOpen ? (
          <RecommendationPriceItemPicker
            disabled={pending}
            onCancel={() => onCloseFallback(recommendation.id)}
            onConfirm={(item) => onAccept(recommendation.id, item.id)}
          />
        ) : (
          <button
            type="button"
            aria-label={`${title} — ${t.recommendations.fallback_button}`}
            className="min-h-11 self-start rounded-lg border border-neutral-300 px-3 text-sm font-medium text-neutral-700 disabled:opacity-50"
            disabled={pending}
            onClick={() => onOpenFallback(recommendation.id)}
          >
            <Ico>🛠️</Ico>{t.recommendations.fallback_button}
          </button>
        )
      ) : null}

      {hasLifecycleAction ? (
        <>
          <button
            type="button"
            aria-expanded={optionsOpen}
            aria-label={`${title} — ${t.recommendations.options}`}
            className="min-h-11 self-start rounded-lg border border-neutral-300 px-3 text-sm font-medium text-neutral-700"
            onClick={() => onToggleOptions(recommendation.id)}
          >
            {optionsOpen ? t.recommendations.hide_options : t.recommendations.options}
          </button>

          {optionsOpen ? (
            <div className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-neutral-50 p-3">
              {recommendation.status === 'PENDING' ? (
                <button
                  type="button"
                  aria-label={`${title} — ${t.recommendations.dismiss}`}
                  className="min-h-11 rounded-lg border border-neutral-300 px-3 text-sm font-medium text-neutral-700 disabled:opacity-50"
                  disabled={pending}
                  onClick={() => onDismiss(recommendation.id)}
                >
                  <Ico>✖️</Ico>{t.recommendations.dismiss}
                </button>
              ) : null}
              {recommendation.status === 'DISMISSED' ? (
                <button
                  type="button"
                  aria-label={`${title} — ${t.recommendations.reconsider}`}
                  className="min-h-11 rounded-lg border border-neutral-300 px-3 text-sm font-medium text-neutral-700 disabled:opacity-50"
                  disabled={pending}
                  onClick={() => onReconsider(recommendation.id)}
                >
                  <Ico>🔄</Ico>{t.recommendations.reconsider}
                </button>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </li>
  );
}
