import { useCallback, useEffect, useState } from 'react';
import { addManualEstimateLine, deleteEstimateLine, getEstimate, patchEstimateLine, previewEstimateRegeneration, regenerateEstimate } from '../api/estimates';
import { useI18n } from '../hooks/useI18n';
import type { EstimateLineRead, EstimateLineUpdatePayload, EstimateRead, EstimateSummaryRead, EstimateStatusValue, LineOriginValue, LineChangeEntry, LineChangeTypeValue, ManualLineCreatePayload, RegenerationPreviewResponse } from '../types/estimate';
import { PRICE_UNITS, type PriceScopeValue, type PriceUnitValue } from '../types/priceItem';
import { sumDecimalStrings } from '../utils/decimalArithmetic';
import { formatDecimalMoney } from '../utils/format';
import { resolveKey } from '../utils/i18nKeys';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';

// Stage 10G.3C — the backend rejects LABOR_AND_MATERIAL for MANUAL lines (no
// PriceBook source to split into labor/material components), so the manual
// line form only ever offers the two scopes it actually accepts.
const MANUAL_LINE_SCOPES: readonly PriceScopeValue[] = ['LABOR', 'MATERIAL'];

interface EstimateShellProps {
  estimate: EstimateSummaryRead;
  onBack: () => void;
  selectedGroupKey: string | null;
  onGroupKeyChange: (key: string | null) => void;
}

interface EstimateGroup {
  key: string;
  rawDescription: string;
  scope: string;
  origin: LineOriginValue;
  isReveal: boolean;
  unit: string | null;
  quantity: string | null;
  unitPrice: string | null;
  amount: string | null;
  currency: string;
  lineCount: number;
  hasOverrides: boolean;
  lines: EstimateLineRead[];
}

// Deterministic, stable surface_id → subtle-tint mapping for atomic drill-down
// cards. Must depend only on surface_id (never array index / sort position),
// so the same surface always renders the same tint regardless of line order.
const SURFACE_TINT_PALETTE: readonly { bg: string; border: string }[] = [
  { bg: 'bg-blue-50', border: 'border-blue-100' },
  { bg: 'bg-emerald-50', border: 'border-emerald-100' },
  { bg: 'bg-amber-50', border: 'border-amber-100' },
  { bg: 'bg-rose-50', border: 'border-rose-100' },
  { bg: 'bg-violet-50', border: 'border-violet-100' },
  { bg: 'bg-teal-50', border: 'border-teal-100' },
];

const NEUTRAL_CARD_TINT = { bg: 'bg-white', border: 'border-slate-200' };

// FNV-1a 32-bit — cheap, stable, well-distributed for short UUID strings.
function hashSurfaceId(surfaceId: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < surfaceId.length; i++) {
    hash ^= surfaceId.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function surfaceCardTint(surfaceId: string | null): { bg: string; border: string } {
  if (surfaceId === null) return NEUTRAL_CARD_TINT;
  return SURFACE_TINT_PALETTE[hashSurfaceId(surfaceId) % SURFACE_TINT_PALETTE.length];
}

// Client-side shape guard only — never converts to Number. The backend
// remains the sole authority on whether a decimal string is acceptable.
function isValidDecimalString(value: string): boolean {
  return /^\d+(\.\d+)?$/.test(value.trim());
}

type PriceEditMode = 'value' | 'unresolved';

// Shared structural shape for compact provenance rendering — see the
// compactProvenanceLabel comment below for why this is reused rather than
// duplicated across EstimateLineRead and LineChangeEntry.
interface ProvenanceSource {
  room_name?: string | null;
  surface_name?: string | null;
  surface_type_value?: string | null;
  opening_id: string | null;
  opening_name?: string | null;
  opening_type_value?: string | null;
}

function getGroupKey(line: EstimateLineRead): string {
  if (line.origin === 'MANUAL' || line.price_item_id === null) {
    return `manual::${line.id}`;
  }
  const isReveal = line.opening_id !== null;
  return `planned::${line.price_item_id}::${line.scope}::${line.unit}::${isReveal ? 'reveal' : 'surface'}`;
}

function buildGroups(lines: EstimateLineRead[]): EstimateGroup[] {
  const order: string[] = [];
  const map = new Map<string, EstimateLineRead[]>();

  for (const line of lines) {
    const key = getGroupKey(line);
    if (!map.has(key)) {
      order.push(key);
      map.set(key, []);
    }
    map.get(key)!.push(line);
  }

  return order.map((key) => {
    const gLines = map.get(key)!;
    const first = gLines[0];

    const unitSet = new Set(gLines.map((l) => l.unit));
    const sameUnit = unitSet.size === 1;
    const aggregateQty = sameUnit ? sumDecimalStrings(gLines.map((l) => l.quantity)) : null;

    const hasAnyPriceOverride = gLines.some((l) => l.price_override);
    const priceSet = new Set(gLines.map((l) => l.unit_price));
    const uniformUnitPrice =
      !hasAnyPriceOverride && priceSet.size === 1 ? first.unit_price : null;

    const hasAnyNullAmount = gLines.some((l) => l.amount === null);
    const aggregateAmount = hasAnyNullAmount
      ? null
      : sumDecimalStrings(gLines.map((l) => l.amount as string));

    return {
      key,
      rawDescription: first.description,
      scope: first.scope,
      origin: first.origin,
      isReveal: first.opening_id !== null,
      unit: sameUnit ? first.unit : null,
      quantity: aggregateQty,
      unitPrice: uniformUnitPrice,
      amount: aggregateAmount,
      currency: first.currency,
      lineCount: gLines.length,
      hasOverrides: gLines.some((l) => l.quantity_overridden || l.price_override),
      lines: gLines,
    };
  });
}

export function EstimateShell({ estimate, selectedGroupKey, onGroupKeyChange }: EstimateShellProps) {
  const { t } = useI18n();
  const [detail, setDetail] = useState<EstimateRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getEstimate(estimate.project_id, estimate.id);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.estimates.error_load_detail);
    } finally {
      setLoading(false);
    }
  }, [estimate.project_id, estimate.id, t.estimates.error_load_detail]);

  useEffect(() => {
    void load();
  }, [load]);

  // Stage 10G.3A — atomic line editing state. One line editable at a time;
  // the backend EstimateLine remains authoritative — every successful
  // mutation triggers a full refetch rather than a local/optimistic patch.
  const [editingLineId, setEditingLineId] = useState<string | null>(null);
  const [editQuantity, setEditQuantity] = useState('');
  const [editPriceMode, setEditPriceMode] = useState<PriceEditMode>('value');
  const [editUnitPrice, setEditUnitPrice] = useState('');
  const [actionBusyLineId, setActionBusyLineId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ lineId: string; message: string } | null>(null);

  const beginEdit = (line: EstimateLineRead) => {
    setEditingLineId(line.id);
    setEditQuantity(line.quantity);
    setEditPriceMode(line.unit_price === null ? 'unresolved' : 'value');
    setEditUnitPrice(line.unit_price ?? '');
    setActionError(null);
  };

  const cancelEdit = () => {
    setEditingLineId(null);
    setEditQuantity('');
    setEditPriceMode('value');
    setEditUnitPrice('');
    setActionError(null);
  };

  const submitEdit = async (line: EstimateLineRead) => {
    const payload: EstimateLineUpdatePayload = {};

    if (editQuantity !== line.quantity) {
      if (!isValidDecimalString(editQuantity)) {
        setActionError({ lineId: line.id, message: t.estimates.line_edit_invalid_number });
        return;
      }
      payload.quantity = editQuantity;
    }

    if (editPriceMode === 'unresolved') {
      if (line.unit_price !== null) payload.unit_price = null;
    } else {
      const currentPrice = line.unit_price ?? '';
      if (editUnitPrice !== currentPrice) {
        if (!isValidDecimalString(editUnitPrice)) {
          setActionError({ lineId: line.id, message: t.estimates.line_edit_invalid_number });
          return;
        }
        payload.unit_price = editUnitPrice;
      }
    }

    if (Object.keys(payload).length === 0) {
      cancelEdit();
      return;
    }

    setActionBusyLineId(line.id);
    setActionError(null);
    try {
      await patchEstimateLine(estimate.project_id, estimate.id, line.id, payload);
      await load();
      cancelEdit();
    } catch (err) {
      setActionError({
        lineId: line.id,
        message: err instanceof Error ? err.message : t.estimates.line_edit_error,
      });
    } finally {
      setActionBusyLineId(null);
    }
  };

  const submitReset = async (line: EstimateLineRead, field: 'quantity' | 'price') => {
    setActionBusyLineId(line.id);
    setActionError(null);
    try {
      await patchEstimateLine(
        estimate.project_id,
        estimate.id,
        line.id,
        field === 'quantity' ? { reset_quantity_override: true } : { reset_price_override: true },
      );
      await load();
    } catch (err) {
      setActionError({
        lineId: line.id,
        message: err instanceof Error ? err.message : t.estimates.line_edit_error,
      });
    } finally {
      setActionBusyLineId(null);
    }
  };

  // Stage 10G.3A — group-level bulk price editing. There is no bulk/
  // transactional backend endpoint: this reuses the existing atomic PATCH
  // EstimateLine call once per line in group.lines (the authoritative,
  // already-accepted 10G.2 grouping key — never a text/description search).
  // The loop stops on the first failure so a partial group update is never
  // reported as a full success; every attempt (success or failure) refetches
  // the authoritative Estimate afterward.
  const [optionsOpenGroupKey, setOptionsOpenGroupKey] = useState<string | null>(null);
  const [editingGroupPriceKey, setEditingGroupPriceKey] = useState<string | null>(null);
  const [groupPriceMode, setGroupPriceMode] = useState<PriceEditMode>('value');
  const [groupUnitPrice, setGroupUnitPrice] = useState('');
  const [groupPriceMixed, setGroupPriceMixed] = useState(false);
  const [groupActionBusyKey, setGroupActionBusyKey] = useState<string | null>(null);
  const [groupActionError, setGroupActionError] = useState<{ groupKey: string; message: string } | null>(null);

  const closeGroupOptions = (groupKey: string) => {
    setOptionsOpenGroupKey(null);
    if (editingGroupPriceKey === groupKey) {
      setEditingGroupPriceKey(null);
      setGroupUnitPrice('');
      setGroupPriceMode('value');
      setGroupPriceMixed(false);
      setGroupActionError(null);
    }
  };

  const beginGroupPriceEdit = (group: EstimateGroup) => {
    const prices = group.lines.map((l) => l.unit_price);
    const uniquePrices = new Set(prices);
    if (uniquePrices.size === 1) {
      const value = prices[0];
      setGroupPriceMode(value === null ? 'unresolved' : 'value');
      setGroupUnitPrice(value ?? '');
      setGroupPriceMixed(false);
    } else {
      setGroupPriceMode('value');
      setGroupUnitPrice('');
      setGroupPriceMixed(true);
    }
    setEditingGroupPriceKey(group.key);
    setGroupActionError(null);
  };

  const cancelGroupPriceEdit = () => {
    setEditingGroupPriceKey(null);
    setGroupUnitPrice('');
    setGroupPriceMode('value');
    setGroupPriceMixed(false);
    setGroupActionError(null);
  };

  const submitGroupPriceEdit = async (group: EstimateGroup) => {
    let payload: EstimateLineUpdatePayload;
    if (groupPriceMode === 'unresolved') {
      payload = { unit_price: null };
    } else {
      if (!isValidDecimalString(groupUnitPrice)) {
        setGroupActionError({ groupKey: group.key, message: t.estimates.line_edit_invalid_number });
        return;
      }
      payload = { unit_price: groupUnitPrice };
    }

    setGroupActionBusyKey(group.key);
    setGroupActionError(null);
    try {
      for (const line of group.lines) {
        await patchEstimateLine(estimate.project_id, estimate.id, line.id, payload);
      }
      await load();
      cancelGroupPriceEdit();
    } catch {
      await load();
      setGroupActionError({ groupKey: group.key, message: t.estimates.group_bulk_partial_failure });
    } finally {
      setGroupActionBusyKey(null);
    }
  };

  const submitGroupPriceReset = async (group: EstimateGroup) => {
    setGroupActionBusyKey(group.key);
    setGroupActionError(null);
    try {
      for (const line of group.lines) {
        await patchEstimateLine(estimate.project_id, estimate.id, line.id, { reset_price_override: true });
      }
      await load();
    } catch {
      await load();
      setGroupActionError({ groupKey: group.key, message: t.estimates.group_bulk_partial_failure });
    } finally {
      setGroupActionBusyKey(null);
    }
  };

  // Stage 10G.3B — regeneration preview/confirm. Preview is strictly
  // read-only (regenerate-preview never mutates); only explicit confirmation
  // calls the mutating regenerate endpoint. Checks the WHOLE project
  // estimate, never scoped to the currently opened room or group.
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewResult, setPreviewResult] = useState<RegenerationPreviewResponse | null>(null);
  const [regenerateBusy, setRegenerateBusy] = useState(false);
  const [regenerateError, setRegenerateError] = useState<string | null>(null);

  const openPreview = async () => {
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewResult(null);
    setRegenerateError(null);
    try {
      const result = await previewEstimateRegeneration(estimate.project_id, estimate.id);
      setPreviewResult(result);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : t.estimates.preview_error);
    } finally {
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewOpen(false);
    setPreviewLoading(false);
    setPreviewError(null);
    setPreviewResult(null);
    setRegenerateError(null);
  };

  const confirmRegenerate = async () => {
    setRegenerateBusy(true);
    setRegenerateError(null);
    try {
      await regenerateEstimate(estimate.project_id, estimate.id);
      await load();
      closePreview();
    } catch (err) {
      setRegenerateError(err instanceof Error ? err.message : t.estimates.preview_regenerate_error);
    } finally {
      setRegenerateBusy(false);
    }
  };

  // Stage 10G.3C — manual EstimateLine creation. Belongs to the Estimate as a
  // whole (shared header area, like "Sprawdź zmiany"), never scoped to a
  // group/room. No optimistic insertion — success always triggers an
  // authoritative refetch via load().
  const [manualFormOpen, setManualFormOpen] = useState(false);
  const [manualDescription, setManualDescription] = useState('');
  const [manualScope, setManualScope] = useState<PriceScopeValue>('LABOR');
  const [manualUnit, setManualUnit] = useState<PriceUnitValue>('M2');
  const [manualQuantity, setManualQuantity] = useState('1');
  const [manualPriceMode, setManualPriceMode] = useState<PriceEditMode>('value');
  const [manualUnitPrice, setManualUnitPrice] = useState('');
  const [manualBusy, setManualBusy] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);

  const openManualForm = () => {
    setManualFormOpen(true);
    setManualDescription('');
    setManualScope('LABOR');
    setManualUnit('M2');
    setManualQuantity('1');
    setManualPriceMode('value');
    setManualUnitPrice('');
    setManualError(null);
  };

  const closeManualForm = () => {
    setManualFormOpen(false);
    setManualError(null);
  };

  const submitManualLine = async () => {
    if (detail === null) return;

    const trimmedDescription = manualDescription.trim();
    if (trimmedDescription.length === 0) {
      setManualError(t.estimates.manual_line_description_required);
      return;
    }
    if (!isValidDecimalString(manualQuantity)) {
      setManualError(t.estimates.line_edit_invalid_number);
      return;
    }

    let unitPrice: string | null;
    if (manualPriceMode === 'unresolved') {
      unitPrice = null;
    } else {
      if (!isValidDecimalString(manualUnitPrice)) {
        setManualError(t.estimates.line_edit_invalid_number);
        return;
      }
      unitPrice = manualUnitPrice;
    }

    const payload: ManualLineCreatePayload = {
      description: trimmedDescription,
      scope: manualScope,
      unit: manualUnit,
      quantity: manualQuantity,
      unit_price: unitPrice,
      currency: detail.currency,
    };

    setManualBusy(true);
    setManualError(null);
    try {
      await addManualEstimateLine(estimate.project_id, estimate.id, payload);
      await load();
      closeManualForm();
    } catch (err) {
      setManualError(err instanceof Error ? err.message : t.estimates.manual_line_error);
    } finally {
      setManualBusy(false);
    }
  };

  // Stage 10G.3C — MANUAL line deletion. DRAFT-only, MANUAL-only (enforced
  // server-side too); requires an explicit confirmation step.
  const [deleteConfirmLineId, setDeleteConfirmLineId] = useState<string | null>(null);
  const [deleteBusyLineId, setDeleteBusyLineId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<{ lineId: string; message: string } | null>(null);

  const requestDeleteLine = (lineId: string) => {
    setDeleteConfirmLineId(lineId);
    setDeleteError(null);
  };

  const cancelDeleteLine = () => {
    setDeleteConfirmLineId(null);
  };

  const confirmDeleteLine = async (line: EstimateLineRead) => {
    setDeleteBusyLineId(line.id);
    setDeleteError(null);
    try {
      await deleteEstimateLine(estimate.project_id, estimate.id, line.id);
      await load();
      setDeleteConfirmLineId(null);
    } catch (err) {
      setDeleteError({
        lineId: line.id,
        message: err instanceof Error ? err.message : t.estimates.manual_line_delete_error,
      });
    } finally {
      setDeleteBusyLineId(null);
    }
  };

  const changeCategoryLabel = (changeType: LineChangeTypeValue): string => {
    if (changeType === 'ADDED') return t.estimates.preview_category_added;
    if (changeType === 'REMOVED') return t.estimates.preview_category_removed;
    return t.estimates.preview_category_updated;
  };

  // Never invents a value for the side that doesn't apply (ADDED has no
  // "old", REMOVED has no "new"); collapses to a single value when an
  // UPDATED entry's quantity/price didn't actually change (e.g. only the
  // description changed) instead of showing "X -> X".
  const changeQuantityDisplay = (entry: LineChangeEntry): string => {
    const fmt = (v: string | null) => (v !== null ? `${v} ${entry.unit}` : '—');
    if (entry.change_type === 'ADDED') return fmt(entry.new_source_quantity);
    if (entry.change_type === 'REMOVED') return fmt(entry.old_source_quantity);
    if (entry.old_source_quantity === entry.new_source_quantity) return fmt(entry.new_source_quantity);
    return `${fmt(entry.old_source_quantity)} → ${fmt(entry.new_source_quantity)}`;
  };

  const changePriceDisplay = (entry: LineChangeEntry): string => {
    const fmt = (v: string | null) =>
      v !== null ? `${formatDecimalMoney(v)} ${estimate.currency}` : t.estimates.price_not_set;
    if (entry.change_type === 'ADDED') return fmt(entry.new_unit_price);
    if (entry.change_type === 'REMOVED') return fmt(entry.old_unit_price);
    if (entry.old_unit_price === entry.new_unit_price) return fmt(entry.new_unit_price);
    return `${fmt(entry.old_unit_price)} → ${fmt(entry.new_unit_price)}`;
  };

  const statusLabel = (status: EstimateStatusValue): string => {
    const labels: Record<EstimateStatusValue, string> = {
      DRAFT: t.estimates.status_draft,
      FINAL: t.estimates.status_final,
      ACCEPTED: t.estimates.status_accepted,
      ARCHIVED: t.estimates.status_archived,
    };
    return labels[status];
  };

  const statusBadgeClass = (status: EstimateStatusValue): string => {
    switch (status) {
      case 'DRAFT': return 'bg-blue-100 text-blue-700';
      case 'FINAL': return 'bg-emerald-100 text-emerald-700';
      case 'ACCEPTED': return 'bg-violet-100 text-violet-700';
      case 'ARCHIVED': return 'bg-slate-100 text-slate-500';
    }
  };

  const originLabel = (line: EstimateLineRead): string => {
    if (line.origin === 'MANUAL') return t.estimates.origin_manual;
    if (line.opening_id !== null) return t.estimates.origin_reveal_work;
    return t.estimates.origin_planned_work;
  };

  const originLabelFromGroup = (group: EstimateGroup): string => {
    if (group.origin === 'MANUAL') return t.estimates.origin_manual;
    if (group.isReveal) return t.estimates.origin_reveal_work;
    return t.estimates.origin_planned_work;
  };

  const scopeLabel = (scope: string): string => {
    if (scope === 'LABOR') return t.estimates.scope_labor;
    if (scope === 'MATERIAL') return t.estimates.scope_material;
    if (scope === 'LABOR_AND_MATERIAL') return t.estimates.scope_labor_and_material;
    return scope;
  };

  // The `estimate` prop is a point-in-time EstimateSummaryRead handed down by
  // the parent (e.g. from the version list) and is never refreshed by this
  // component. Once `detail` has been fetched at least once, it is the only
  // authoritative source for anything that a mutation here (price/quantity
  // edit, regeneration, ...) can change — total and currency above all.
  // Falling back to the prop only covers the brief window before the first
  // successful load(); `detail` is never cleared afterward, even on a later
  // reload error, so it never regresses to the stale prop once available.
  const headerSource: EstimateSummaryRead = detail ?? estimate;

  const header = (
    <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-2">
      <div className="flex items-center gap-2 flex-wrap min-w-0">
        <h2 className="font-bold text-slate-900 text-base shrink-0">
          {t.estimates.title} — {t.estimates.version} {headerSource.version}
        </h2>
        <span
          aria-label="estimate-shell-status"
          className={`text-xs px-2.5 py-0.5 rounded-full font-medium shrink-0 ${statusBadgeClass(headerSource.status)}`}
        >
          {statusLabel(headerSource.status)}
        </span>
      </div>

      {headerSource.name && (
        <p className="text-sm text-slate-600 break-words min-w-0">{headerSource.name}</p>
      )}

      <div className="text-xs text-slate-500 space-y-0.5">
        <div>
          <span className="text-slate-400">{t.estimates.total}: </span>
          <span className="font-medium text-slate-700" aria-label="estimate-shell-total">
            {headerSource.total !== null
              ? `${formatDecimalMoney(headerSource.total)} ${headerSource.currency}`
              : '—'}
          </span>
        </div>
      </div>
    </div>
  );

  if (loading) {
    return (
      <article aria-label="estimate-shell" className="space-y-3">
        {header}
        <p aria-label="estimate-lines-loading" className="text-sm text-slate-500 text-center py-6">
          {t.estimates.lines_loading}
        </p>
      </article>
    );
  }

  if (error) {
    return (
      <article aria-label="estimate-shell" className="space-y-3">
        {header}
        <div className="space-y-2 py-4 text-center">
          <p role="alert" aria-label="estimate-lines-error" className="text-sm text-red-600">
            {error}
          </p>
          <button
            type="button"
            onClick={() => void load()}
            className="text-sm text-blue-600 font-medium hover:underline"
          >
            {t.estimates.retry}
          </button>
        </div>
      </article>
    );
  }

  if (!detail || detail.lines.length === 0) {
    return (
      <article aria-label="estimate-shell" className="space-y-3">
        {header}
        <div
          aria-label="estimate-lines-empty"
          className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-1"
        >
          <p className="text-sm font-medium text-slate-700">{t.estimates.lines_empty_title}</p>
          <p className="text-xs text-slate-500">{t.estimates.lines_empty_description}</p>
        </div>
      </article>
    );
  }

  const groups = buildGroups(detail.lines);

  const surfaceDisplayLabels = {
    wall: t.surfaces.wall,
    floor: t.surfaces.floor,
    ceiling: t.surfaces.ceiling,
  };

  // Shared shape for anything that can carry live-resolved room/surface/
  // opening presentation metadata — both EstimateLineRead and (since the
  // 10G.3B provenance follow-up) LineChangeEntry satisfy this structurally,
  // so the compact provenance logic is never duplicated between the two.
  //
  // Preferred order: 1) explicit surface_name if non-empty, 2) canonical
  // localized surface type if known, 3) omit — never invent a name or guess
  // from array order. Presentation metadata may be null OR absent
  // (undefined) at runtime, so every check below must treat them the same.
  const provenanceSurfaceLabel = (source: ProvenanceSource): string | null => {
    const surfaceName = source.surface_name;
    if (surfaceName !== null && surfaceName !== undefined && surfaceName.trim().length > 0) {
      return getSurfaceDisplayName(
        { name: surfaceName, surface_type: source.surface_type_value },
        surfaceDisplayLabels,
      );
    }
    if (source.surface_type_value === 'WALL') return surfaceDisplayLabels.wall;
    if (source.surface_type_value === 'FLOOR') return surfaceDisplayLabels.floor;
    if (source.surface_type_value === 'CEILING') return surfaceDisplayLabels.ceiling;
    return null;
  };

  const provenanceOpeningLabel = (source: ProvenanceSource): string | null => {
    if (source.opening_id === null) return null;
    if (source.opening_name !== null && source.opening_name !== undefined) return source.opening_name;
    if (source.opening_type_value === 'DOOR') return t.openings.door;
    if (source.opening_type_value === 'WINDOW') return t.openings.window;
    return t.openings.other;
  };

  // Compact "room — surface — opening" provenance, replacing the previous
  // labeled Pomieszczenie/Powierzchnia/Otwór rows. Missing pieces are simply
  // omitted — never invent a placeholder for a part that isn't available.
  const compactProvenanceLabel = (source: ProvenanceSource): string | null => {
    const parts: string[] = [];
    if (source.room_name !== null && source.room_name !== undefined) parts.push(source.room_name);
    const surfaceLabel = provenanceSurfaceLabel(source);
    if (surfaceLabel !== null) parts.push(surfaceLabel);
    const openingLabel = provenanceOpeningLabel(source);
    if (openingLabel !== null) parts.push(openingLabel);
    return parts.length > 0 ? parts.join(' — ') : null;
  };

  // Stage 10G.3B — "Sprawdź zmiany" lives in the shared header area (not on
  // every group card) and always checks the WHOLE project estimate, never
  // scoped to the currently opened room/group. DRAFT-only, never rendered
  // (not just disabled) for FINAL/ACCEPTED/ARCHIVED.
  const regenerationSection = detail.status === 'DRAFT' && (
    <div
      aria-label="estimate-regeneration"
      className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm space-y-2"
    >
      {!previewOpen ? (
        <button
          type="button"
          aria-label="estimate-check-changes-action"
          onClick={() => void openPreview()}
          className="w-full min-h-[44px] px-3 text-sm font-medium text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-50"
        >
          {t.estimates.check_changes_action}
        </button>
      ) : (
        <div aria-label="estimate-regeneration-panel" className="space-y-2">
          {previewLoading && (
            <p aria-label="estimate-regeneration-loading" className="text-sm text-slate-500 text-center py-2">
              {t.estimates.preview_loading}
            </p>
          )}

          {!previewLoading && previewError !== null && (
            <div className="space-y-2">
              <p
                role="alert"
                aria-label="estimate-regeneration-error"
                className="text-sm text-red-600 break-words min-w-0"
              >
                {previewError}
              </p>
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  aria-label="estimate-regeneration-retry"
                  onClick={() => void openPreview()}
                  className="flex-1 min-h-[44px] bg-blue-600 text-white text-sm font-medium rounded-lg px-3"
                >
                  {t.estimates.preview_retry}
                </button>
                <button
                  type="button"
                  aria-label="estimate-regeneration-close"
                  onClick={closePreview}
                  className="flex-1 min-h-[44px] border border-slate-300 text-slate-600 text-sm font-medium rounded-lg px-3"
                >
                  {t.estimates.preview_close}
                </button>
              </div>
            </div>
          )}

          {!previewLoading && previewError === null && previewResult !== null && (
            previewResult.changes.length === 0 ? (
              <div aria-label="estimate-regeneration-no-changes" className="space-y-1.5">
                <p className="text-sm font-medium text-slate-700">{t.estimates.preview_no_changes_title}</p>
                <p className="text-xs text-slate-500">{t.estimates.preview_no_changes_description}</p>
                <button
                  type="button"
                  aria-label="estimate-regeneration-close"
                  onClick={closePreview}
                  className="w-full min-h-[44px] border border-slate-300 text-slate-600 text-sm font-medium rounded-lg px-3"
                >
                  {t.estimates.preview_close}
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {(['ADDED', 'UPDATED', 'REMOVED'] as const).map((changeType) => {
                  const entries = previewResult.changes.filter((c) => c.change_type === changeType);
                  if (entries.length === 0) return null;
                  return (
                    <div
                      key={changeType}
                      aria-label={`estimate-regeneration-category-${changeType}`}
                      className="space-y-1.5"
                    >
                      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                        {changeCategoryLabel(changeType)}
                      </p>
                      {entries.map((entry, i) => {
                        const entryProvenance = compactProvenanceLabel(entry);
                        return (
                        <div
                          key={`${changeType}-${i}`}
                          aria-label={`estimate-regeneration-change-${changeType}-${i}`}
                          className="border border-slate-200 rounded-lg p-2 space-y-1"
                        >
                          {entryProvenance !== null && (
                            <p
                              aria-label={`estimate-regeneration-change-provenance-${changeType}-${i}`}
                              className="text-xs text-slate-500 break-words min-w-0"
                            >
                              {entryProvenance}
                            </p>
                          )}
                          <p
                            aria-label={`estimate-regeneration-change-description-${changeType}-${i}`}
                            className="text-sm text-slate-900 break-words min-w-0"
                          >
                            {resolveKey(t, entry.description)}
                          </p>
                          <div className="text-xs text-slate-600 flex items-baseline gap-1 flex-wrap min-w-0">
                            <span aria-label={`estimate-regeneration-change-quantity-${changeType}-${i}`}>
                              {changeQuantityDisplay(entry)}
                            </span>
                            <span className="text-slate-400">×</span>
                            <span aria-label={`estimate-regeneration-change-price-${changeType}-${i}`}>
                              {changePriceDisplay(entry)}
                            </span>
                          </div>
                          {(entry.quantity_overridden || entry.price_override) && (
                            <div
                              aria-label={`estimate-regeneration-change-override-${changeType}-${i}`}
                              className="text-xs text-amber-700 space-y-0.5"
                            >
                              {entry.quantity_overridden && <p>{t.estimates.quantity_overridden}</p>}
                              {entry.price_override && <p>{t.estimates.price_overridden}</p>}
                            </div>
                          )}
                        </div>
                        );
                      })}
                    </div>
                  );
                })}

                <div className="flex items-center gap-2 flex-wrap pt-1">
                  <button
                    type="button"
                    aria-label="estimate-regeneration-confirm"
                    onClick={() => void confirmRegenerate()}
                    disabled={regenerateBusy}
                    className="flex-1 min-h-[44px] bg-blue-600 text-white text-sm font-medium rounded-lg px-3 disabled:opacity-60"
                  >
                    {regenerateBusy ? t.estimates.preview_updating : t.estimates.preview_confirm}
                  </button>
                  <button
                    type="button"
                    aria-label="estimate-regeneration-cancel"
                    onClick={closePreview}
                    disabled={regenerateBusy}
                    className="flex-1 min-h-[44px] border border-slate-300 text-slate-600 text-sm font-medium rounded-lg px-3 disabled:opacity-60"
                  >
                    {t.estimates.preview_cancel}
                  </button>
                </div>

                {regenerateError !== null && (
                  <p
                    role="alert"
                    aria-label="estimate-regeneration-confirm-error"
                    className="text-xs text-red-600 break-words min-w-0"
                  >
                    {regenerateError}
                  </p>
                )}
              </div>
            )
          )}
        </div>
      )}
    </div>
  );

  // Stage 10G.3C — "+ Dodaj pozycję" belongs to the Estimate as a whole
  // (shared header area, like regenerationSection above), never scoped to a
  // group/room/surface. DRAFT-only, never rendered for immutable estimates.
  const manualLineSection = detail.status === 'DRAFT' && (
    <div
      aria-label="estimate-manual-line"
      className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm space-y-2"
    >
      {!manualFormOpen ? (
        <button
          type="button"
          aria-label="estimate-add-manual-line-action"
          onClick={openManualForm}
          className="w-full min-h-[44px] px-3 text-sm font-medium text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-50"
        >
          {t.estimates.add_manual_line_action}
        </button>
      ) : (
        <div aria-label="estimate-manual-line-form" className="space-y-2">
          <label className="block text-xs text-slate-500">
            <span className="block mb-0.5">{t.estimates.manual_line_description_label}</span>
            <textarea
              aria-label="manual-line-description"
              value={manualDescription}
              onChange={(e) => setManualDescription(e.target.value)}
              placeholder={t.estimates.manual_line_description_placeholder}
              rows={2}
              className="w-full border border-slate-300 rounded-lg px-2 py-2 text-sm bg-white resize-none"
            />
          </label>

          <label className="block text-xs text-slate-500">
            <span className="block mb-0.5">{t.estimates.manual_line_scope_label}</span>
            <select
              aria-label="manual-line-scope"
              value={manualScope}
              onChange={(e) => setManualScope(e.target.value as PriceScopeValue)}
              className="w-full border border-slate-300 rounded-lg px-2 min-h-[44px] text-sm bg-white"
            >
              {MANUAL_LINE_SCOPES.map((scope) => (
                <option key={scope} value={scope}>{scopeLabel(scope)}</option>
              ))}
            </select>
          </label>

          <label className="block text-xs text-slate-500">
            <span className="block mb-0.5">{t.estimates.manual_line_unit_label}</span>
            <select
              aria-label="manual-line-unit"
              value={manualUnit}
              onChange={(e) => setManualUnit(e.target.value as PriceUnitValue)}
              className="w-full border border-slate-300 rounded-lg px-2 min-h-[44px] text-sm bg-white"
            >
              {PRICE_UNITS.map((unit) => (
                <option key={unit} value={unit}>{t.pricebook.units[unit]}</option>
              ))}
            </select>
          </label>

          <label className="block text-xs text-slate-500">
            <span className="block mb-0.5">{t.estimates.line_edit_quantity_label}</span>
            <input
              type="text"
              inputMode="decimal"
              aria-label="manual-line-quantity"
              value={manualQuantity}
              onChange={(e) => setManualQuantity(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-2 min-h-[44px] text-sm bg-white"
            />
          </label>

          <div className="text-xs text-slate-500 space-y-1.5">
            <span className="block">{t.estimates.line_edit_price_label}</span>
            <label className="flex items-center gap-2 min-h-[44px]">
              <input
                type="checkbox"
                aria-label="manual-line-price-unresolved"
                checked={manualPriceMode === 'unresolved'}
                onChange={(e) => setManualPriceMode(e.target.checked ? 'unresolved' : 'value')}
                className="w-5 h-5 shrink-0"
              />
              <span>{t.estimates.line_edit_price_unresolved}</span>
            </label>
            {manualPriceMode === 'value' && (
              <input
                type="text"
                inputMode="decimal"
                aria-label="manual-line-price"
                value={manualUnitPrice}
                onChange={(e) => setManualUnitPrice(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-2 min-h-[44px] text-sm bg-white"
              />
            )}
          </div>

          {manualError !== null && (
            <p
              role="alert"
              aria-label="estimate-manual-line-error"
              className="text-xs text-red-600 break-words min-w-0"
            >
              {manualError}
            </p>
          )}

          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              aria-label="estimate-manual-line-save"
              onClick={() => void submitManualLine()}
              disabled={manualBusy}
              className="flex-1 min-h-[44px] bg-blue-600 text-white text-sm font-medium rounded-lg px-3 disabled:opacity-60"
            >
              {manualBusy ? t.estimates.manual_line_saving : t.estimates.manual_line_save}
            </button>
            <button
              type="button"
              aria-label="estimate-manual-line-cancel"
              onClick={closeManualForm}
              disabled={manualBusy}
              className="flex-1 min-h-[44px] border border-slate-300 text-slate-600 text-sm font-medium rounded-lg px-3 disabled:opacity-60"
            >
              {t.estimates.line_edit_cancel}
            </button>
          </div>
        </div>
      )}
    </div>
  );

  // Detail view: show individual lines for the selected group
  if (selectedGroupKey !== null) {
    const selectedGroup = groups.find((g) => g.key === selectedGroupKey);
    const linesToShow = selectedGroup ? selectedGroup.lines : [];

    return (
      <article aria-label="estimate-shell" className="space-y-3">
        {header}
        {regenerationSection}
        {manualLineSection}

        <button
          type="button"
          aria-label="estimate-detail-back"
          onClick={() => onGroupKeyChange(null)}
          className="w-full bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm text-left text-sm font-medium text-blue-600 hover:bg-slate-50 transition min-h-[44px]"
        >
          {t.estimates.detail_back}
        </button>

        <div aria-label="estimate-lines" className="space-y-2">
          {linesToShow.map((line) => {
            const compactProvenance = compactProvenanceLabel(line);
            const tint = surfaceCardTint(line.surface_id);
            // Stage 10G.3A polish — the footer (edit panel / error / reset
            // buttons) only renders when it has something to show, so a
            // DRAFT line with no overrides and not mid-edit never leaves a
            // stray empty bordered strip now that Edytuj lives in the header.
            const hasDraftFooterContent =
              editingLineId === line.id ||
              (actionError !== null && actionError.lineId === line.id) ||
              line.quantity_overridden ||
              (line.price_override && line.origin !== 'MANUAL') ||
              // Stage 10G.3C — a MANUAL line always offers deletion in DRAFT.
              line.origin === 'MANUAL' ||
              deleteConfirmLineId === line.id ||
              (deleteError !== null && deleteError.lineId === line.id);
            return (
              <div
                key={line.id}
                aria-label={`estimate-line-${line.position}`}
                className={`${tint.bg} border ${tint.border} rounded-2xl p-3 shadow-sm space-y-1.5`}
              >
                <div className="flex items-start justify-between gap-1.5 flex-wrap min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap min-w-0 flex-1">
                    <span
                      aria-label={`line-origin-${line.position}`}
                      className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-medium shrink-0"
                    >
                      {originLabel(line)}
                    </span>
                    <span
                      aria-label={`line-scope-${line.position}`}
                      className="text-xs px-2 py-0.5 rounded-full bg-slate-50 text-slate-500 border border-slate-200 shrink-0"
                    >
                      {scopeLabel(line.scope)}
                    </span>
                    {compactProvenance !== null && (
                      <span
                        aria-label={`line-provenance-${line.position}`}
                        className="text-xs text-slate-500 break-words min-w-0"
                      >
                        {compactProvenance}
                      </span>
                    )}
                  </div>

                  {/* Stage 10G.3A polish — Edytuj sits top-right, beside the
                      badge/provenance header, per owner-approved placement. */}
                  {detail.status === 'DRAFT' && editingLineId !== line.id && (
                    <button
                      type="button"
                      aria-label={`line-edit-action-${line.position}`}
                      onClick={() => beginEdit(line)}
                      className="shrink-0 min-h-[44px] px-3 text-xs font-medium text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-50"
                    >
                      {t.estimates.line_edit_action}
                    </button>
                  )}
                </div>

                <p
                  aria-label={`line-description-${line.position}`}
                  className="text-sm font-medium text-slate-900 break-words min-w-0"
                >
                  {resolveKey(t, line.description)}
                </p>

                <div className="text-xs text-slate-600 space-y-0.5">
                  <div className="flex items-baseline gap-1 flex-wrap min-w-0">
                    <span aria-label={`line-quantity-${line.position}`} className="shrink-0">
                      {line.quantity} {line.unit}
                    </span>
                    <span className="text-slate-400 shrink-0">×</span>
                    <span aria-label={`line-unit-price-${line.position}`} className="shrink-0">
                      {line.unit_price !== null
                        ? `${formatDecimalMoney(line.unit_price)} ${line.currency}`
                        : t.estimates.price_not_set}
                    </span>
                  </div>
                  <div className="font-semibold text-slate-800">
                    <span aria-label={`line-amount-${line.position}`}>
                      {line.amount !== null
                        ? `${formatDecimalMoney(line.amount)} ${line.currency}`
                        : '—'}
                    </span>
                  </div>
                </div>

                {line.quantity_overridden && (
                  <div aria-label={`line-qty-override-${line.position}`} className="text-xs text-amber-700 space-y-0.5 pt-0.5">
                    <p>{t.estimates.quantity_overridden}</p>
                    {line.source_quantity !== null && (
                      <p className="text-slate-400">
                        {t.estimates.source_quantity}: {line.source_quantity} {line.unit}
                      </p>
                    )}
                  </div>
                )}

                {line.price_override && (
                  <p
                    aria-label={`line-price-override-${line.position}`}
                    className="text-xs text-amber-700 pt-0.5"
                  >
                    {t.estimates.price_overridden}
                  </p>
                )}

                {/* Stage 10G.3A — draft-only editing. Never rendered (not just
                    disabled) once the estimate leaves DRAFT. Edytuj itself now
                    lives in the header row above; this footer only appears
                    when it has something to show (mid-edit, an error, or a
                    reset action). */}
                {detail.status === 'DRAFT' && hasDraftFooterContent && (
                  <div className="pt-1.5 space-y-1.5 border-t border-slate-200/70">
                    {editingLineId === line.id ? (
                      <div aria-label={`line-edit-panel-${line.position}`} className="space-y-2">
                        <label className="block text-xs text-slate-500">
                          <span className="block mb-0.5">{t.estimates.line_edit_quantity_label}</span>
                          <div className="flex items-center gap-1.5">
                            <input
                              type="text"
                              inputMode="decimal"
                              aria-label={`line-edit-quantity-${line.position}`}
                              value={editQuantity}
                              onChange={(e) => setEditQuantity(e.target.value)}
                              className="flex-1 min-w-0 border border-slate-300 rounded-lg px-2 min-h-[44px] text-sm bg-white"
                            />
                            <span className="text-slate-400 shrink-0">{line.unit}</span>
                          </div>
                        </label>

                        <div className="text-xs text-slate-500 space-y-1.5">
                          <span className="block">{t.estimates.line_edit_price_label}</span>
                          <label className="flex items-center gap-2 min-h-[44px]">
                            <input
                              type="checkbox"
                              aria-label={`line-edit-price-unresolved-${line.position}`}
                              checked={editPriceMode === 'unresolved'}
                              onChange={(e) => setEditPriceMode(e.target.checked ? 'unresolved' : 'value')}
                              className="w-5 h-5 shrink-0"
                            />
                            <span>{t.estimates.line_edit_price_unresolved}</span>
                          </label>
                          {editPriceMode === 'value' && (
                            <input
                              type="text"
                              inputMode="decimal"
                              aria-label={`line-edit-price-${line.position}`}
                              value={editUnitPrice}
                              onChange={(e) => setEditUnitPrice(e.target.value)}
                              className="w-full border border-slate-300 rounded-lg px-2 min-h-[44px] text-sm bg-white"
                            />
                          )}
                        </div>

                        {actionError !== null && actionError.lineId === line.id && (
                          <p
                            role="alert"
                            aria-label={`line-edit-error-${line.position}`}
                            className="text-xs text-red-600 break-words min-w-0"
                          >
                            {actionError.message}
                          </p>
                        )}

                        <div className="flex items-center gap-2 flex-wrap">
                          <button
                            type="button"
                            aria-label={`line-edit-save-${line.position}`}
                            onClick={() => void submitEdit(line)}
                            disabled={actionBusyLineId === line.id}
                            className="flex-1 min-h-[44px] bg-blue-600 text-white text-sm font-medium rounded-lg px-3 disabled:opacity-60"
                          >
                            {actionBusyLineId === line.id ? t.estimates.line_edit_saving : t.estimates.line_edit_save}
                          </button>
                          <button
                            type="button"
                            aria-label={`line-edit-cancel-${line.position}`}
                            onClick={cancelEdit}
                            disabled={actionBusyLineId === line.id}
                            className="flex-1 min-h-[44px] border border-slate-300 text-slate-600 text-sm font-medium rounded-lg px-3 disabled:opacity-60"
                          >
                            {t.estimates.line_edit_cancel}
                          </button>
                        </div>
                      </div>
                    ) : null}

                    {editingLineId !== line.id && actionError !== null && actionError.lineId === line.id && (
                      <p
                        role="alert"
                        aria-label={`line-edit-error-${line.position}`}
                        className="text-xs text-red-600 break-words min-w-0"
                      >
                        {actionError.message}
                      </p>
                    )}

                    <div className="flex items-center gap-2 flex-wrap">
                      {line.quantity_overridden && (
                        <button
                          type="button"
                          aria-label={`line-reset-quantity-${line.position}`}
                          onClick={() => void submitReset(line, 'quantity')}
                          disabled={actionBusyLineId === line.id}
                          className="min-h-[44px] px-3 text-xs font-medium text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-50 disabled:opacity-60"
                        >
                          {t.estimates.line_reset_quantity}
                        </button>
                      )}
                      {line.price_override && line.origin !== 'MANUAL' && (
                        <button
                          type="button"
                          aria-label={`line-reset-price-${line.position}`}
                          onClick={() => void submitReset(line, 'price')}
                          disabled={actionBusyLineId === line.id}
                          className="min-h-[44px] px-3 text-xs font-medium text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-50 disabled:opacity-60"
                        >
                          {t.estimates.line_reset_price}
                        </button>
                      )}
                    </div>

                    {/* Stage 10G.3C — MANUAL lines only; PLANNED_WORK lines
                        are controlled by project planning + regeneration and
                        are never deletable here. */}
                    {line.origin === 'MANUAL' && editingLineId !== line.id && (
                      deleteConfirmLineId === line.id ? (
                        <div aria-label={`line-delete-confirm-${line.position}`} className="space-y-1.5 pt-1.5 border-t border-slate-200/70">
                          <p className="text-xs text-slate-600 break-words min-w-0">
                            {t.estimates.manual_line_delete_confirm_title}
                          </p>
                          {deleteError !== null && deleteError.lineId === line.id && (
                            <p
                              role="alert"
                              aria-label={`line-delete-error-${line.position}`}
                              className="text-xs text-red-600 break-words min-w-0"
                            >
                              {deleteError.message}
                            </p>
                          )}
                          <div className="flex items-center gap-2 flex-wrap">
                            <button
                              type="button"
                              aria-label={`line-delete-confirm-yes-${line.position}`}
                              onClick={() => void confirmDeleteLine(line)}
                              disabled={deleteBusyLineId === line.id}
                              className="flex-1 min-h-[44px] bg-red-600 text-white text-sm font-medium rounded-lg px-3 disabled:opacity-60"
                            >
                              {deleteBusyLineId === line.id ? t.estimates.manual_line_deleting : t.estimates.manual_line_delete_confirm_yes}
                            </button>
                            <button
                              type="button"
                              aria-label={`line-delete-cancel-${line.position}`}
                              onClick={cancelDeleteLine}
                              disabled={deleteBusyLineId === line.id}
                              className="flex-1 min-h-[44px] border border-slate-300 text-slate-600 text-sm font-medium rounded-lg px-3 disabled:opacity-60"
                            >
                              {t.estimates.line_edit_cancel}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="pt-1.5 border-t border-slate-200/70 space-y-1.5">
                          <button
                            type="button"
                            aria-label={`line-delete-action-${line.position}`}
                            onClick={() => requestDeleteLine(line.id)}
                            className="min-h-[44px] px-3 text-xs font-medium text-red-700 border border-red-200 rounded-lg hover:bg-red-50"
                          >
                            {t.estimates.manual_line_delete_action}
                          </button>
                          {deleteError !== null && deleteError.lineId === line.id && (
                            <p
                              role="alert"
                              aria-label={`line-delete-error-${line.position}`}
                              className="text-xs text-red-600 break-words min-w-0"
                            >
                              {deleteError.message}
                            </p>
                          )}
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </article>
    );
  }

  // Grouped summary view
  return (
    <article aria-label="estimate-shell" className="space-y-3">
      {header}
      {regenerationSection}
      {manualLineSection}

      <div aria-label="estimate-groups" className="space-y-2">
        {groups.map((group, index) => {
          const supportsPriceReset = group.origin !== 'MANUAL';
          const optionsOpen = optionsOpenGroupKey === group.key;
          const isGroupBusy = groupActionBusyKey === group.key;

          return (
            <div
              key={group.key}
              className="bg-white border border-slate-200 rounded-2xl shadow-sm p-3 space-y-1.5"
            >
              {/* Stage 10G.3A polish — Opcje sits top-right, beside the
                  work title/header, per owner-approved placement. The
                  drill-down button carries the rest of the card content;
                  items-start keeps Opcje pinned to the top even when the
                  title wraps to multiple lines. */}
              <div className="flex items-start gap-2">
                <button
                  type="button"
                  aria-label={`estimate-group-${index}`}
                  onClick={() => onGroupKeyChange(group.key)}
                  className="flex-1 min-w-0 space-y-1.5 text-left hover:bg-slate-50 transition min-h-[44px] rounded-lg"
                >
                  <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                    <span
                      aria-label={`group-origin-${index}`}
                      className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-medium shrink-0"
                    >
                      {originLabelFromGroup(group)}
                    </span>
                    <span
                      aria-label={`group-scope-${index}`}
                      className="text-xs px-2 py-0.5 rounded-full bg-slate-50 text-slate-500 border border-slate-200 shrink-0"
                    >
                      {scopeLabel(group.scope)}
                    </span>
                  </div>

                  <p
                    aria-label={`group-description-${index}`}
                    className="text-sm font-medium text-slate-900 break-words min-w-0"
                  >
                    {resolveKey(t, group.rawDescription)}
                  </p>

                  <div className="text-xs text-slate-600 space-y-0.5">
                    {group.quantity !== null && (
                      <div className="flex items-baseline gap-1 flex-wrap min-w-0">
                        <span aria-label={`group-quantity-${index}`} className="shrink-0">
                          {group.quantity} {group.unit}
                        </span>
                        {group.unitPrice !== null && (
                          <>
                            <span className="text-slate-400 shrink-0">×</span>
                            <span aria-label={`group-unit-price-${index}`} className="shrink-0">
                              {formatDecimalMoney(group.unitPrice)} {group.currency}
                            </span>
                          </>
                        )}
                      </div>
                    )}
                    <div className="font-semibold text-slate-800">
                      <span aria-label={`group-amount-${index}`}>
                        {group.amount !== null
                          ? `${formatDecimalMoney(group.amount)} ${group.currency}`
                          : '—'}
                      </span>
                    </div>
                  </div>

                  {group.lineCount > 1 && (
                    <p
                      aria-label={`group-line-count-${index}`}
                      className="text-xs text-slate-400"
                    >
                      {group.lineCount} {t.estimates.group_lines_count}
                    </p>
                  )}

                  {group.hasOverrides && (
                    <p
                      aria-label={`group-has-overrides-${index}`}
                      className="text-xs text-amber-700 pt-0.5"
                    >
                      {t.estimates.group_has_overrides}
                    </p>
                  )}
                </button>

                {detail.status === 'DRAFT' && !optionsOpen && (
                  <button
                    type="button"
                    aria-label={`group-options-${index}`}
                    onClick={() => setOptionsOpenGroupKey(group.key)}
                    className="shrink-0 min-h-[44px] px-3 text-xs font-medium text-slate-500 border border-slate-200 rounded-lg hover:bg-slate-50"
                  >
                    {t.estimates.group_options}
                  </button>
                )}
              </div>

              {/* Stage 10G.3A — group-level price actions panel. DRAFT-only,
                  hidden behind "Opcje" progressive disclosure per the field-
                  usage principle (avoid cluttering the grouped card). */}
              {detail.status === 'DRAFT' && optionsOpen && (
                <div
                  aria-label={`group-options-panel-${index}`}
                  className="space-y-1.5 pt-1.5 border-t border-slate-200/70"
                >
                  <button
                    type="button"
                    aria-label={`group-price-edit-action-${index}`}
                    onClick={() => beginGroupPriceEdit(group)}
                    className="w-full min-h-[44px] px-3 text-xs font-medium text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-50"
                  >
                    {t.estimates.group_price_edit_action}
                  </button>

                  {supportsPriceReset && (
                    <button
                      type="button"
                      aria-label={`group-reset-price-action-${index}`}
                      onClick={() => void submitGroupPriceReset(group)}
                      disabled={isGroupBusy}
                      className="w-full min-h-[44px] px-3 text-xs font-medium text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-50 disabled:opacity-60"
                    >
                      {isGroupBusy ? t.estimates.group_reset_price_saving : t.estimates.group_reset_price_action}
                    </button>
                  )}

                  <button
                    type="button"
                    aria-label={`group-options-close-${index}`}
                    onClick={() => closeGroupOptions(group.key)}
                    className="w-full min-h-[44px] px-3 text-xs font-medium text-slate-500 border border-slate-200 rounded-lg hover:bg-slate-50"
                  >
                    {t.estimates.group_options_close}
                  </button>

                  {/* Visible for both the bulk price-edit panel below and
                      the direct reset-all action above, since a
                      partial-failure error can originate from either. */}
                  {editingGroupPriceKey !== group.key &&
                    groupActionError !== null &&
                    groupActionError.groupKey === group.key && (
                      <p
                        role="alert"
                        aria-label={`group-price-edit-error-${index}`}
                        className="text-xs text-red-600 break-words min-w-0"
                      >
                        {groupActionError.message}
                      </p>
                    )}

                  {editingGroupPriceKey === group.key && (
                    <div
                      aria-label={`group-price-edit-panel-${index}`}
                      className="space-y-2 pt-1.5 border-t border-slate-200/70"
                    >
                      <p className="text-xs text-slate-500">{t.estimates.group_price_edit_title}</p>

                      {groupPriceMixed && groupPriceMode === 'value' && (
                        <p
                          aria-label={`group-price-edit-mixed-${index}`}
                          className="text-xs text-amber-700"
                        >
                          {t.estimates.group_price_edit_mixed}
                        </p>
                      )}

                      <label className="flex items-center gap-2 min-h-[44px]">
                        <input
                          type="checkbox"
                          aria-label={`group-price-edit-unresolved-${index}`}
                          checked={groupPriceMode === 'unresolved'}
                          onChange={(e) => setGroupPriceMode(e.target.checked ? 'unresolved' : 'value')}
                          className="w-5 h-5 shrink-0"
                        />
                        <span className="text-xs text-slate-500">{t.estimates.group_price_edit_unresolved}</span>
                      </label>

                      {groupPriceMode === 'value' && (
                        <input
                          type="text"
                          inputMode="decimal"
                          aria-label={`group-price-edit-value-${index}`}
                          value={groupUnitPrice}
                          onChange={(e) => setGroupUnitPrice(e.target.value)}
                          className="w-full border border-slate-300 rounded-lg px-2 min-h-[44px] text-sm bg-white"
                        />
                      )}

                      {groupActionError !== null && groupActionError.groupKey === group.key && (
                        <p
                          role="alert"
                          aria-label={`group-price-edit-error-${index}`}
                          className="text-xs text-red-600 break-words min-w-0"
                        >
                          {groupActionError.message}
                        </p>
                      )}

                      <div className="flex items-center gap-2 flex-wrap">
                        <button
                          type="button"
                          aria-label={`group-price-edit-save-${index}`}
                          onClick={() => void submitGroupPriceEdit(group)}
                          disabled={isGroupBusy}
                          className="flex-1 min-h-[44px] bg-blue-600 text-white text-sm font-medium rounded-lg px-3 disabled:opacity-60"
                        >
                          {isGroupBusy ? t.estimates.group_price_edit_saving : t.estimates.group_price_edit_save}
                        </button>
                        <button
                          type="button"
                          aria-label={`group-price-edit-cancel-${index}`}
                          onClick={cancelGroupPriceEdit}
                          disabled={isGroupBusy}
                          className="flex-1 min-h-[44px] border border-slate-300 text-slate-600 text-sm font-medium rounded-lg px-3 disabled:opacity-60"
                        >
                          {t.estimates.group_price_edit_cancel}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </article>
  );
}
