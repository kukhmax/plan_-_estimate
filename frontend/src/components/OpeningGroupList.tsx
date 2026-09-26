import { useI18n } from '../hooks/useI18n';
import { OpeningTypeValue } from '../types/opening';
import { OpeningGroup } from '../types/room';
import { formatExactDimension } from '../utils/openingSummary';

const TYPES: OpeningTypeValue[] = ['DOOR', 'WINDOW', 'OTHER'];

interface OpeningGroupListProps {
  groups: OpeningGroup[];
  /** aria-label of the block (room vs object summary). */
  label: string;
}

/**
 * Read-only opening dimension summary (Stage 13F-PRE). Rows arrive already
 * grouped and ordered by the backend (type + exact Decimal width/height,
 * quantities summed); this component only presents them, stacked per type.
 */
export function OpeningGroupList({ groups, label }: OpeningGroupListProps) {
  const { t } = useI18n();
  if (groups.length === 0) return null;
  const heading: Record<OpeningTypeValue, string> = {
    DOOR: t.object_summary.doors,
    WINDOW: t.object_summary.windows,
    OTHER: t.object_summary.others,
  };
  return (
    <div aria-label={label} className="space-y-1.5">
      <span className="block font-semibold text-slate-700">{t.object_summary.openings}</span>
      {TYPES.filter((type) => groups.some((g) => g.opening_type === type)).map((type) => (
        <div key={type} aria-label={`${label}-${type}`} className="space-y-0.5">
          <span className="block text-slate-500 font-medium">{heading[type]}</span>
          <ul className="space-y-0.5">
            {groups
              .filter((g) => g.opening_type === type)
              .map((g) => (
                <li
                  key={`${g.width}-${g.height}`}
                  className="flex items-baseline justify-between gap-3 text-slate-700"
                >
                  <span className="min-w-0 break-words">
                    {formatExactDimension(g.width)} × {formatExactDimension(g.height)} {t.common.unit_m}
                  </span>
                  <strong className="shrink-0 text-slate-900 tabular-nums">× {g.quantity}</strong>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
