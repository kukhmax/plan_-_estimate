import { useEffect, useState } from 'react';
import { fetchProjectSummary } from '../api/rooms';
import { useI18n } from '../hooks/useI18n';
import { ProjectSummary } from '../types/room';
import { formatMetric } from '../utils/format';
import { OpeningGroupList } from './OpeningGroupList';

interface ProjectSummaryCardProps {
  projectId: string;
  /** Bumped by the parent after a room change so the summary reloads. */
  refreshToken?: number;
}

/**
 * "Podsumowanie obiektu" (Stage 13F-PRE): object-level aggregate shown after
 * the room list. Every number comes from the backend summary read model
 * (Decimal sums of canonical room calculations over ACTIVE rooms; openings
 * grouped server-side) -- nothing is computed here, values are only formatted.
 */
export function ProjectSummaryCard({ projectId, refreshToken = 0 }: ProjectSummaryCardProps) {
  const { t } = useI18n();
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    fetchProjectSummary(projectId)
      .then((data) => {
        if (cancelled) return;
        setSummary(data);
        setState('ready');
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, refreshToken]);

  // Nothing to aggregate yet: the room list already shows its own empty state.
  if (state === 'ready' && summary && summary.room_count === 0) return null;

  const m2 = (value: string | null) => (value === null ? '—' : `${formatMetric(value)} ${t.common.unit_m2}`);
  const rows: { key: string; label: string; value: string; strong?: boolean }[] = summary
    ? [
        { key: 'floor', label: t.object_summary.floors, value: m2(summary.floor_area) },
        { key: 'ceiling', label: t.object_summary.ceilings, value: m2(summary.ceiling_area) },
        { key: 'gross', label: t.object_summary.walls_gross, value: m2(summary.total_wall_area) },
        { key: 'deductions', label: t.object_summary.deductions, value: m2(summary.total_deduction_area) },
        { key: 'net', label: t.object_summary.walls_net, value: m2(summary.net_wall_area), strong: true },
        {
          key: 'reveals',
          label: t.object_summary.reveals,
          value:
            summary.reveal_total_length === null
              ? '—'
              : `${formatMetric(summary.reveal_total_length)} ${t.object_summary.unit_lm} / ${m2(summary.reveal_total_area)}`,
        },
      ]
    : [];

  return (
    <section
      aria-label="object-summary"
      className="mt-4 bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3 text-xs"
    >
      <h3 className="text-base font-bold text-slate-900 break-words">{t.object_summary.title}</h3>
      {state === 'loading' && <p role="status" className="text-slate-500">{t.object_summary.loading}</p>}
      {state === 'error' && (
        <p role="alert" className="text-red-600">{t.object_summary.error}</p>
      )}
      {state === 'ready' && summary && (
        <>
          <div aria-label="object-summary-areas" className="space-y-1">
            <span className="block font-semibold text-slate-700">{t.object_summary.areas}</span>
            <dl className="space-y-1">
              {rows.map((row) => (
                <div
                  key={row.key}
                  aria-label={`object-summary-${row.key}`}
                  className={`flex items-baseline justify-between gap-3 ${
                    row.strong ? 'pt-1 border-t border-slate-100 text-emerald-700' : 'text-slate-600'
                  }`}
                >
                  <dt className="min-w-0 break-words">{row.label}</dt>
                  <dd className={`shrink-0 text-right tabular-nums ${row.strong ? 'font-bold' : 'font-semibold text-slate-800'}`}>
                    {row.value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
          {summary.opening_groups.length > 0 && (
            <div className="pt-2 border-t border-slate-100">
              <OpeningGroupList groups={summary.opening_groups} label="object-summary-openings" />
            </div>
          )}
        </>
      )}
    </section>
  );
}
