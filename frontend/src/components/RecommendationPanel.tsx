import { useEffect, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { resolveKey } from '../utils/i18nKeys';
import { formatPrice } from '../utils/priceFormat';
import {
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

export interface RecommendationPanelProps {
  projectId: string;
  roomId: string;
  inspectionId: string;
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

export function RecommendationPanel({ projectId, roomId, inspectionId }: RecommendationPanelProps) {
  const { t } = useI18n();
  const [activity, setActivity] = useState<WorkRecommendationActivityValue>('active');
  const [items, setItems] = useState<WorkRecommendationRead[]>([]);
  const [optionsOpen, setOptionsOpen] = useState<string[]>([]);
  const [pending, setPending] = useState<string[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
                : 'border-neutral-300 bg-white text-neutral-700'
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
        <p className="text-sm text-neutral-500">{t.recommendations.no_recommendations}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <RecommendationCard
              key={item.id}
              recommendation={item}
              optionsOpen={optionsOpen.includes(item.id)}
              pending={pending.includes(item.id)}
              onToggleOptions={toggleOptions}
              onDismiss={handleDismiss}
              onReconsider={handleReconsider}
              t={t}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function RecommendationCard({
  recommendation,
  optionsOpen,
  pending,
  onToggleOptions,
  onDismiss,
  onReconsider,
  t,
}: {
  recommendation: WorkRecommendationRead;
  optionsOpen: boolean;
  pending: boolean;
  onToggleOptions: (id: string) => void;
  onDismiss: (id: string) => void;
  onReconsider: (id: string) => void;
  t: ReturnType<typeof useI18n>['t'];
}) {
  const isRoomAdvisory = recommendation.target_kind === 'ROOM';
  const title = recommendationTitle(t, recommendation);
  const summary = recommendation.current_price_item;
  const statusLabel = t.recommendations[STATUS_LABEL_KEY[recommendation.status]];
  const inactiveSince = recommendation.resolved_at
    ? t.recommendations.inactive_since.replace('{date}', recommendation.resolved_at.slice(0, 10))
    : null;
  const hasLifecycleAction =
    recommendation.status === 'PENDING' || recommendation.status === 'DISMISSED';

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-white p-3 text-sm">
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

      {hasLifecycleAction ? (
        <>
          <button
            type="button"
            aria-expanded={optionsOpen}
            aria-label={`${title} — ${t.recommendations.options}`}
            className="min-h-10 self-start rounded-lg border border-neutral-300 px-3 text-sm font-medium text-neutral-700"
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
                  className="min-h-10 rounded-lg border border-neutral-300 px-3 text-sm font-medium text-neutral-700 disabled:opacity-50"
                  disabled={pending}
                  onClick={() => onDismiss(recommendation.id)}
                >
                  {t.recommendations.dismiss}
                </button>
              ) : null}
              {recommendation.status === 'DISMISSED' ? (
                <button
                  type="button"
                  aria-label={`${title} — ${t.recommendations.reconsider}`}
                  className="min-h-10 rounded-lg border border-neutral-300 px-3 text-sm font-medium text-neutral-700 disabled:opacity-50"
                  disabled={pending}
                  onClick={() => onReconsider(recommendation.id)}
                >
                  {t.recommendations.reconsider}
                </button>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </li>
  );
}
