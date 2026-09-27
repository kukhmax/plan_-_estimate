import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { fetchPriceItems } from '../api/priceItems';
import {
  applyWorkPlanToRoomWalls,
  fetchSurfaceWorkPlan,
  isStaleWorkPlanError,
  isSurfaceWorkPlanMissing,
  parseExecutionDetachConfirmation,
  putSurfaceWorkPlan,
} from '../api/workPlans';
import { useI18n } from '../hooks/useI18n';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { PriceItem } from '../types/priceItem';
import {
  ExecutionDetachAffected,
  PlannedWorkCoefficientOptionRead,
  PlannedWorkExecutionRead,
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
import { formatWaitHours, parseWaitInput } from '../utils/waitFormat';
import { CoefficientAssignmentModal } from './CoefficientAssignmentModal';
import { ExecutionDetachDialog } from './ExecutionDetachDialog';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';
import { PriceItemForm } from './PriceItemForm';
import { WorkflowTemplateApplySheet } from './WorkflowTemplateApplySheet';
import { SurfaceTypeValue } from '../types/surface';

interface SurfaceWorkPlanEditorProps {
  projectId: string;
  roomId: string;
  surfaceId: string;
  surfaceName: string;
  /** True only for WALL surfaces — enables the apply-to-all-walls action. */
  isWall?: boolean;
  /** Count of other active WALL surfaces in the same room (apply-to-all target count). */
  otherActiveWallCount?: number;
  /** Surface type, used to find compatible technological workflows (13E.4). */
  surfaceType?: SurfaceTypeValue;
  /** Display names of the room's surfaces by id, to identify apply-to-all
   * targets in an execution-detach confirmation (Stage 13H.5). */
  surfaceNames?: Record<string, string>;
  onClose: () => void;
}

type LoadState = 'loading' | 'ready' | 'error';
type PickerState = 'closed' | 'loading' | 'ready' | 'error';
type ApplyState = 'idle' | 'confirming' | 'applying' | 'success' | 'error';

/** Stage 13H.5: a destructive request refused with the 409 execution-detach
 * contract, waiting for the owner. The ORIGINAL request is kept verbatim and
 * retried with exactly the server's keys -- never rebuilt or recomputed. */
type DetachPrompt =
  | { kind: 'save'; payload: SurfaceWorkPlanUpsert; affected: ExecutionDetachAffected[]; repeated: boolean }
  | { kind: 'apply'; affected: ExecutionDetachAffected[]; repeated: boolean };

interface WorkPlanBaseline {
  substrate: SubstrateValue | '';
  qualityTarget: QualityLevelValue | null;
  /** Occurrence identities (server occurrence_key, or the local draftKey of
   * an unsaved row) as committed by the last successful save/load. */
  occurrenceIdentities: string[];
  /** Coefficient option id lists per occurrence, same ordering. */
  coefficientOptionIdLists: string[][];
  /** Stage 13G: loaded breaks per occurrence, same ordering. */
  waitList: (number | null)[];
}

/** A draft occurrence: may be persisted (has work_plan_id) or local-only. */
interface DraftOccurrence {
  /** Frontend-only row identity for React / local edits. NEVER sent to the
   * server as an occurrence_key. */
  draftKey: string;
  /** Server-generated logical identity of an EXISTING occurrence; null for a
   * row added in this draft (the server assigns one on save). */
  occurrenceKey: string | null;
  /** Backend-provided technological break (as loaded). */
  waitAfterHours: number | null;
  /** Stage 13G: editable hours input for this occurrence ('' = no break). */
  waitInput: string;
  /** price_item_id sent in PUT */
  priceItemId: string;
  /** Full summary snapshot for display — may be null for unavailable items. */
  summary: SurfacePriceItemSummaryRead | null;
  /** Currently assigned coefficient options (draft-local, not yet persisted). */
  coefficientOptions: PlannedWorkCoefficientOptionRead[];
  /** Stage 13H.5: server execution state of a SAVED occurrence (read-only,
   * never sent back); null for a row added in this draft. */
  execution: PlannedWorkExecutionRead | null;
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
    waitInput: work.wait_after_hours == null ? '' : String(work.wait_after_hours),
    priceItemId: work.price_item_id,
    summary: work.price_item,
    coefficientOptions: work.coefficient_options ?? [],
    execution: work.execution ?? null,
  };
}

export function SurfaceWorkPlanEditor({
  projectId,
  roomId,
  surfaceId,
  surfaceName,
  isWall = false,
  otherActiveWallCount = 0,
  surfaceType,
  surfaceNames,
  onClose,
}: SurfaceWorkPlanEditorProps) {
  const { t, locale } = useI18n();
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  // The last save echoed an occurrence_key that is no longer current: the plan
  // changed elsewhere and must be reloaded (never retried without keys).
  const [staleSave, setStaleSave] = useState(false);
  // Stage 13E.4: technological workflow apply sheet.
  const [templateSheetOpen, setTemplateSheetOpen] = useState(false);
  const [templateApplied, setTemplateApplied] = useState(false);
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
    waitList: [],
  });

  // Apply-to-all-walls state (WALL surfaces only)
  const [applyState, setApplyState] = useState<ApplyState>('idle');
  const [applyError, setApplyError] = useState<string | null>(null);
  const [appliedCount, setAppliedCount] = useState<number | null>(null);
  const [detachPrompt, setDetachPrompt] = useState<DetachPrompt | null>(null);

  // Price Book picker state
  const [pickerState, setPickerState] = useState<PickerState>('closed');
  const [allPriceItems, setAllPriceItems] = useState<PriceItem[]>([]);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [pickerSearch, setPickerSearch] = useState('');
  // Inline "+ Dodaj nową pracę do cennika" creation, shown inside the picker.
  const [creatingPriceItem, setCreatingPriceItem] = useState(false);

  // Stage 13G: which occurrence has its break editor open (progressive disclosure).
  const [waitEditorKey, setWaitEditorKey] = useState<string | null>(null);
  const setWaitInput = (draftKey: string, value: string) => {
    setDraftOccurrences((prev) => prev.map((o) => (o.draftKey === draftKey ? { ...o, waitInput: value } : o)));
    setSaved(false);
    setSaveError(null);
  };

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
  // Stage 13G: a break belongs to its occurrence; an invalid input counts as a
  // change (it can never be saved) so the owner is not silently reset.
  const currentWaits = draftOccurrences.map((o) => parseWaitInput(o.waitInput));
  const invalidWait = currentWaits.some((w) => w === 'invalid');
  const dirty =
    substrate !== baseline.substrate ||
    qualityTarget !== baseline.qualityTarget ||
    JSON.stringify(currentOccurrenceIdentities) !== JSON.stringify(baseline.occurrenceIdentities) ||
    JSON.stringify(currentCoefficientLists) !== JSON.stringify(baseline.coefficientOptionIdLists) ||
    JSON.stringify(currentWaits) !== JSON.stringify(baseline.waitList);

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
      waitList: nextOccurrences.map((o) => o.waitAfterHours),
    });
  };

  useEffect(() => {
    const generation = ++loadGeneration.current;
    setLoadState('loading');
    setLoadError(null);
    setSaveError(null);
    setStaleSave(false);
    setTemplateSheetOpen(false);
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

  /** Sends one save; a detach-confirmation 409 opens the dialog with this
   * exact payload (repeated = it was already a confirmed retry). */
  const performSave = async (payload: SurfaceWorkPlanUpsert, repeated: boolean) => {
    setSaving(true);
    setSaveError(null);
    setStaleSave(false);
    setTemplateApplied(false);
    setSaved(false);
    try {
      const plan = await putSurfaceWorkPlan(projectId, roomId, surfaceId, payload);
      setDetachPrompt(null);
      // Re-hydrate from the server so new rows now carry their server keys.
      hydrate(plan);
      setSaved(true);
    } catch (error) {
      const affected = parseExecutionDetachConfirmation(error);
      if (affected) {
        const { confirm_execution_detach_keys: _previous, ...original } = payload;
        setDetachPrompt({ kind: 'save', payload: original, affected, repeated });
      } else if (isStaleWorkPlanError(error)) {
        setDetachPrompt(null);
        // Never retry without keys and never turn rows into new work: the
        // owner reloads the current plan first.
        setStaleSave(true);
      } else {
        setDetachPrompt(null);
        setSaveError(describeError(error, t.work_plan.error_save));
      }
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (loadState !== 'ready' || !substrate || !dirty || saving || invalidWait) return;

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
        wait_after_hours: parseWaitInput(o.waitInput) as number | null,
        coefficient_option_ids: o.coefficientOptions.map((c) => c.id),
      })),
    };
    await performSave(payload, false);
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
      waitInput: '',
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
      execution: null,
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

  const handleApplyToAllWalls = async (confirmKeys?: string[]) => {
    setApplyState('applying');
    setApplyError(null);
    try {
      const result = confirmKeys
        ? await applyWorkPlanToRoomWalls(projectId, roomId, surfaceId, confirmKeys)
        : await applyWorkPlanToRoomWalls(projectId, roomId, surfaceId);
      setDetachPrompt(null);
      setAppliedCount(result.target_count);
      setApplyState('success');
    } catch (error) {
      const affected = parseExecutionDetachConfirmation(error);
      if (affected) {
        // Target walls hold started/completed works: one flat confirmation.
        setDetachPrompt({ kind: 'apply', affected, repeated: confirmKeys !== undefined });
        setApplyState('confirming');
        return;
      }
      setDetachPrompt(null);
      setApplyError(describeError(error, t.work_plan.apply_error));
      setApplyState('error');
    }
  };

  const confirmDetach = () => {
    if (!detachPrompt) return;
    const keys = detachPrompt.affected.map((a) => a.occurrence_key);
    if (detachPrompt.kind === 'save') {
      void performSave({ ...detachPrompt.payload, confirm_execution_detach_keys: keys }, true);
    } else {
      void handleApplyToAllWalls(keys);
    }
  };

  const cancelDetach = () => {
    // Nothing is retried; the draft (and any unsaved change) stays as it was.
    if (detachPrompt?.kind === 'apply') setApplyState('idle');
    setDetachPrompt(null);
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
                            <span aria-hidden="true" className="text-[var(--tg-theme-hint-color)]">{index + 1}. </span>
                            {occurrenceDisplayName(item)}
                          </span>
                          {/* Stage 13H.5: read-only; execution changes only in Realizacja. */}
                          {occurrence.execution ? (
                            <div className="mt-0.5">
                              <ExecutionStatusBadge
                                status={occurrence.execution.status}
                                ariaLabel={`occurrence-execution-${occurrence.draftKey}`}
                              />
                            </div>
                          ) : occurrence.occurrenceKey === null ? (
                            <p
                              aria-label={`occurrence-unsaved-${occurrence.draftKey}`}
                              className="mt-0.5 text-xs text-[var(--tg-theme-hint-color)] break-words"
                            >
                              {t.execution.not_saved}
                            </p>
                          ) : null}
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
                      {(() => {
                        // Stage 13G: minimum technological break AFTER this work (not its duration).
                        const wait = parseWaitInput(occurrence.waitInput);
                        const open = waitEditorKey === occurrence.draftKey;
                        return (
                          <div className="mt-1.5 space-y-1.5">
                            {typeof wait === 'number' && (
                              <p
                                aria-label={`occurrence-wait-${occurrence.draftKey}`}
                                className="rounded-lg bg-amber-50 border border-amber-200 px-2 py-1 text-xs font-medium text-amber-900 break-words"
                              >
                                <span aria-hidden="true">⏸ </span>{t.work_plan.wait_after_work.replace('{value}', formatWaitHours(t, locale, wait))}
                              </p>
                            )}
                            <button
                              type="button"
                              aria-label={`edit-wait-${occurrence.draftKey}`}
                              aria-expanded={open}
                              onClick={() => setWaitEditorKey(open ? null : occurrence.draftKey)}
                              disabled={saving}
                              className="w-full min-h-[44px] px-3 py-1.5 text-xs font-semibold text-[var(--tg-control-text-color)] bg-[var(--tg-control-bg-color)] border border-[var(--tg-control-border-color)] rounded-lg disabled:opacity-60"
                            >
                              {open ? t.work_plan.wait_hide : t.work_plan.wait_toggle}
                            </button>
                            {open && (
                              <label className="block space-y-1">
                                <span className="block text-xs font-medium text-[var(--tg-theme-text-color)]">
                                  {t.work_plan.wait_hours_label}
                                </span>
                                <input
                                  aria-label={`wait-input-${occurrence.draftKey}`}
                                  value={occurrence.waitInput}
                                  inputMode="numeric"
                                  placeholder={t.work_plan.wait_none}
                                  onChange={(e) => setWaitInput(occurrence.draftKey, e.target.value)}
                                  disabled={saving}
                                  className="w-full min-h-[44px] px-3 rounded-lg border border-[var(--tg-control-border-color)] text-sm"
                                />
                                {wait === 'invalid' ? (
                                  <span role="alert" className="block text-xs text-[var(--tg-theme-destructive-text-color)]">
                                    {t.work_plan.wait_invalid}
                                  </span>
                                ) : (
                                  <span className="block text-xs text-[var(--tg-theme-hint-color)] break-words">
                                    {wait === null ? t.work_plan.wait_none : formatWaitHours(t, locale, wait)} · {t.work_plan.wait_help}
                                  </span>
                                )}
                              </label>
                            )}
                          </div>
                        );
                      })()}
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

          {hasPlan && (
            <div className="space-y-1 pt-1">
              <button
                type="button"
                aria-label={`open-template-sheet-${surfaceId}`}
                onClick={() => {
                  setTemplateApplied(false);
                  setTemplateSheetOpen(true);
                }}
                disabled={dirty || saving || !baseline.qualityTarget || !baseline.substrate}
                className="w-full min-h-11 px-3 rounded-xl border border-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-color)] font-semibold text-sm disabled:opacity-60 break-words"
              >
                {t.work_plan.tpl_open}
              </button>
              {dirty ? (
                <p aria-label={`template-unsaved-${surfaceId}`} className="text-xs text-[var(--tg-theme-hint-color)] break-words">
                  {t.work_plan.tpl_unsaved}
                </p>
              ) : !baseline.qualityTarget ? (
                <p aria-label={`template-need-quality-${surfaceId}`} className="text-xs text-[var(--tg-theme-hint-color)] break-words">
                  {t.work_plan.tpl_need_quality}
                </p>
              ) : null}
              {/* apply-template already persisted the plan server-side, so Save
                  stays disabled until the next ordinary edit makes it dirty. */}
              {templateApplied && !dirty && (
                <div
                  role="status"
                  aria-label={`template-applied-${surfaceId}`}
                  className="rounded-xl bg-green-50 text-green-900 p-3 space-y-0.5"
                >
                  <p className="text-sm font-semibold break-words"><span aria-hidden="true">✓ </span>{t.work_plan.tpl_success}</p>
                  <p className="text-xs break-words">{t.work_plan.tpl_success_hint}</p>
                </div>
              )}
            </div>
          )}

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
            disabled={!substrate || !dirty || saving || invalidWait}
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
                      disabled={detachPrompt !== null}
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
        {templateSheetOpen && baseline.substrate && baseline.qualityTarget && (
          <WorkflowTemplateApplySheet
            projectId={projectId}
            roomId={roomId}
            surfaceId={surfaceId}
            surfaceType={surfaceType}
            substrate={baseline.substrate}
            qualityTarget={baseline.qualityTarget}
            occurrenceKeys={draftOccurrences.map((o) => o.occurrenceKey)}
            planPriceItemIds={draftOccurrences.map((o) => o.priceItemId)}
            coefficientAssignmentCount={draftOccurrences.reduce((n, o) => n + o.coefficientOptions.length, 0)}
            onApplied={(plan) => {
              // The server response is the new truth (13E.2C identity contract);
              // no WorkPlan PUT and no Estimate regeneration follow.
              hydrate(plan);
              setTemplateSheetOpen(false);
              setSaved(false);
              setTemplateApplied(true);
            }}
            onReloadPlan={() => {
              setTemplateSheetOpen(false);
              setLoadAttempt((current) => current + 1);
            }}
            onClose={() => setTemplateSheetOpen(false)}
          />
        )}

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

      {detachPrompt && (
        <ExecutionDetachDialog
          affected={detachPrompt.affected}
          repeated={detachPrompt.repeated}
          surfaceNames={surfaceNames}
          showSurface={detachPrompt.kind === 'apply'}
          busy={saving || applyState === 'applying'}
          onConfirm={confirmDetach}
          onCancel={cancelDetach}
          idSuffix={surfaceId}
        />
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
