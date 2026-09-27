import { useI18n } from '../hooks/useI18n';
import { WorkExecutionStatus } from '../types/workPlan';

/**
 * Stage 13H.5: compact read-only execution status. The status is always
 * spelled out and carries a symbol, so it never relies on color alone; every
 * variant pairs Telegram theme tokens (readable in light and dark themes).
 */
const STYLES: Record<WorkExecutionStatus, { symbol: string; className: string }> = {
  NOT_STARTED: {
    symbol: '○',
    className: 'border border-[var(--tg-control-border-color)] text-[var(--tg-theme-hint-color)]',
  },
  IN_PROGRESS: {
    symbol: '◐',
    className: 'border border-[var(--tg-theme-accent-text-color)] text-[var(--tg-theme-accent-text-color)]',
  },
  COMPLETED: {
    symbol: '✓',
    className: 'border border-[var(--tg-theme-button-color)] bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]',
  },
};

export function ExecutionStatusBadge({
  status,
  ariaLabel,
}: {
  status: WorkExecutionStatus;
  ariaLabel?: string;
}) {
  const { t } = useI18n();
  const style = STYLES[status];
  const label = t.execution.status[status];
  return (
    <span
      aria-label={ariaLabel}
      title={t.execution.status_label.replace('{status}', label)}
      data-status={status}
      className={`inline-flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold break-words ${style.className}`}
    >
      <span aria-hidden="true">{style.symbol}</span>
      <span>{label}</span>
    </span>
  );
}
