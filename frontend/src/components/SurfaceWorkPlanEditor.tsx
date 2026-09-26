import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { fetchPriceItems } from '../api/priceItems';
import {
  applyWorkPlanToRoomWalls,
  fetchSurfaceWorkPlan,
  isStaleWorkPlanError,
  isSurfaceWorkPlanMissing,
  putSurfaceWorkPlan,
} from '../api/workPlans';
import { useI18n } from '../hooks/useI18n';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { PriceItem } from '../types/priceItem';
import {
  PlannedWorkCoefficientOptionRead,
  SurfacePlannedWorkRead,
  SurfacePriceItemSummaryRead,
  SurfaceWorkPlanRead,
  SurfaceWorkPlanUpsert,
} from '../types/workPlan';
import { localizeApiError } from '../utils/apiErrors';
import { resolveKey } from '../utils/i18nKeys';
import { formatPrice } from '../utils/priceFormat';
import {
  calculateEffectivePrice,
  formatCoefficientSummary,
  sumPercentages,
} from '../utils/coefficientCalculations';
import { CoefficientAssignmentModal } from './CoefficientAssignmentModal';
import { PriceItemForm } from './PriceItemForm';

interface SurfaceWorkPlanEditorProps {
  projectId: string;
  roomId: string;
  surfaceId: string;
  surfaceName: string;
  /** True only for WALL surfaces — enables the apply-to-all-walls action. */
  isWall?: boolean;
  /** Count of other active WALL surfaces in the same room (apply-to-all target count). */
  otherActiveWallCount?: number;
  onClose: () => void;
}

type LoadState = 'loading' | 'ready' | 'error';
type PickerState = 'closed' | 'loading' | 'ready' | 'error';
type ApplyState = 'idle' | 'confirming' | 'applying' | 'success' | 'error';

interface WorkPlanBaseline {
  substrate: SubstrateValue | '';
  qualityTarget: QualityLevelValue | null;
  /** Occurrence identities (server occurrence_key, or the local draftKey of
   * an unsaved row) as committed by the last successful save/load. */
  occurrenceIdentities: string[];
  /** Coefficient option id lists per occurrence, same ordering. */
  coefficientOptionIdLists: string[][];
}

/** A draft occurrence: may be persisted (has work_plan_id) or local-only. */
interface DraftOccurrence {
  /** Frontend-only row identity for React / local edits. NEVER sent to the
   * server as an occurrence_key. */
  draftKey: string;
  /** Server-generated logical identity of an EXISTING occurrence; null for a
   * row added in this draft (the server assigns one on save). */
  occurrenceKey: string | null;
  /** Backend-provided technological break, preserved verbatim on save. */
  waitAfterHours: number | null;
  /** price_item_id sent in PUT */
  priceItemId: string;
  /** Full summary snapshot for display — may be null for unavailable items. */
  summary: SurfacePriceItemSummaryRead | null;
  /** Currently assigned coefficient options (draft-local, not yet persisted). */
  coefficientOptions: PlannedWorkCoefficientOptionRead[];
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
    occurrenceKey: work.occurrence_key,
    waitAfterHours: work.wait_after_hours ?? null,
    priceItemId: work.price_item_id,
    summary: work.price_item,
    coefficientOptions: work.coefficient_options ?? [],
  };
}

export function SurfaceWorkPlanEditor({
  projectId,
  roomId,
  surfaceId,
  surfaceName,
  isWall = false,
  otherActiveWallCount = 0,
  onClose,
}: SurfaceWorkPlanEditorProps) {
  const { t } = useI18n();
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  // The last save echoed an occurrence_key that is no longer current: the plan
  // changed elsewhere and must be reloaded (never retried without keys).
  const [staleSave, setStaleSave] = useState(false);
  const [hasPlan, setHasPlan] = useState(false);
  const [substrate, setSubstrate] = useState<SubstrateValue | ''>('');
  const [qualityTarget, setQualityTarget] = useState<QualityLevelValue | null>(null);

  // Draft occurrences — independent stable list, preserves order + duplicates.
  const [draftOccurrences, setDraftOccurrences] = useState<DraftOccurrence[]>([]);

  const [baseline, setBaseline] = useState<WorkPlanBaseline>({
    substrate: '',
    qualityTarget: null,
    occurrenceIdentities: [],
    coefficientOptionIdLists: [],
  });

  // Apply-to-all-walls state (WALL surfaces only)
  const [applyState, setApplyState] = useState<ApplyState>('idle');
  const [applyError, setApplyError] = useState<string | null>(null);
  const [appliedCount, setAppliedCount] = useState<number | null>(null);

  // Price Book picker state
  const [pickerState, setPickerState] = useState<PickerState>('closed');
  const [allPriceItems, setAllPriceItems] = useState<PriceItem[]>([]);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [pickerSearch, setPickerSearch] = useState('');
  // Inline "+ Dodaj nową pracę do cennika" creation, shown inside the picker.
  const [creatingPriceItem, setCreatingPriceItem] = useState(false);

  // Coefficient assignment modal state
  const [coefficientModalOpen, setCoefficientModalOpen] = useState(false);
  const [coefficientModalDraftKey, setCoefficientModalDraftKey] = useState<string | null>(null);

  const loadGeneration = useRef(0);

  const editorId = `work-plan-editor-${surfaceId}`;
  const qualityLevels = qualityLevelsForSubstrate(substrate);

  const identityOf = (o: DraftOccurrence): string => o.occurrenceKey ?? o.draftKey;
  const currentOccurrenceIdentities = draftOccurrences.map(identityOf);
  const currentCoefficientLists = draftOccurrences.map((o) =>
    o.coefficientOptions.map((c) => c.id),
  );
  const dirty =
    substrate !== baseline.substrate ||
    qualityTarget !== baseline.qualityTarget ||
    JSON.stringify(currentOccurrenceIdentities) !== JSON.stringify(baseline.occurrenceIdentities) ||
    JSON.stringify(currentCoefficientLists) !== JSON.stringify(baseline.coefficientOptionIdLists);

  const describeError = (error: unknown, fallback: string): string => {
    const detail = localizeApiError(error, t);
    return /^Request failed(?: \(\d+\))?$/.test(detail) ? fallback : detail;
  };

  const hydrate = (plan: SurfaceWorkPlanRead | null) => {
    const nextSubstrate = plan?.substrate ?? '';
    const nextQuality = plan?.quality_target ?? null;
    const nextOccurrences = (plan?.planned_works ?? []).map(workToDraft);
    const nextIdentities = nextOccurrences.map(identityOf);
    const nextCoefficientLists = nextOccurrences.map((o) =>
      o.coefficientOptions.map((c) => c.id),
    );
    setHasPlan(plan !== null);
    setSubstrate(nextSubstrate);
    setQualityTarget(nextQuality);
    setDraftOccurrences(nextOccurrences);
    setBaseline({
      substrate: nextSubstrate,
      qualityTarget: nextQuality,
      occurrenceIdentities: nextIdentities,
      coefficientOptionIdLists: nextCoefficientLists,
    });
  };

  useEffect(() => {
    const generation = ++loadGeneration.current;
    setLoadState('loading');
    setLoadError(null);
    setSaveError(null);
    setStaleSave(false);
    setSaved(false);
    setSaving(false);
    setApplyState('idle');
    setApplyError(null);
    setAppliedCount(null);

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
    setStaleSave(false);
    setSaved(false);
    try {
      // Stage 13E.2C: every ordinary save uses planned_works[] and carries each
      // occurrence's identity and configuration -- an existing occurrence
      // echoes its server occurrence_key (same logical work, so Estimate
      // overrides survive the row recreation); a new one omits it and the
      // server generates one. Breaks and coefficients are sent verbatim.
      const payload: SurfaceWorkPlanUpsert = {
        substrate,
        quality_target: qualityTarget,
        planned_works: draftOccurrences.map((o) => ({
          price_item_id: o.priceItemId,
          ...(o.occurrenceKey !== null ? { occurrence_key: o.occurrenceKey } : {}),
          wait_after_hours: o.waitAfterHours,
          coefficient_option_ids: o.coefficientOptions.map((c) => c.id),
        })),
      };
      const plan = await putSurfaceWorkPlan(projectId, roomId, surfaceId, payload);
      // Re-hydrate from the server so new rows now carry their server keys.
      hydrate(plan);
      setSaved(true);
    } catch (error) {
      if (isStaleWorkPlanError(error)) {
        // Never retry without keys and never turn rows into new work: the
        // owner reloads the current plan first.
        setStaleSave(true);
      } else {
        setSaveError(describeError(error, t.work_plan.error_save));
      }
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
    setCreatingPriceItem(false);
    try {
      // Load ALL active items in one shot — avoid N+1; filter client-side.
      // Reveal work is planned per opening (Stage 10 D19), never on a surface.
      const resp = await fetchPriceItems({ archived: 'active' });
      setAllPriceItems(resp.items.filter((item) => item.category !== 'REVEAL'));
      setPickerState('ready');
    } catch {
      setPickerError(t.work_plan.picker_error);
      setPickerState('error');
    }
  };

  const closePicker = () => {
    setPickerState('closed');
    setPickerSearch('');
    setCreatingPriceItem(false);
  };

  const addItemToDraft = (item: PriceItem) => {
    const occurrence: DraftOccurrence = {
      draftKey: nextDraftKey(),
      occurrenceKey: null,
      waitAfterHours: null,
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
      coefficientOptions: [],
    };
    setDraftOccurrences((prev) => [...prev, occurrence]);
    setSaveError(null);
    setSaved(false);
  };

  const handlePickerSelect = (item: PriceItem) => {
    addItemToDraft(item);
    closePicker();
  };

  // Inline Price Book creation from the picker (Stage 10G.4 follow-up). The
  // new item is persisted through the normal Price Book API and immediately
  // added to this draft — the Surface Work Plan itself is never auto-saved;
  // the owner still presses the existing Save button explicitly. Category is
  // not locked (the picker spans every surface category), but REVEAL is
  // excluded: reveal work belongs under an opening.
  const handlePriceItemCreated = (item: PriceItem) => {
    addItemToDraft(item);
    closePicker();
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

  // ---------------------------------------------------------------------------
  // Coefficient assignment modal (Stage 12F)
  // ---------------------------------------------------------------------------

  const activeModalOccurrence = coefficientModalDraftKey
    ? draftOccurrences.find((o) => o.draftKey === coefficientModalDraftKey) ?? null
    : null;

  const openCoefficientModal = (draftKey: string) => {
    setCoefficientModalDraftKey(draftKey);
    setCoefficientModalOpen(true);
  };

  const closeCoefficientModal = () => {
    setCoefficientModalOpen(false);
    setCoefficientModalDraftKey(null);
  };

  const handleApplyCoefficients = (
    selectedOptions: PlannedWorkCoefficientOptionRead[],
  ) => {
    if (!coefficientModalDraftKey) {
      closeCoefficientModal();
      return;
    }
    setDraftOccurrences((prev) =>
      prev.map((o) =>
        o.draftKey === coefficientModalDraftKey
          ? { ...o, coefficientOptions: selectedOptions }
          : o,
      ),
    );
    setSaveError(null);
    setSaved(false);
    closeCoefficientModal();
  };

  // ---------------------------------------------------------------------------
  // Apply to all walls
  // ---------------------------------------------------------------------------

  const handleApplyToAllWalls = async () => {
    setApplyState('applying');
    setApplyError(null);
    try {
      const result = await applyWorkPlanToRoomWalls(projectId, roomId, surfaceId);
      setAppliedCount(result.target_count);
      setApplyState('success');
    } catch (error) {
      setApplyError(describeError(error, t.work_plan.apply_error));
      setApplyState('error');
    }
  };

  const handleApplyCancel = () => {
    setApplyState('idle');
    setApplyError(null);
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
        <>
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
                  const isLabor = item?.price_scope === 'LABOR';
                  const coefSummary = formatCoefficientSummary(occurrence.coefficientOptions);
                  const basePrice = item?.price ?? null;
                  const currency = item?.currency ?? 'PLN';
                  const totalPercentage = sumPercentages(
                    occurrence.coefficientOptions.map((o) => o.percentage),
                  );
                  const effectivePrice =
                    occurrence.coefficientOptions.length > 0
                      ? calculateEffectivePrice(basePrice, totalPercentage)
                      : basePrice;
                  return (
                    <li
                      key={occurrence.draftKey}
                      aria-label={`draft-occurrence-${occurrence.draftKey}`}
                      className="min-w-0 rounded-lg border border-[var(--tg-control-border-color)] p-2"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <span className="min-w-0 text-sm font-semibold text-[var(--tg-theme-text-color)] break-words block">
                            {occurrenceDisplayName(item)}
                          </span>
                          {coefSummary && (
                            <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs">
                              <span
                                aria-label={`occurrence-coefficient-summary-${occurrence.draftKey}`}
                                className="px-1.5 py-0.5 rounded font-medium bg-blue-50 text-blue-700 border border-blue-200"
                              >
                                {t.estimates.coefficient_adjustment}: {coefSummary}
                              </span>
                              {effectivePrice !== basePrice && effectivePrice !== null && (
                                <span className="text-[var(--tg-theme-hint-color)]">
                                  → {formatPrice(effectivePrice)} {currency === 'PLN' ? t.pricebook.currency_symbol : currency}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
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
                        <div className="mt-1 space-y-1">
                          <div className="flex flex-wrap gap-x-2 gap-y-1 text-xs text-[var(--tg-theme-hint-color)]">
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
                          {item.category === 'REVEAL' && (
                            <p
                              aria-label={`legacy-reveal-note-${occurrence.draftKey}`}
                              className="rounded-lg border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-amber-900 break-words"
                            >
                              {t.work_plan.legacy_reveal_note}
                            </p>
                          )}
                          {isLabor && (
                            <button
                              type="button"
                              aria-label={`assign-coefficient-${occurrence.draftKey}`}
                              onClick={() => openCoefficientModal(occurrence.draftKey)}
                              disabled={saving}
                              className="mt-1 w-full min-h-[44px] px-3 py-1.5 text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 active:bg-blue-200 disabled:opacity-60 flex items-center justify-center gap-1.5"
                            >
                              {t.work_plan.coefficient_action}
                              {coefSummary && <span className="font-mono">({coefSummary})</span>}
                            </button>
                          )}
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

          {staleSave && (
            <div role="alert" aria-label={`stale-work-plan-${surfaceId}`} className="space-y-2">
              <p className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">
                {t.work_plan.stale_plan}
              </p>
              <button
                type="button"
                aria-label={`reload-work-plan-${surfaceId}`}
                onClick={() => setLoadAttempt((current) => current + 1)}
                className="w-full min-h-11 px-3 rounded-xl border border-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-color)] font-semibold text-sm"
              >
                {t.work_plan.reload_plan}
              </button>
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

          {/* Apply to all walls — WALL surfaces with a saved plan only */}
          {isWall && hasPlan && (
            <div className="space-y-2 pt-1 border-t border-[var(--tg-control-border-color)]">
              {applyState === 'idle' && (
                <button
                  type="button"
                  aria-label={`apply-to-all-walls-${surfaceId}`}
                  onClick={() => setApplyState('confirming')}
                  disabled={saving}
                  className="w-full min-h-11 px-3 rounded-xl border border-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-color)] font-semibold text-sm disabled:opacity-60"
                >
                  {t.work_plan.apply_to_walls}
                </button>
              )}
              {applyState === 'confirming' && (
                <div
                  aria-label={`apply-confirm-panel-${surfaceId}`}
                  className="rounded-xl border border-[var(--tg-control-border-color)] p-3 space-y-2"
                >
                  <p className="text-sm text-[var(--tg-theme-text-color)] break-words">
                    {t.work_plan.apply_confirm.replace('{count}', String(otherActiveWallCount))}
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      aria-label={`apply-confirm-yes-${surfaceId}`}
                      onClick={() => void handleApplyToAllWalls()}
                      className="flex-1 min-h-11 px-3 rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] font-semibold text-sm"
                    >
                      {t.work_plan.apply_confirm_yes}
                    </button>
                    <button
                      type="button"
                      aria-label={`apply-cancel-${surfaceId}`}
                      onClick={handleApplyCancel}
                      className="flex-1 min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)] font-semibold text-sm"
                    >
                      {t.common.cancel}
                    </button>
                  </div>
                </div>
              )}
              {applyState === 'applying' && (
                <p role="status" className="py-2 text-sm text-center text-[var(--tg-theme-hint-color)]">
                  {t.work_plan.applying}
                </p>
              )}
              {applyState === 'success' && (
                <div className="space-y-1">
                  <p role="status" className="text-sm text-[var(--tg-theme-text-color)]">
                    {t.work_plan.apply_success.replace('{count}', String(appliedCount ?? 0))}
                  </p>
                  <button
                    type="button"
                    aria-label={`apply-success-dismiss-${surfaceId}`}
                    onClick={handleApplyCancel}
                    className="w-full min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)] text-sm font-medium"
                  >
                    {t.common.close}
                  </button>
                </div>
              )}
              {applyState === 'error' && (
                <div role="alert" className="space-y-1">
                  <p className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)]">
                    {t.work_plan.apply_error}
                  </p>
                  {applyError && applyError !== t.work_plan.apply_error && (
                    <p className="text-xs text-[var(--tg-theme-destructive-text-color)] break-words">{applyError}</p>
                  )}
                  <button
                    type="button"
                    aria-label={`apply-error-dismiss-${surfaceId}`}
                    onClick={handleApplyCancel}
                    className="w-full min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)] text-sm font-medium"
                  >
                    {t.common.close}
                  </button>
                </div>
              )}
            </div>
          )}
        </form>

        {/* Rendered as a SIBLING of the form above, never nested inside it —
            the inline Price Book creation form below embeds its own <form>,
            and a <form> inside a <form> is invalid HTML (unpredictable
            submit/Enter-key behavior in real browsers). */}
        {pickerState !== 'closed' && (
          <div
            aria-label={`picker-panel-${surfaceId}`}
            role="dialog"
            aria-modal="false"
            className="w-full min-w-0 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-bg-color)] p-3 space-y-2 mt-2"
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
              creatingPriceItem ? (
                <PriceItemForm
                  idPrefix={`work-plan-new-price-item-${surfaceId}`}
                  excludedCategories={['REVEAL']}
                  onCancel={() => setCreatingPriceItem(false)}
                  onSaved={handlePriceItemCreated}
                />
              ) : (
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

                  <button
                    type="button"
                    aria-label={`create-price-item-${surfaceId}`}
                    onClick={() => setCreatingPriceItem(true)}
                    className="w-full min-h-11 px-3 rounded-xl border border-dashed border-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-color)] font-semibold text-sm"
                  >
                    {t.work_plan.create_new_item}
                  </button>
                </>
              )
            )}
          </div>
        )}

        {/* Bottom close mirrors the top action exactly — same handler, no
            separate state — so a tall editor with several planned works
            never forces a scroll back to the top to close it. */}
        <button
          type="button"
          aria-label={`close-work-plan-bottom-${surfaceId}`}
          onClick={onClose}
          disabled={saving}
          className="w-full min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)] font-semibold disabled:opacity-60"
        >
          {t.common.close}
        </button>
        </>
      )}

      {/* Coefficient assignment modal — position:fixed, rendered as sibling of content */}
      {activeModalOccurrence && (
        <CoefficientAssignmentModal
          isOpen={coefficientModalOpen}
          occurrenceName={occurrenceDisplayName(activeModalOccurrence.summary)}
          basePrice={activeModalOccurrence.summary?.price ?? null}
          currency={activeModalOccurrence.summary?.currency ?? 'PLN'}
          initialOptionIds={activeModalOccurrence.coefficientOptions.map((o) => o.id)}
          onApply={handleApplyCoefficients}
          onCancel={closeCoefficientModal}
        />
      )}
    </section>
  );
}
