import { useEffect, useState } from 'react';
import { fetchMargin } from '../api/paymentSchedule';
import { useI18n } from '../hooks/useI18n';
import { useConnection } from '../offline/connection';
import type { Margin } from '../types/paymentSchedule';
import { formatMoney, formatPlain } from '../utils/paymentFormat';

interface MarginCardProps {
  projectId: string;
  /** Changes whenever the money, the schedule or the hours change: the margin is read again. */
  version: number;
}

/** V2-9 — the margin of an object: the agreed amount (else the estimate) less the expenses less the owner's own work. Every number is the server's. */
export function MarginCard({ projectId, version }: MarginCardProps) {
  const { t } = useI18n();
  const text = t.payments.margin;
  const { offline } = useConnection();
  const [margin, setMargin] = useState<Margin | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (offline) return;
    let alive = true;
    setFailed(false);
    fetchMargin(projectId)
      .then((found) => {
        if (alive) setMargin(found);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [projectId, version, offline]);

  // the margin is an extra of the screen: while it cannot be read nothing is shown in its place
  if (!margin || failed || typeof margin.expenses !== 'string') return null;

  const negative = typeof margin.margin === 'string' && margin.margin.startsWith('-');
  const rows: { key: string; label: string; value: string; strong?: boolean; negative?: boolean }[] = [];
  if (margin.basis !== null) {
    rows.push({ key: 'basis', label: margin.basis_source === 'ESTIMATE' ? text.basis_estimate : text.basis_agreed, value: formatMoney(margin.basis) });
  }
  rows.push({ key: 'expenses', label: text.expenses, value: formatMoney(margin.expenses) });
  rows.push({ key: 'hours', label: text.hours, value: `${formatPlain(margin.hours)} h` });
  if (margin.basis !== null) {
    rows.push({ key: 'labor', label: text.labor, value: margin.labor_cost === null ? text.labor_none : formatMoney(margin.labor_cost) });
    rows.push({ key: 'margin', label: margin.labor_included ? text.margin : text.margin_before, value: formatMoney(margin.margin), strong: true, negative });
    if (margin.percent !== null) rows.push({ key: 'percent', label: text.percent, value: `${formatPlain(margin.percent)}%` });
    if (margin.per_hour !== null) rows.push({ key: 'per_hour', label: text.per_hour, value: `${formatMoney(margin.per_hour)} / h` });
  }

  return (
    <article aria-label="margin-card" className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
      <h3 className="text-sm font-semibold text-slate-900 break-words">{text.title}</h3>
      {margin.basis === null && <p aria-label="margin-no-basis" className="text-xs text-slate-600 break-words">{text.no_basis}</p>}
      <dl className="space-y-1.5 text-sm">
        {rows.map((row) => (
          <div key={row.key} aria-label={`margin-${row.key}`} className="flex flex-wrap items-baseline justify-between gap-x-3">
            <dt className="text-slate-500 min-w-0 break-words">{row.label}</dt>
            <dd className={`break-words ${row.strong ? 'font-bold' : 'font-semibold'} ${row.negative ? 'text-red-600' : 'text-slate-900'}`}>{row.value}</dd>
          </div>
        ))}
      </dl>
      {margin.basis !== null && margin.hourly_rate === null && <p aria-label="margin-rate-hint" className="text-xs text-slate-600 break-words">{text.rate_hint}</p>}
      <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{text.note}</p>
    </article>
  );
}
