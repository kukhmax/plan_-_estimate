import { useI18n } from '../hooks/useI18n';
import type { EstimateSummaryRead, EstimateStatusValue } from '../types/estimate';
import { formatDecimalMoney } from '../utils/format';

interface EstimateShellProps {
  estimate: EstimateSummaryRead;
  onBack: () => void;
}

export function EstimateShell({ estimate }: EstimateShellProps) {
  const { t } = useI18n();

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

  return (
    <article aria-label="estimate-shell" className="space-y-3">
      <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <h2 className="font-bold text-slate-900 text-base">
            {t.estimates.title} — {t.estimates.version} {estimate.version}
          </h2>
          <span
            aria-label="estimate-shell-status"
            className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${statusBadgeClass(estimate.status)}`}
          >
            {statusLabel(estimate.status)}
          </span>
        </div>

        {estimate.name && (
          <p className="text-sm text-slate-600">{estimate.name}</p>
        )}

        <div className="text-xs text-slate-500 space-y-0.5">
          <div>
            <span className="text-slate-400">{t.estimates.status}: </span>
            <span className="font-medium text-slate-700">{statusLabel(estimate.status)}</span>
          </div>
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

    </article>
  );
}
