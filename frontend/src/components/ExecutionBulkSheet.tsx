import { useI18n } from '../hooks/useI18n';
import { BulkExecutionResultRead } from '../types/workPlan';

interface ExecutionBulkSheetProps {
  /** The PREVIEW response (authoritative; never rebuilt locally). */
  preview: BulkExecutionResultRead;
  surfaceNames?: Record<string, string>;
  applying: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
  idSuffix: string;
}

/** Why a preview has nothing to change, from the counts the API returns. */
export function nothingReason(preview: BulkExecutionResultRead): 'no_walls' | 'not_started' | 'already' | 'no_match' {
  if (preview.walls.length === 0) return 'no_walls';
  if (preview.expected_source.every((item) => item.status === 'NOT_STARTED')) return 'not_started';
  if (preview.unchanged > 0) return 'already';
  return 'no_match';
}

/** Counts of walls that HAVE a plan (a wall without a plan is shown as
 * "Brak planu prac", never as N unmatched works). */
export function displayCounts(result: BulkExecutionResultRead) {
  const withPlan = result.walls.filter((w) => w.has_plan);
  return {
    unmatched: withPlan.reduce((n, w) => n + w.unmatched, 0),
    ambiguous: result.ambiguous,
    noPlanWalls: result.walls.length - withPlan.length,
  };
}

/**
 * Stage 13H.5B.2 — confirmation summary for carrying this wall's execution
 * progress forward to the room's other walls. Shows only what the preview
 * returned; with nothing to change it is informational (no confirm button).
 */
export function ExecutionBulkSheet({
  preview,
  surfaceNames,
  applying,
  error,
  onConfirm,
  onClose,
  idSuffix,
}: ExecutionBulkSheetProps) {
  const { t } = useI18n();
  const b = t.execution.bulk;
  const counts = displayCounts(preview);
  const actionable = preview.changed > 0;
  const titleId = `execution-bulk-title-${idSuffix}`;
  const fill = (template: string, count: number) => template.replace('{count}', String(count));
  const line = 'text-sm text-[var(--tg-theme-text-color)] break-words';
  const hint = 'text-sm text-[var(--tg-theme-hint-color)] break-words';
  return (
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div
        aria-label={`execution-bulk-sheet-${idSuffix}`}
        className="w-full max-w-lg bg-[var(--tg-theme-bg-color,#ffffff)] rounded-t-2xl sm:rounded-2xl shadow-xl flex flex-col max-h-[90vh] overflow-hidden"
      >
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          <h2 id={titleId} className="text-lg font-semibold text-[var(--tg-theme-text-color)] break-words">
            {actionable ? b.title : b.nothing_title}
          </h2>
          {!actionable && (
            <p aria-label={`execution-bulk-nothing-${idSuffix}`} className={line}>
              {b[`nothing_${nothingReason(preview)}`]}
            </p>
          )}
          <ul aria-label={`execution-bulk-counts-${idSuffix}`} className="space-y-1">
            <li className={line}>{fill(b.walls, preview.walls.length)}</li>
            {preview.walls.length > 0 && (
              <>
                <li className={`${line} font-semibold`}>{fill(b.will_change, preview.changed)}</li>
                <li className={line}>{fill(b.unchanged, preview.unchanged)}</li>
                {counts.unmatched > 0 && <li className={line}>{fill(b.unmatched, counts.unmatched)}</li>}
                {counts.ambiguous > 0 && <li className={line}>{fill(b.ambiguous, counts.ambiguous)}</li>}
                {counts.noPlanWalls > 0 && <li className={line}>{fill(b.no_plan_walls, counts.noPlanWalls)}</li>}
              </>
            )}
          </ul>
          {/* Visible before the per-wall list scrolls away: the owner confirms these rules. */}
          {actionable && (
            <div aria-label={`execution-bulk-explain-${idSuffix}`} className="space-y-1">
              <p className={hint}>{b.explain_scope}</p>
              <p className={hint}>{b.explain_forward}</p>
              <p className={hint}>{b.explain_time}</p>
            </div>
          )}
          {counts.ambiguous > 0 && (
            <p aria-label={`execution-bulk-ambiguous-hint-${idSuffix}`} className={hint}>{b.ambiguous_hint}</p>
          )}
          {preview.walls.length > 0 && (
            <ul aria-label={`execution-bulk-walls-${idSuffix}`} className="space-y-2">
              {preview.walls.map((wall) => {
                const parts = wall.has_plan
                  ? [
                    wall.changed > 0 ? fill(b.wall_changed, wall.changed) : null,
                    wall.unchanged > 0 ? fill(b.wall_unchanged, wall.unchanged) : null,
                    wall.unmatched > 0 ? fill(b.wall_unmatched, wall.unmatched) : null,
                    wall.ambiguous > 0 ? fill(b.wall_ambiguous, wall.ambiguous) : null,
                  ].filter((p): p is string => p !== null)
                  : [b.wall_no_plan];
                return (
                  <li
                    key={wall.surface_id}
                    aria-label={`execution-bulk-wall-${wall.surface_id}`}
                    className="min-w-0 rounded-lg border border-[var(--tg-control-border-color)] p-2 space-y-0.5"
                  >
                    <p className="text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">
                      {surfaceNames?.[wall.surface_id] ?? b.other_wall}
                    </p>
                    {parts.map((part) => (
                      <p key={part} className="text-xs text-[var(--tg-theme-hint-color)] break-words">{part}</p>
                    ))}
                  </li>
                );
              })}
            </ul>
          )}
          {error && (
            <p role="alert" aria-label={`execution-bulk-error-${idSuffix}`} className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">
              {error}
            </p>
          )}
        </div>
        <div className="p-4 border-t border-[var(--tg-control-border-color)] space-y-2">
          {actionable && (
            <button
              type="button"
              aria-label={`execution-bulk-confirm-${idSuffix}`}
              onClick={onConfirm}
              disabled={applying}
              className="w-full min-h-11 px-3 rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] font-semibold text-sm disabled:opacity-60 break-words"
            >
              {applying ? b.applying : b.confirm}
            </button>
          )}
          <button
            type="button"
            aria-label={`execution-bulk-close-${idSuffix}`}
            onClick={onClose}
            disabled={applying}
            className="w-full min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)] font-semibold text-sm disabled:opacity-60"
          >
            {actionable ? b.cancel : b.close}
          </button>
        </div>
      </div>
    </div>
  );
}
