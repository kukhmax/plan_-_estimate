import { useCallback, useEffect, useState } from 'react';
import { getEstimate, patchEstimateLine } from '../api/estimates';
import { useI18n } from '../hooks/useI18n';
import type { EstimateLineRead, EstimateLineUpdatePayload, EstimateRead, EstimateSummaryRead, EstimateStatusValue, LineOriginValue } from '../types/estimate';
import { sumDecimalStrings } from '../utils/decimalArithmetic';
import { formatDecimalMoney } from '../utils/format';
import { resolveKey } from '../utils/i18nKeys';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';

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

  const header = (
    <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-2">
      <div className="flex items-center gap-2 flex-wrap min-w-0">
        <h2 className="font-bold text-slate-900 text-base shrink-0">
          {t.estimates.title} — {t.estimates.version} {estimate.version}
        </h2>
        <span
          aria-label="estimate-shell-status"
          className={`text-xs px-2.5 py-0.5 rounded-full font-medium shrink-0 ${statusBadgeClass(estimate.status)}`}
        >
          {statusLabel(estimate.status)}
        </span>
      </div>

      {estimate.name && (
        <p className="text-sm text-slate-600 break-words min-w-0">{estimate.name}</p>
      )}

      <div className="text-xs text-slate-500 space-y-0.5">
        <div>
          <span className="text-slate-400">{t.estimates.total}: </span>
          <span className="font-medium text-slate-700">
            {estimate.total !== null
              ? `${formatDecimalMoney(estimate.total)} ${estimate.currency}`
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

  // Preferred order: 1) explicit surface_name if non-empty, 2) canonical
  // localized surface type if known, 3) omit — never invent a name or guess
  // from array order. Presentation metadata may be null OR absent
  // (undefined) at runtime, so every check below must treat them the same.
  const provenanceSurfaceLabel = (line: EstimateLineRead): string | null => {
    const surfaceName = line.surface_name;
    if (surfaceName !== null && surfaceName !== undefined && surfaceName.trim().length > 0) {
      return getSurfaceDisplayName(
        { name: surfaceName, surface_type: line.surface_type_value },
        surfaceDisplayLabels,
      );
    }
    if (line.surface_type_value === 'WALL') return surfaceDisplayLabels.wall;
    if (line.surface_type_value === 'FLOOR') return surfaceDisplayLabels.floor;
    if (line.surface_type_value === 'CEILING') return surfaceDisplayLabels.ceiling;
    return null;
  };

  const provenanceOpeningLabel = (line: EstimateLineRead): string | null => {
    if (line.opening_id === null) return null;
    if (line.opening_name !== null && line.opening_name !== undefined) return line.opening_name;
    if (line.opening_type_value === 'DOOR') return t.openings.door;
    if (line.opening_type_value === 'WINDOW') return t.openings.window;
    return t.openings.other;
  };

  // Compact "room — surface — opening" provenance, replacing the previous
  // labeled Pomieszczenie/Powierzchnia/Otwór rows. Missing pieces are simply
  // omitted — never invent a placeholder for a part that isn't available.
  const compactProvenanceLabel = (line: EstimateLineRead): string | null => {
    const parts: string[] = [];
    if (line.room_name !== null && line.room_name !== undefined) parts.push(line.room_name);
    const surfaceLabel = provenanceSurfaceLabel(line);
    if (surfaceLabel !== null) parts.push(surfaceLabel);
    const openingLabel = provenanceOpeningLabel(line);
    if (openingLabel !== null) parts.push(openingLabel);
    return parts.length > 0 ? parts.join(' — ') : null;
  };

  // Detail view: show individual lines for the selected group
  if (selectedGroupKey !== null) {
    const selectedGroup = groups.find((g) => g.key === selectedGroupKey);
    const linesToShow = selectedGroup ? selectedGroup.lines : [];

    return (
      <article aria-label="estimate-shell" className="space-y-3">
        {header}

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
              (line.price_override && line.origin !== 'MANUAL');
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
