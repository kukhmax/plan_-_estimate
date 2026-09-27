import { useI18n } from '../hooks/useI18n';
import { ExecutionDetachAffected } from '../types/workPlan';
import { priceItemLabel } from '../utils/executionFormat';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

interface ExecutionDetachDialogProps {
  /** The server's authoritative list from the 409 (never rebuilt locally). */
  affected: ExecutionDetachAffected[];
  /** True when this list came from a retry that was itself refused again. */
  repeated: boolean;
  /** Shown per entry when the mutation spans several surfaces (apply-to-all). */
  surfaceNames?: Record<string, string>;
  showSurface?: boolean;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  idSuffix: string;
}

/**
 * Stage 13H.4/13H.5 execution-detach confirmation. A blocking modal sheet, so
 * the underlying draft cannot change while the owner decides: confirming
 * retries the ORIGINAL request with exactly the returned keys. The text never
 * says execution is deleted -- it is detached from the current plan and its
 * history is kept.
 */
export function ExecutionDetachDialog({
  affected,
  repeated,
  surfaceNames,
  showSurface = false,
  busy,
  onConfirm,
  onCancel,
  idSuffix,
}: ExecutionDetachDialogProps) {
  const { t } = useI18n();
  const titleId = `execution-detach-title-${idSuffix}`;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div
        aria-label={`execution-detach-dialog-${idSuffix}`}
        className="w-full max-w-lg bg-[var(--tg-theme-bg-color,#ffffff)] rounded-t-2xl sm:rounded-2xl shadow-xl flex flex-col max-h-[90vh] overflow-hidden"
      >
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          <h2 id={titleId} className="text-lg font-semibold text-[var(--tg-theme-text-color)] break-words">
            {t.execution.detach_title}
          </h2>
          {repeated && (
            <p role="status" aria-label={`execution-detach-repeat-${idSuffix}`} className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">
              {t.execution.detach_repeat}
            </p>
          )}
          {affected.length > 0 ? (
            <>
              <p className="text-sm text-[var(--tg-theme-text-color)] break-words">{t.execution.detach_body}</p>
              <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{t.execution.detach_history}</p>
              <p className="text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">{t.execution.detach_affected}</p>
              <ul aria-label={`execution-detach-list-${idSuffix}`} className="space-y-2">
                {affected.map((entry) => (
                  <li
                    key={entry.occurrence_key}
                    aria-label={`execution-detach-item-${entry.occurrence_key}`}
                    className="min-w-0 rounded-lg border border-[var(--tg-control-border-color)] p-2 space-y-1"
                  >
                    {showSurface && (
                      <p className="text-xs font-semibold text-[var(--tg-theme-hint-color)] break-words">
                        {surfaceNames?.[entry.surface_id] ?? t.execution.detach_other_surface}
                      </p>
                    )}
                    <p className="text-sm font-medium text-[var(--tg-theme-text-color)] break-words">
                      <span aria-hidden="true" className="text-[var(--tg-theme-hint-color)]">{entry.position + 1}. </span>
                      {priceItemLabel(
                        t,
                        { display_name: entry.price_item_display_name, name_key: entry.price_item_name_key, code: entry.price_item_code },
                        t.work_plan.unavailable_item,
                      )}
                    </p>
                    <ExecutionStatusBadge status={entry.status} />
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-[var(--tg-theme-text-color)] break-words">{t.execution.detach_none}</p>
          )}
        </div>
        <div className="p-4 border-t border-[var(--tg-control-border-color)] space-y-2">
          <button
            type="button"
            aria-label={`execution-detach-confirm-${idSuffix}`}
            onClick={onConfirm}
            disabled={busy}
            className="w-full min-h-11 px-3 rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] font-semibold text-sm disabled:opacity-60 break-words"
          >
            {busy ? t.execution.detach_working : t.execution.detach_confirm}
          </button>
          <button
            type="button"
            aria-label={`execution-detach-cancel-${idSuffix}`}
            onClick={onCancel}
            disabled={busy}
            className="w-full min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)] font-semibold text-sm disabled:opacity-60"
          >
            {t.execution.detach_cancel}
          </button>
        </div>
      </div>
    </div>
  );
}
