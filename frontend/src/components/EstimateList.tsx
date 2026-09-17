import { useCallback, useEffect, useState } from 'react';
import { generateEstimate, listEstimates } from '../api/estimates';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import type { EstimateSummaryRead, EstimateStatusValue } from '../types/estimate';
import { formatDecimalMoney } from '../utils/format';

interface EstimateListProps {
  projectId: string;
  onOpenEstimate: (estimate: EstimateSummaryRead) => void;
}

export function EstimateList({ projectId, onOpenEstimate }: EstimateListProps) {
  const { t } = useI18n();
  const [estimates, setEstimates] = useState<EstimateSummaryRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listEstimates(projectId);
      setEstimates(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.estimates.error_load);
    } finally {
      setLoading(false);
    }
  }, [projectId, t.estimates.error_load]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleGenerate = async () => {
    if (generating) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      await generateEstimate(projectId);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setGenerateError(t.estimates.conflict_message);
        await load();
      } else {
        setGenerateError(err instanceof Error ? err.message : t.estimates.error_generate);
      }
    } finally {
      setGenerating(false);
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

  const formatTotal = (total: string | null, currency: string): string => {
    const formatted = formatDecimalMoney(total);
    return total === null ? formatted : `${formatted} ${currency}`;
  };

  const formatDate = (iso: string): string => {
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      });
    } catch {
      return iso;
    }
  };

  const activeDraft = estimates.find((e) => e.status === 'DRAFT');
  const hasDraft = activeDraft !== undefined;

  if (loading) {
    return (
      <p aria-label="estimates-loading" className="text-sm text-slate-500 text-center py-6">
        {t.estimates.loading}
      </p>
    );
  }

  if (error) {
    return (
      <div className="space-y-2 py-4 text-center">
        <p role="alert" aria-label="estimates-error" className="text-sm text-red-600">
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
    );
  }

  if (estimates.length === 0) {
    return (
      <div
        aria-label="estimates-empty-state"
        className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3"
      >
        <h3 className="font-semibold text-slate-900 text-sm">{t.estimates.empty_title}</h3>
        <p className="text-xs text-slate-500">{t.estimates.empty_description}</p>
        {generateError && (
          <p role="alert" className="text-xs text-red-600">{generateError}</p>
        )}
        <button
          type="button"
          aria-label="generate-estimate"
          disabled={generating}
          onClick={() => void handleGenerate()}
          className="w-full min-h-11 bg-blue-600 text-white font-semibold rounded-xl py-2.5 text-sm hover:bg-blue-700 transition disabled:opacity-50"
        >
          {generating ? t.estimates.creating : t.estimates.create}
        </button>
      </div>
    );
  }

  return (
    <div aria-label="estimates-list" className="space-y-3">
      {estimates.map((estimate) => {
        const isDraft = estimate.status === 'DRAFT';
        return (
          <article
            key={estimate.id}
            aria-label={`estimate-version-${estimate.version}`}
            className={`bg-white border rounded-2xl p-4 shadow-sm space-y-2.5 ${
              isDraft ? 'border-blue-300' : 'border-slate-200'
            }`}
          >
            <div className="flex items-start justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2 flex-wrap min-w-0">
                <span className="font-bold text-slate-900 text-sm">
                  {t.estimates.version} {estimate.version}
                </span>
                <span
                  aria-label={`estimate-status-${estimate.version}`}
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusBadgeClass(estimate.status)}`}
                >
                  {statusLabel(estimate.status)}
                </span>
                {isDraft && (
                  <span
                    aria-label="draft-badge"
                    className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 font-medium border border-blue-200"
                  >
                    {t.estimates.draft_badge}
                  </span>
                )}
              </div>
              <span className="text-xs text-slate-400 shrink-0">
                {t.estimates.updated_at}: {formatDate(estimate.updated_at)}
              </span>
            </div>

            {estimate.name && (
              <p className="text-xs text-slate-600 font-medium">{estimate.name}</p>
            )}

            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="text-sm font-semibold text-slate-800">
                {t.estimates.total}: {formatTotal(estimate.total, estimate.currency)}
              </span>
              <button
                type="button"
                aria-label={isDraft ? 'open-draft-estimate' : `open-estimate-${estimate.version}`}
                onClick={() => onOpenEstimate(estimate)}
                className={`min-h-10 px-3 py-2 text-xs font-semibold rounded-xl transition ${
                  isDraft
                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                    : 'bg-slate-50 text-slate-700 hover:bg-slate-100 border border-slate-200'
                }`}
              >
                {isDraft ? t.estimates.open_draft : t.estimates.open_version}
              </button>
            </div>
          </article>
        );
      })}

      {generateError && (
        <p role="alert" aria-label="generate-error" className="text-xs text-red-600 text-center">
          {generateError}
        </p>
      )}

      {!hasDraft && (
        <button
          type="button"
          aria-label="create-new-version"
          disabled={generating}
          onClick={() => void handleGenerate()}
          className="w-full min-h-11 bg-blue-600 text-white font-semibold rounded-xl py-2.5 text-sm hover:bg-blue-700 transition disabled:opacity-50"
        >
          {generating ? t.estimates.creating : t.estimates.create_new_version}
        </button>
      )}
    </div>
  );
}
