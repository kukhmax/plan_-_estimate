import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { fetchOpenings } from '../api/openings';
import { fetchPriceItems } from '../api/priceItems';
import {
  applyRevealWorksToRoom,
  fetchRevealWorks,
  putRevealWorks,
} from '../api/revealWorks';
import { fetchSurfaces } from '../api/surfaces';
import { useI18n } from '../hooks/useI18n';
import { PriceItem } from '../types/priceItem';
import { RevealWorkItemRead } from '../types/revealWork';
import { SurfacePriceItemSummaryRead } from '../types/workPlan';
import { localizeApiError } from '../utils/apiErrors';
import { formatMetric } from '../utils/format';
import { resolveKey } from '../utils/i18nKeys';
import { formatPrice } from '../utils/priceFormat';
import { PriceItemForm } from './PriceItemForm';

interface RevealWorkPlanEditorProps {
  projectId: string;
  roomId: string;
  surfaceId: string;
  openingId: string;
  openingLabel: string;
  /** Backend-authoritative reveal geometry — display only, never recomputed here. */
  revealTotalLength: string | number | null;
  revealTotalArea: string | number | null;
  onClose: () => void;
}

type LoadState = 'loading' | 'ready' | 'error';
type PickerState = 'closed' | 'loading' | 'ready' | 'error';
/** Stage 10G.4 — bulk apply to every other reveal-enabled opening in the room.
 * 'counting' fetches an accurate eligible-target count before showing the
 * confirmation, so the confirmation text never invents a number. */
type ApplyState = 'idle' | 'counting' | 'confirming' | 'applying' | 'success' | 'error';

/** A draft occurrence: may be persisted or local-only (matches SurfaceWorkPlanEditor). */
interface DraftOccurrence {
  draftKey: string;
  priceItemId: string;
  summary: SurfacePriceItemSummaryRead | null;
}

let draftKeyCounter = 0;
function nextDraftKey(): string {
  return `rwk-${++draftKeyCounter}`;
}

function workToDraft(work: RevealWorkItemRead): DraftOccurrence {
  return {
    draftKey: nextDraftKey(),
    priceItemId: work.price_item_id,
    summary: work.price_item,
  };
}

export function RevealWorkPlanEditor({
  projectId,
  roomId,
  surfaceId,
  openingId,
  openingLabel,
  revealTotalLength,
  revealTotalArea,
  onClose,
}: RevealWorkPlanEditorProps) {
  const { t } = useI18n();
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  // Draft occurrences — independent stable list, preserves order + duplicates.
  const [draftOccurrences, setDraftOccurrences] = useState<DraftOccurrence[]>([]);
  const [baselineIds, setBaselineIds] = useState<string[]>([]);

  // Price Book picker state — REVEAL category only.
  const [pickerState, setPickerState] = useState<PickerState>('closed');
  const [allPriceItems, setAllPriceItems] = useState<PriceItem[]>([]);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [pickerSearch, setPickerSearch] = useState('');
  // Inline "+ Dodaj nową pracę do cennika" creation, shown inside the picker.
  const [creatingPriceItem, setCreatingPriceItem] = useState(false);

  // Apply-to-room-openings bulk copy state (Stage 10G.4).
  const [applyState, setApplyState] = useState<ApplyState>('idle');
  const [applyError, setApplyError] = useState<string | null>(null);
  const [targetCount, setTargetCount] = useState<number | null>(null);
  const [appliedCount, setAppliedCount] = useState<number | null>(null);

  const loadGeneration = useRef(0);

  const currentIds = draftOccurrences.map((o) => o.priceItemId);
  const dirty = JSON.stringify(currentIds) !== JSON.stringify(baselineIds);

  const describeError = (error: unknown, fallback: string): string => {
    const detail = localizeApiError(error, t);
    return /^Request failed(?: \(\d+\))?$/.test(detail) ? fallback : detail;
  };

  const hydrate = (items: RevealWorkItemRead[]) => {
    const nextOccurrences = items.map(workToDraft);
    setDraftOccurrences(nextOccurrences);
    setBaselineIds(nextOccurrences.map((o) => o.priceItemId));
  };

  useEffect(() => {
    const generation = ++loadGeneration.current;
    setLoadState('loading');
    setLoadError(null);
    setSaveError(null);
    setSaved(false);
    setSaving(false);

    void fetchRevealWorks(projectId, roomId, surfaceId, openingId)
      .then((response) => {
        if (loadGeneration.current !== generation) return;
        hydrate(response.items);
        setLoadState('ready');
      })
      .catch((error: unknown) => {
        if (loadGeneration.current !== generation) return;
        setLoadError(describeError(error, t.reveals.work_error_load));
        setLoadState('error');
      });

    return () => {
      if (loadGeneration.current === generation) loadGeneration.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadAttempt, projectId, roomId, surfaceId, openingId, t]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (loadState !== 'ready' || !dirty || saving) return;

    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const response = await putRevealWorks(projectId, roomId, surfaceId, openingId, {
        // PUT is full replacement; occurrence order and duplicates must remain exact.
        price_item_ids: draftOccurrences.map((o) => o.priceItemId),
      });
      hydrate(response.items);
      setSaved(true);
    } catch (error) {
      setSaveError(describeError(error, t.reveals.work_error_save));
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
  // Picker — server-side filtered to PriceCategory.REVEAL only, never
  // WALL/FLOOR/CEILING-only categories.
  // ---------------------------------------------------------------------------

  const openPicker = async () => {
    setPickerState('loading');
    setPickerSearch('');
    setPickerError(null);
    setCreatingPriceItem(false);
    try {
      const resp = await fetchPriceItems({ category: 'REVEAL', archived: 'active' });
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
    setCreatingPriceItem(false);
  };

  const addItemToDraft = (item: PriceItem) => {
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
    setSaveError(null);
    setSaved(false);
  };

  const handlePickerSelect = (item: PriceItem) => {
    addItemToDraft(item);
    closePicker();
  };

  // Inline Price Book creation from the picker (Stage 10G.4 follow-up). The
  // new item is persisted through the normal Price Book API and immediately
  // added to this draft — the Reveal Work Plan itself is never auto-saved;
  // the owner still presses the existing Save button explicitly.
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
  // Apply to all reveal-enabled openings in the room (Stage 10G.4).
  //
  // Applies the opening's currently PERSISTED selection (baselineIds), never
  // the unsaved draft — the button is only shown once the draft is saved
  // (loadState === 'ready' && !dirty), so what gets copied always matches
  // what is displayed. Only the ordered PriceItem selection travels; target
  // geometry and Estimate-derived quantities remain entirely their own.
  // ---------------------------------------------------------------------------

  const startApply = async () => {
    setApplyState('counting');
    setApplyError(null);
    try {
      const surfacesResp = await fetchSurfaces(projectId, roomId);
      const openingLists = await Promise.all(
        surfacesResp.items.map((s) => fetchOpenings(projectId, roomId, s.id)),
      );
      const eligible = openingLists
        .flatMap((r) => r.items)
        .filter((o) => o.reveal_enabled && o.id !== openingId);
      setTargetCount(eligible.length);
      setApplyState('confirming');
    } catch (error) {
      setApplyError(describeError(error, t.reveals.apply_error));
      setApplyState('error');
    }
  };

  const handleApplyToRoomOpenings = async () => {
    setApplyState('applying');
    setApplyError(null);
    try {
      const result = await applyRevealWorksToRoom(projectId, roomId, surfaceId, openingId);
      setAppliedCount(result.target_count);
      // Authoritative refetch of this (source) opening's own reveal work
      // plan — the source is excluded from targets and never mutated by
      // the backend, but a refetch keeps this panel provably in sync with
      // the database rather than trusting client-side assumptions.
      const refreshed = await fetchRevealWorks(projectId, roomId, surfaceId, openingId);
      hydrate(refreshed.items);
      setApplyState('success');
    } catch (error) {
      setApplyError(describeError(error, t.reveals.apply_error));
      setApplyState('error');
    }
  };

  const handleApplyCancel = () => {
    setApplyState('idle');
    setApplyError(null);
    setTargetCount(null);
  };

  // Client-side search across display name, code, category/scope/unit labels.
  const filteredPickerItems = useMemo(() => {
    const q = pickerSearch.trim().toLowerCase();
    if (!q) return allPriceItems;
    return allPriceItems.filter((item) => {
      const name = priceItemDisplayName(item).toLowerCase();
      const scope = t.pricebook.scopes[item.price_scope]?.toLowerCase() ?? '';
      const unit = t.pricebook.units[item.unit]?.toLowerCase() ?? '';
      return (
        name.includes(q) ||
        scope.includes(q) ||
        unit.includes(q) ||
        item.code.toLowerCase().includes(q)
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allPriceItems, pickerSearch, t]);

  return (
    <section
      id={`reveal-work-editor-${openingId}`}
      aria-label={`reveal-work-editor-${openingId}`}
      className="mt-2 w-full min-w-0 rounded-xl border border-slate-200 bg-white p-3 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h5 className="text-sm font-bold text-slate-800 break-words">
            {t.reveals.work_section_title}
          </h5>
          <p className="text-xs text-slate-500 break-words">{openingLabel}</p>
        </div>
        <button
          type="button"
          aria-label={`close-reveal-work-${openingId}`}
          onClick={onClose}
          disabled={saving}
          className="min-h-[44px] px-3 rounded-xl border border-slate-300 bg-white text-slate-700 font-semibold text-sm disabled:opacity-60"
        >
          {t.common.close}
        </button>
      </div>

      {/* Backend-authoritative reveal geometry — display only, never recalculated here. */}
      {revealTotalLength != null && (
        <p aria-label={`reveal-geometry-${openingId}`} className="text-xs text-slate-500">
          {t.reveals.summary_title}:{' '}
          <strong className="text-slate-700">{formatMetric(revealTotalLength)} {t.pricebook.units.LM}</strong>
          {' · '}
          <strong className="text-slate-700">{formatMetric(revealTotalArea)} {t.common.unit_m2}</strong>
        </p>
      )}

      {loadState === 'loading' && (
        <p role="status" className="py-4 text-sm text-center text-slate-500">
          {t.reveals.work_loading}
        </p>
      )}

      {loadState === 'error' && (
        <div role="alert" className="space-y-2">
          <p className="text-sm font-semibold text-red-600">{t.reveals.work_error_load}</p>
          {loadError && loadError !== t.reveals.work_error_load && (
            <p className="text-xs text-red-600 break-words">{loadError}</p>
          )}
          <button
            type="button"
            aria-label={`retry-reveal-work-${openingId}`}
            onClick={() => setLoadAttempt((current) => current + 1)}
            className="w-full min-h-[44px] px-3 rounded-xl bg-blue-600 text-white font-semibold text-sm"
          >
            {t.work_plan.retry}
          </button>
        </div>
      )}

      {loadState === 'ready' && (
        <>
        <form
          aria-label={`reveal-work-form-${openingId}`}
          onSubmit={(event) => void handleSubmit(event)}
          className="space-y-3"
        >
          <div className="space-y-2 min-w-0">
            {draftOccurrences.length === 0 ? (
              <p className="text-sm text-slate-500">{t.reveals.work_no_works}</p>
            ) : (
              <ol aria-label={`reveal-works-${openingId}`} className="space-y-2">
                {draftOccurrences.map((occurrence, index) => {
                  const item = occurrence.summary;
                  return (
                    <li
                      key={occurrence.draftKey}
                      aria-label={`reveal-work-occurrence-${occurrence.draftKey}`}
                      className="min-w-0 rounded-lg border border-slate-200 p-2"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <span className="min-w-0 text-sm font-semibold text-slate-800 break-words">
                          {occurrenceDisplayName(item)}
                        </span>
                        <div className="flex items-center gap-1 shrink-0">
                          {item?.is_archived && (
                            <span className="text-xs text-red-600 mr-1">
                              {t.pricebook.archived_badge}
                            </span>
                          )}
                          <button
                            type="button"
                            aria-label={`reveal-move-up-${occurrence.draftKey}`}
                            onClick={() => handleMoveOccurrenceUp(index)}
                            disabled={saving || index === 0}
                            className="min-h-[44px] min-w-[36px] px-1 flex items-center justify-center text-sm font-bold text-slate-700 disabled:opacity-30"
                            title={t.work_plan.move_up}
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            aria-label={`reveal-move-down-${occurrence.draftKey}`}
                            onClick={() => handleMoveOccurrenceDown(index)}
                            disabled={saving || index === draftOccurrences.length - 1}
                            className="min-h-[44px] min-w-[36px] px-1 flex items-center justify-center text-sm font-bold text-slate-700 disabled:opacity-30"
                            title={t.work_plan.move_down}
                          >
                            ↓
                          </button>
                          <button
                            type="button"
                            aria-label={`reveal-remove-${occurrence.draftKey}`}
                            onClick={() => handleRemoveOccurrence(occurrence.draftKey)}
                            disabled={saving}
                            className="min-h-[44px] min-w-[44px] flex items-center justify-center text-xs text-red-600 disabled:opacity-60"
                          >
                            {t.work_plan.remove_work}
                          </button>
                        </div>
                      </div>
                      {item ? (
                        <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs text-slate-500">
                          <span>{t.pricebook.units[item.unit]}</span>
                          <span>{t.pricebook.scopes[item.price_scope]}</span>
                          <span aria-label={`reveal-occurrence-price-${occurrence.draftKey}`}>
                            {item.price === null
                              ? t.pricebook.price_not_set
                              : `${formatPrice(item.price)} ${item.currency === 'PLN' ? t.pricebook.currency_symbol : item.currency}`}
                          </span>
                        </div>
                      ) : (
                        <p className="mt-1 text-xs text-slate-500">{t.work_plan.unavailable_item}</p>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}

            <button
              type="button"
              aria-label={`open-reveal-picker-${openingId}`}
              onClick={() => void openPicker()}
              disabled={saving || pickerState === 'loading'}
              className="w-full min-h-[44px] px-3 rounded-xl border border-blue-600 text-blue-700 font-semibold text-sm disabled:opacity-60"
            >
              {t.work_plan.add_work}
            </button>
          </div>

          {saveError && (
            <div role="alert" className="space-y-1">
              <p className="text-sm font-semibold text-red-600">{t.reveals.work_error_save}</p>
              {saveError !== t.reveals.work_error_save && (
                <p className="text-xs text-red-600 break-words">{saveError}</p>
              )}
            </div>
          )}
          {saved && (
            <p role="status" className="text-sm text-slate-700">
              {t.reveals.work_saved}
            </p>
          )}

          <button
            type="submit"
            aria-label={`save-reveal-work-${openingId}`}
            disabled={!dirty || saving}
            className="w-full min-h-[44px] px-3 rounded-xl bg-blue-600 text-white font-semibold text-sm disabled:opacity-60"
          >
            {saving ? t.common.saving : t.common.save}
          </button>

          {/* Apply to all reveal-enabled openings in the room (Stage 10G.4) —
              only offered once the current selection is saved, so what gets
              copied always matches what is displayed here. */}
          {!dirty && (
            <div className="space-y-2 pt-1 border-t border-slate-200">
              {applyState === 'idle' && (
                <button
                  type="button"
                  aria-label={`apply-to-room-openings-${openingId}`}
                  onClick={() => void startApply()}
                  disabled={saving}
                  className="w-full min-h-[44px] px-3 rounded-xl border border-blue-600 text-blue-700 font-semibold text-sm disabled:opacity-60"
                >
                  {t.reveals.apply_to_openings}
                </button>
              )}
              {applyState === 'counting' && (
                <p role="status" className="py-2 text-sm text-center text-slate-500">
                  {t.reveals.applying}
                </p>
              )}
              {applyState === 'confirming' && (
                <div
                  aria-label={`apply-confirm-panel-${openingId}`}
                  className="rounded-xl border border-slate-200 p-3 space-y-2"
                >
                  <p className="text-sm text-slate-700 break-words">
                    {(baselineIds.length === 0
                      ? t.reveals.apply_confirm_empty
                      : t.reveals.apply_confirm
                    ).replace('{count}', String(targetCount ?? 0))}
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      aria-label={`apply-confirm-yes-${openingId}`}
                      onClick={() => void handleApplyToRoomOpenings()}
                      className="flex-1 min-h-[44px] px-3 rounded-xl bg-blue-600 text-white font-semibold text-sm"
                    >
                      {t.reveals.apply_confirm_yes}
                    </button>
                    <button
                      type="button"
                      aria-label={`apply-cancel-${openingId}`}
                      onClick={handleApplyCancel}
                      className="flex-1 min-h-[44px] px-3 rounded-xl border border-slate-300 text-slate-700 font-semibold text-sm"
                    >
                      {t.common.cancel}
                    </button>
                  </div>
                </div>
              )}
              {applyState === 'applying' && (
                <p role="status" className="py-2 text-sm text-center text-slate-500">
                  {t.reveals.applying}
                </p>
              )}
              {applyState === 'success' && (
                <div className="space-y-1">
                  <p role="status" className="text-sm text-slate-700">
                    {t.reveals.apply_success.replace('{count}', String(appliedCount ?? 0))}
                  </p>
                  <button
                    type="button"
                    aria-label={`apply-success-dismiss-${openingId}`}
                    onClick={handleApplyCancel}
                    className="w-full min-h-[44px] px-3 rounded-xl border border-slate-300 text-slate-700 text-sm font-medium"
                  >
                    {t.common.close}
                  </button>
                </div>
              )}
              {applyState === 'error' && (
                <div role="alert" className="space-y-1">
                  <p className="text-sm font-semibold text-red-600">{t.reveals.apply_error}</p>
                  {applyError && applyError !== t.reveals.apply_error && (
                    <p className="text-xs text-red-600 break-words">{applyError}</p>
                  )}
                  <button
                    type="button"
                    aria-label={`apply-error-dismiss-${openingId}`}
                    onClick={handleApplyCancel}
                    className="w-full min-h-[44px] px-3 rounded-xl border border-slate-300 text-slate-700 text-sm font-medium"
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
            aria-label={`reveal-picker-panel-${openingId}`}
            role="dialog"
            aria-modal="false"
            className="w-full min-w-0 rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2 mt-2"
          >
            <div className="flex items-center justify-between gap-2">
              <h6 className="text-sm font-semibold text-slate-800 break-words">
                {t.work_plan.picker_title}
              </h6>
              <button
                type="button"
                aria-label={`close-reveal-picker-${openingId}`}
                onClick={closePicker}
                className="min-h-[44px] min-w-[44px] flex items-center justify-center text-sm text-slate-500"
              >
                {t.work_plan.picker_close}
              </button>
            </div>

            {pickerState === 'loading' && (
              <p role="status" className="py-3 text-sm text-center text-slate-500">
                {t.work_plan.picker_loading}
              </p>
            )}

            {pickerState === 'error' && (
              <p role="alert" className="text-sm text-red-600">
                {pickerError ?? t.work_plan.picker_error}
              </p>
            )}

            {pickerState === 'ready' && (
              creatingPriceItem ? (
                <PriceItemForm
                  idPrefix={`reveal-new-price-item-${openingId}`}
                  lockedCategory="REVEAL"
                  onCancel={() => setCreatingPriceItem(false)}
                  onSaved={handlePriceItemCreated}
                />
              ) : (
                <>
                  <input
                    type="search"
                    aria-label={`reveal-picker-search-${openingId}`}
                    placeholder={t.work_plan.picker_search}
                    value={pickerSearch}
                    onChange={(e) => setPickerSearch(e.target.value)}
                    className="w-full min-h-[44px] rounded-xl border border-slate-300 px-3 py-2 text-sm bg-white text-slate-800"
                  />

                  {filteredPickerItems.length === 0 ? (
                    <p className="py-3 text-sm text-center text-slate-500">
                      {pickerSearch.trim() ? t.work_plan.picker_no_results : t.work_plan.picker_empty}
                    </p>
                  ) : (
                    <ul aria-label={`reveal-picker-list-${openingId}`} className="space-y-1 max-h-64 overflow-y-auto">
                      {filteredPickerItems.map((item) => (
                        <li key={item.id}>
                          <button
                            type="button"
                            aria-label={`reveal-picker-item-${item.id}`}
                            onClick={() => handlePickerSelect(item)}
                            className="w-full min-h-[44px] text-left px-3 py-2 rounded-lg hover:bg-white active:bg-white text-slate-800"
                          >
                            <div className="text-sm font-semibold break-words">
                              {priceItemDisplayName(item)}
                            </div>
                            <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-slate-500">
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
                    aria-label={`reveal-create-price-item-${openingId}`}
                    onClick={() => setCreatingPriceItem(true)}
                    className="w-full min-h-[44px] px-3 rounded-xl border border-dashed border-blue-400 text-blue-700 font-semibold text-sm"
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
          aria-label={`close-reveal-work-bottom-${openingId}`}
          onClick={onClose}
          disabled={saving}
          className="w-full min-h-[44px] px-3 rounded-xl border border-slate-300 bg-white text-slate-700 font-semibold text-sm disabled:opacity-60"
        >
          {t.common.close}
        </button>
        </>
      )}
    </section>
  );
}
