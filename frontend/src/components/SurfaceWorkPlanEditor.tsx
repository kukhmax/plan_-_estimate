import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { fetchPriceItems } from '../api/priceItems';
import {
  fetchSurfaceWorkPlan,
  isSurfaceWorkPlanMissing,
  putSurfaceWorkPlan,
} from '../api/workPlans';
import { useI18n } from '../hooks/useI18n';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { PriceItem } from '../types/priceItem';
import {
  SurfacePlannedWorkRead,
  SurfacePriceItemSummaryRead,
  SurfaceWorkPlanRead,
} from '../types/workPlan';
import { localizeApiError } from '../utils/apiErrors';
import { resolveKey } from '../utils/i18nKeys';
import { formatPrice } from '../utils/priceFormat';

interface SurfaceWorkPlanEditorProps {
  projectId: string;
  roomId: string;
  surfaceId: string;
  surfaceName: string;
  onClose: () => void;
}

type LoadState = 'loading' | 'ready' | 'error';
type PickerState = 'closed' | 'loading' | 'ready' | 'error';

interface WorkPlanBaseline {
  substrate: SubstrateValue | '';
  qualityTarget: QualityLevelValue | null;
  /** Occurrence IDs as committed by the last successful save/load. */
  occurrenceIds: string[];
}

/** A draft occurrence: may be persisted (has work_plan_id) or local-only. */
interface DraftOccurrence {
  /** Unique key within the draft list; stable identity for React. */
  draftKey: string;
  /** price_item_id sent in PUT */
  priceItemId: string;
  /** Full summary snapshot for display — may be null for unavailable items. */
  summary: SurfacePriceItemSummaryRead | null;
}

const SUBSTRATES: readonly SubstrateValue[] = [
  'CONCRETE',
  'GYPSUM_PLASTER',
  'CEMENT_LIME_PLASTER',
  'GYPSUM_BOARD',
  'PAINTED',
  'OTHER',
];
const S_QUALITY_LEVELS: readonly QualityLevelValue[] = ['S1', 'S2', 'S3', 'S4'];
const Q_QUALITY_LEVELS: readonly QualityLevelValue[] = ['Q1', 'Q2', 'Q3', 'Q4'];
const ALL_QUALITY_LEVELS: readonly QualityLevelValue[] = [
  ...S_QUALITY_LEVELS,
  ...Q_QUALITY_LEVELS,
];

function qualityLevelsForSubstrate(substrate: SubstrateValue | ''): readonly QualityLevelValue[] {
  if (substrate === 'GYPSUM_BOARD') return Q_QUALITY_LEVELS;
  if (
    substrate === 'CONCRETE' ||
    substrate === 'GYPSUM_PLASTER' ||
    substrate === 'CEMENT_LIME_PLASTER'
  ) {
    return S_QUALITY_LEVELS;
  }
  if (substrate === 'PAINTED' || substrate === 'OTHER') return ALL_QUALITY_LEVELS;
  return [];
}

/** Stable draft key generator — monotonically increasing per render lifetime. */
let draftKeyCounter = 0;
function nextDraftKey(): string {
  return `dk-${++draftKeyCounter}`;
}

/** Convert a persisted occurrence to a draft occurrence. */
function workToDraft(work: SurfacePlannedWorkRead): DraftOccurrence {
  return {
    draftKey: nextDraftKey(),
    priceItemId: work.price_item_id,
    summary: work.price_item,
  };
}

export function SurfaceWorkPlanEditor({
  projectId,
  roomId,
  surfaceId,
  surfaceName,
  onClose,
}: SurfaceWorkPlanEditorProps) {
  const { t } = useI18n();
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [hasPlan, setHasPlan] = useState(false);
  const [substrate, setSubstrate] = useState<SubstrateValue | ''>('');
  const [qualityTarget, setQualityTarget] = useState<QualityLevelValue | null>(null);

  // Draft occurrences — independent stable list, preserves order + duplicates.
  const [draftOccurrences, setDraftOccurrences] = useState<DraftOccurrence[]>([]);

  const [baseline, setBaseline] = useState<WorkPlanBaseline>({
    substrate: '',
    qualityTarget: null,
    occurrenceIds: [],
  });

  // Price Book picker state
  const [pickerState, setPickerState] = useState<PickerState>('closed');
  const [allPriceItems, setAllPriceItems] = useState<PriceItem[]>([]);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [pickerSearch, setPickerSearch] = useState('');

  const loadGeneration = useRef(0);

  const editorId = `work-plan-editor-${surfaceId}`;
  const qualityLevels = qualityLevelsForSubstrate(substrate);

  const currentOccurrenceIds = draftOccurrences.map((o) => o.priceItemId);
  const dirty =
    substrate !== baseline.substrate ||
    qualityTarget !== baseline.qualityTarget ||
    JSON.stringify(currentOccurrenceIds) !== JSON.stringify(baseline.occurrenceIds);

  const describeError = (error: unknown, fallback: string): string => {
    const detail = localizeApiError(error, t);
    return /^Request failed(?: \(\d+\))?$/.test(detail) ? fallback : detail;
  };

  const hydrate = (plan: SurfaceWorkPlanRead | null) => {
    const nextSubstrate = plan?.substrate ?? '';
    const nextQuality = plan?.quality_target ?? null;
    const nextOccurrences = (plan?.planned_works ?? []).map(workToDraft);
    const nextIds = nextOccurrences.map((o) => o.priceItemId);
    setHasPlan(plan !== null);
    setSubstrate(nextSubstrate);
    setQualityTarget(nextQuality);
    setDraftOccurrences(nextOccurrences);
    setBaseline({ substrate: nextSubstrate, qualityTarget: nextQuality, occurrenceIds: nextIds });
  };

  useEffect(() => {
    const generation = ++loadGeneration.current;
    setLoadState('loading');
    setLoadError(null);
    setSaveError(null);
    setSaved(false);
    setSaving(false);

    void fetchSurfaceWorkPlan(projectId, roomId, surfaceId)
      .then((plan) => {
        if (loadGeneration.current !== generation) return;
        hydrate(plan);
        setLoadState('ready');
      })
      .catch((error: unknown) => {
        if (loadGeneration.current !== generation) return;
        if (isSurfaceWorkPlanMissing(error)) {
          hydrate(null);
          setLoadState('ready');
          return;
        }
        setLoadError(describeError(error, t.work_plan.error_load));
        setLoadState('error');
      });

    return () => {
      if (loadGeneration.current === generation) loadGeneration.current += 1;
    };
  }, [loadAttempt, projectId, roomId, surfaceId, t]);

  const substrateLabel = (value: SubstrateValue): string => {
    const labels: Record<SubstrateValue, string> = {
      CONCRETE: t.inspections.substrate_concrete,
      GYPSUM_PLASTER: t.inspections.substrate_gypsum_plaster,
      CEMENT_LIME_PLASTER: t.inspections.substrate_cement_lime_plaster,
      GYPSUM_BOARD: t.inspections.substrate_gypsum_board,
      PAINTED: t.inspections.substrate_painted,
      OTHER: t.inspections.substrate_other,
    };
    return labels[value];
  };

  const handleSubstrateChange = (next: SubstrateValue | '') => {
    const nextLevels = qualityLevelsForSubstrate(next);
    setSubstrate(next);
    setQualityTarget((current) => {
      if (next === 'PAINTED' || next === 'OTHER') return null;
      return current !== null && nextLevels.includes(current) ? current : null;
    });
    setSaveError(null);
    setSaved(false);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (loadState !== 'ready' || !substrate || !dirty || saving) return;

    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const plan = await putSurfaceWorkPlan(projectId, roomId, surfaceId, {
        substrate,
        quality_target: qualityTarget,
        // PUT is full replacement; occurrence order and duplicates must remain exact.
        price_item_ids: draftOccurrences.map((o) => o.priceItemId),
      });
      hydrate(plan);
      setSaved(true);
    } catch (error) {
      setSaveError(describeError(error, t.work_plan.error_save));
    } finally {
      setSaving(false);
    }
  };

  const occurrenceDisplayName = (summary: SurfacePriceItemSummaryRead | null): string => {
    if (!summary) return t.work_plan.unavailable_item;
    if (summary.display_name) return summary.display_name;
    if (summary.name_key) {
      const localized = resolveKey(t, summary.name_key);
      if (localized !== summary.name_key) return localized;
    }
    return t.work_plan.unavailable_item;
  };

  const priceItemDisplayName = (item: PriceItem): string => {
    if (item.display_name) return item.display_name;
    if (item.name_key) {
      const localized = resolveKey(t, item.name_key);
      if (localized !== item.name_key) return localized;
    }
    return item.code;
  };

  // ---------------------------------------------------------------------------
  // Picker
  // ---------------------------------------------------------------------------

  const openPicker = async () => {
    setPickerState('loading');
    setPickerSearch('');
    setPickerError(null);
    try {
      // Load ALL active items in one shot — avoid N+1; filter client-side.
      const resp = await fetchPriceItems({ archived: 'active' });
      setAllPriceItems(resp.items);
      setPickerState('ready');
    } catch {
      setPickerError(t.work_plan.picker_error);
      setPickerState('error');
    }
  };

  const closePicker = () => {
    setPickerState('closed');
    setPickerSearch('');
  };

  const handlePickerSelect = (item: PriceItem) => {
    const occurrence: DraftOccurrence = {
      draftKey: nextDraftKey(),
      priceItemId: item.id,
      summary: {
        id: item.id,
        code: item.code,
        name_key: item.name_key,
        display_name: item.display_name,
        category: item.category,
        unit: item.unit,
        price_scope: item.price_scope,
        price: item.price,
        currency: item.currency,
        is_archived: item.is_archived,
        quality_level: item.quality_level,
      },
    };
    setDraftOccurrences((prev) => [...prev, occurrence]);
    closePicker();
    setSaveError(null);
    setSaved(false);
  };

  const handleRemoveOccurrence = (draftKey: string) => {
    setDraftOccurrences((prev) => prev.filter((o) => o.draftKey !== draftKey));
    setSaveError(null);
    setSaved(false);
  };

  const handleMoveOccurrenceUp = (index: number) => {
    if (index <= 0 || index >= draftOccurrences.length) return;
    setDraftOccurrences((prev) => {
      const next = [...prev];
      const item = next[index];
      next[index] = next[index - 1];
      next[index - 1] = item;
      return next;
    });
    setSaveError(null);
    setSaved(false);
  };

  const handleMoveOccurrenceDown = (index: number) => {
    if (index < 0 || index >= draftOccurrences.length - 1) return;
    setDraftOccurrences((prev) => {
      const next = [...prev];
      const item = next[index];
      next[index] = next[index + 1];
      next[index + 1] = item;
      return next;
    });
    setSaveError(null);
    setSaved(false);
  };

  // Client-side search across display name, name_key (localized), code, category, scope, unit.
  const filteredPickerItems = useMemo(() => {
    const q = pickerSearch.trim().toLowerCase();
    if (!q) return allPriceItems;
    return allPriceItems.filter((item) => {
      const name = priceItemDisplayName(item).toLowerCase();
      const cat = t.pricebook.categories[item.category]?.toLowerCase() ?? '';
      const scope = t.pricebook.scopes[item.price_scope]?.toLowerCase() ?? '';
      const unit = t.pricebook.units[item.unit]?.toLowerCase() ?? '';
      return (
        name.includes(q) ||
        cat.includes(q) ||
        scope.includes(q) ||
        unit.includes(q) ||
        item.code.toLowerCase().includes(q)
      );
    });
  }, [allPriceItems, pickerSearch, t]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <section
      id={editorId}
      aria-label={`work-plan-editor-${surfaceId}`}
      className="w-full min-w-0 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] p-3 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h5 className="text-sm font-bold text-[var(--tg-theme-text-color)] break-words">
            {t.work_plan.title}
          </h5>
          <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{surfaceName}</p>
        </div>
        <button
          type="button"
          aria-label={`close-work-plan-${surfaceId}`}
          onClick={onClose}
          disabled={saving}
          className="min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)] font-semibold disabled:opacity-60"
        >
          {t.common.close}
        </button>
      </div>

      {loadState === 'loading' && (
        <p role="status" className="py-4 text-sm text-center text-[var(--tg-theme-hint-color)]">
          {t.work_plan.loading}
        </p>
      )}

      {loadState === 'error' && (
        <div role="alert" className="space-y-2">
          <p className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)]">
            {t.work_plan.error_load}
          </p>
          {loadError && loadError !== t.work_plan.error_load && (
            <p className="text-xs text-[var(--tg-theme-destructive-text-color)] break-words">{loadError}</p>
          )}
          <button
            type="button"
            aria-label={`retry-work-plan-${surfaceId}`}
            onClick={() => setLoadAttempt((current) => current + 1)}
            className="w-full min-h-11 px-3 rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] font-semibold"
          >
            {t.work_plan.retry}
          </button>
        </div>
      )}

      {loadState === 'ready' && (
        <form aria-label={`work-plan-form-${surfaceId}`} onSubmit={(event) => void handleSubmit(event)} className="space-y-3">
          {!hasPlan && (
            <p className="text-sm text-[var(--tg-theme-hint-color)]">{t.work_plan.no_plan}</p>
          )}

          <label className="block text-sm font-medium text-[var(--tg-theme-text-color)]">
            {t.inspections.substrate}
            <select
              aria-label={`work-plan-substrate-${surfaceId}`}
              value={substrate}
              onChange={(event) => handleSubstrateChange(event.target.value as SubstrateValue | '')}
              disabled={saving}
              className="mt-1 w-full min-h-11 rounded-xl border px-3 py-2 text-base disabled:opacity-60"
            >
              <option value="">{t.inspections.select_substrate}</option>
              {SUBSTRATES.map((value) => (
                <option key={value} value={value}>{substrateLabel(value)}</option>
              ))}
            </select>
          </label>

          <label className="block text-sm font-medium text-[var(--tg-theme-text-color)]">
            {t.inspections.quality_target}
            <select
              aria-label={`work-plan-quality-${surfaceId}`}
              value={qualityTarget ?? ''}
              onChange={(event) => {
                setQualityTarget(event.target.value === '' ? null : event.target.value as QualityLevelValue);
                setSaveError(null);
                setSaved(false);
              }}
              disabled={saving || substrate === ''}
              className="mt-1 w-full min-h-11 rounded-xl border px-3 py-2 text-base disabled:opacity-60"
            >
              <option value="">{t.inspections.quality_optional}</option>
              {qualityLevels.map((level) => (
                <option key={level} value={level}>{t.pricebook.quality[level]}</option>
              ))}
            </select>
          </label>

          {/* Planned works draft */}
          <div className="space-y-2 min-w-0">
            <h6 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">
              {t.work_plan.planned_works}
            </h6>
            {draftOccurrences.length === 0 ? (
              <p className="text-sm text-[var(--tg-theme-hint-color)]">{t.work_plan.no_works}</p>
            ) : (
              <ol aria-label={`planned-works-${surfaceId}`} className="space-y-2">
                {draftOccurrences.map((occurrence, index) => {
                  const item = occurrence.summary;
                  return (
                    <li
                      key={occurrence.draftKey}
                      aria-label={`draft-occurrence-${occurrence.draftKey}`}
                      className="min-w-0 rounded-lg border border-[var(--tg-control-border-color)] p-2"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <span className="min-w-0 text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">
                          {occurrenceDisplayName(item)}
                        </span>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {item?.is_archived && (
                            <span className="text-xs text-[var(--tg-theme-destructive-text-color)] mr-1">
                              {t.pricebook.archived_badge}
                            </span>
                          )}
                          <button
                            type="button"
                            aria-label={`move-up-occurrence-${occurrence.draftKey}`}
                            onClick={() => handleMoveOccurrenceUp(index)}
                            disabled={saving || index === 0}
                            className="min-h-[44px] min-w-[36px] px-1 flex items-center justify-center text-sm font-bold text-[var(--tg-theme-text-color)] disabled:opacity-30"
                            title={t.work_plan.move_up}
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            aria-label={`move-down-occurrence-${occurrence.draftKey}`}
                            onClick={() => handleMoveOccurrenceDown(index)}
                            disabled={saving || index === draftOccurrences.length - 1}
                            className="min-h-[44px] min-w-[36px] px-1 flex items-center justify-center text-sm font-bold text-[var(--tg-theme-text-color)] disabled:opacity-30"
                            title={t.work_plan.move_down}
                          >
                            ↓
                          </button>
                          <button
                            type="button"
                            aria-label={`remove-occurrence-${occurrence.draftKey}`}
                            onClick={() => handleRemoveOccurrence(occurrence.draftKey)}
                            disabled={saving}
                            className="min-h-[44px] min-w-[44px] flex items-center justify-center text-xs text-[var(--tg-theme-destructive-text-color)] disabled:opacity-60"
                          >
                            {t.work_plan.remove_work}
                          </button>
                        </div>
                      </div>
                      {item ? (
                        <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs text-[var(--tg-theme-hint-color)]">
                          <span>{t.pricebook.categories[item.category]}</span>
                          <span>{t.pricebook.units[item.unit]}</span>
                          <span>{t.pricebook.scopes[item.price_scope]}</span>
                          {item.quality_level && <span>{t.pricebook.quality[item.quality_level]}</span>}
                          <span>
                            {item.price === null
                              ? t.pricebook.price_not_set
                              : `${formatPrice(item.price)} ${item.currency === 'PLN' ? t.pricebook.currency_symbol : item.currency}`}
                          </span>
                        </div>
                      ) : (
                        <p className="mt-1 text-xs text-[var(--tg-theme-hint-color)]">{t.work_plan.unavailable_item}</p>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}

            {/* Add work button — always visible when ready */}
            <button
              type="button"
              aria-label={`open-picker-${surfaceId}`}
              onClick={() => void openPicker()}
              disabled={saving || pickerState === 'loading'}
              className="w-full min-h-11 px-3 rounded-xl border border-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-color)] font-semibold text-sm disabled:opacity-60"
            >
              {t.work_plan.add_work}
            </button>
          </div>

          {/* Price Book Picker — inline panel */}
          {pickerState !== 'closed' && (
            <div
              aria-label={`picker-panel-${surfaceId}`}
              role="dialog"
              aria-modal="false"
              className="w-full min-w-0 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-bg-color)] p-3 space-y-2"
            >
              <div className="flex items-center justify-between gap-2">
                <h6 className="text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">
                  {t.work_plan.picker_title}
                </h6>
                <button
                  type="button"
                  aria-label={`close-picker-${surfaceId}`}
                  onClick={closePicker}
                  className="min-h-11 min-w-11 flex items-center justify-center text-sm text-[var(--tg-theme-hint-color)]"
                >
                  {t.work_plan.picker_close}
                </button>
              </div>

              {pickerState === 'loading' && (
                <p role="status" className="py-3 text-sm text-center text-[var(--tg-theme-hint-color)]">
                  {t.work_plan.picker_loading}
                </p>
              )}

              {pickerState === 'error' && (
                <p role="alert" className="text-sm text-[var(--tg-theme-destructive-text-color)]">
                  {pickerError ?? t.work_plan.picker_error}
                </p>
              )}

              {pickerState === 'ready' && (
                <>
                  <input
                    type="search"
                    aria-label={`picker-search-${surfaceId}`}
                    placeholder={t.work_plan.picker_search}
                    value={pickerSearch}
                    onChange={(e) => setPickerSearch(e.target.value)}
                    className="w-full min-h-11 rounded-xl border px-3 py-2 text-sm bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]"
                  />

                  {filteredPickerItems.length === 0 ? (
                    <p className="py-3 text-sm text-center text-[var(--tg-theme-hint-color)]">
                      {pickerSearch.trim() ? t.work_plan.picker_no_results : t.work_plan.picker_empty}
                    </p>
                  ) : (
                    <ul aria-label={`picker-list-${surfaceId}`} className="space-y-1 max-h-64 overflow-y-auto">
                      {filteredPickerItems.map((item) => (
                        <li key={item.id}>
                          <button
                            type="button"
                            aria-label={`picker-item-${item.id}`}
                            onClick={() => handlePickerSelect(item)}
                            className="w-full min-h-11 text-left px-3 py-2 rounded-lg hover:bg-[var(--tg-theme-secondary-bg-color)] active:bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]"
                          >
                            <div className="text-sm font-semibold break-words">
                              {priceItemDisplayName(item)}
                            </div>
                            <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-[var(--tg-theme-hint-color)]">
                              <span>{t.pricebook.categories[item.category]}</span>
                              <span>{t.pricebook.units[item.unit]}</span>
                              <span>{t.pricebook.scopes[item.price_scope]}</span>
                              <span>
                                {item.price === null
                                  ? t.pricebook.price_not_set
                                  : `${formatPrice(item.price)} ${item.currency === 'PLN' ? t.pricebook.currency_symbol : item.currency}`}
                              </span>
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </div>
          )}

          {saveError && (
            <div role="alert" className="space-y-1">
              <p className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)]">
                {t.work_plan.error_save}
              </p>
              {saveError !== t.work_plan.error_save && (
                <p className="text-xs text-[var(--tg-theme-destructive-text-color)] break-words">{saveError}</p>
              )}
            </div>
          )}
          {saved && (
            <p role="status" className="text-sm text-[var(--tg-theme-text-color)]">
              {t.work_plan.saved}
            </p>
          )}

          <button
            type="submit"
            aria-label={`save-work-plan-${surfaceId}`}
            disabled={!substrate || !dirty || saving}
            className="w-full min-h-11 px-3 rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] font-semibold disabled:opacity-60"
          >
            {saving ? t.common.saving : t.common.save}
          </button>
        </form>
      )}
    </section>
  );
}
