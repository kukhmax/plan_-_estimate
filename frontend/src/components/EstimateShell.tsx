import { useCallback, useEffect, useState } from 'react';
import { getEstimate } from '../api/estimates';
import { useI18n } from '../hooks/useI18n';
import type { EstimateLineRead, EstimateRead, EstimateSummaryRead, EstimateStatusValue, LineOriginValue } from '../types/estimate';
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
            return (
              <div
                key={line.id}
                aria-label={`estimate-line-${line.position}`}
                className={`${tint.bg} border ${tint.border} rounded-2xl p-3 shadow-sm space-y-1.5`}
              >
                <div className="flex items-center gap-1.5 flex-wrap min-w-0">
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
        {groups.map((group, index) => (
          <button
            key={group.key}
            type="button"
            aria-label={`estimate-group-${index}`}
            onClick={() => onGroupKeyChange(group.key)}
            className="w-full bg-white border border-slate-200 rounded-2xl p-3 shadow-sm space-y-1.5 text-left hover:bg-slate-50 transition min-h-[44px]"
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
        ))}
      </div>
    </article>
  );
}
