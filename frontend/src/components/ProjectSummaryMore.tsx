import { useState } from 'react';
import { fetchSchedule as fetchWorkSchedule } from '../api/calendar';
import { listEstimates } from '../api/estimates';
import { fetchSchedule as fetchPaymentSchedule } from '../api/paymentSchedule';
import { fetchPayments } from '../api/payments';
import { useI18n } from '../hooks/useI18n';
import type { EstimateSummaryRead } from '../types/estimate';
import type { PaymentSummary } from '../types/payment';
import type { Schedule as PaymentSchedule } from '../types/paymentSchedule';
import { formatDay, formatMoney } from '../utils/paymentFormat';
import { Ico } from './Ico';

interface MoreState {
  estimate: EstimateSummaryRead | null;
  payments: PaymentSchedule | null;
  /** The settlement of the object ("Faktury i zaliczki"): what came in and the agreed amount less it -- the stages may not be set at all. */
  money: PaymentSummary | null;
  first: string | null;
  last: string | null;
}

/**
 * Owner 2026-10-31: the summary of an object shows its areas; "Dodatkowo" opens the rest -- the money (the estimate, the agreed amount, what
 * came in and what is still due), the dates (the planned works, the next payment stage) and where the open high risks are. Every amount and
 * every date is the server's; the screen only picks the latest estimate, the first and last planned day and the next stage due.
 */
export function ProjectSummaryMore({ projectId, risks }: { projectId: string; risks: { room_id: string; room_name: string; count: number }[] }) {
  const { t } = useI18n();
  const text = t.object_summary;
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<MoreState | null>(null);
  const [failed, setFailed] = useState(false);

  const load = async () => {
    setFailed(false);
    // each part is read on its own: a part that cannot be read is shown as "—", the others stay
    const [estimates, payments, works, money] = await Promise.all([
      listEstimates(projectId).catch(() => null),
      fetchPaymentSchedule(projectId).catch(() => null),
      fetchWorkSchedule(projectId).catch(() => null),
      fetchPayments(projectId).then((list) => list.summary).catch(() => null),
    ]);
    if (estimates === null && payments === null && works === null && money === null) {
      setFailed(true);
      return;
    }
    const days = (works?.planned ?? []).map((row) => row.planned_date).sort();
    setData({
      estimate: (estimates?.items ?? []).filter((e) => e.status !== 'ARCHIVED').sort((a, b) => b.version - a.version)[0] ?? null,
      payments,
      money,
      first: days[0] ?? null,
      last: days[days.length - 1] ?? null,
    });
  };

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && data === null) void load();
  };

  const statusWord = (status: string) =>
    ({ DRAFT: t.estimates.status_draft, FINAL: t.estimates.status_final, ACCEPTED: t.estimates.status_accepted, ARCHIVED: t.estimates.status_archived })[status] ?? status;
  const nextStage = data?.payments?.items.find((stage) => stage.state !== 'PAID' && stage.due_on !== null) ?? null;
  const row = (key: string, label: string, value: string) => (
    <div key={key} aria-label={`object-summary-${key}`} className="flex items-baseline justify-between gap-3 text-slate-600">
      <dt className="min-w-0 break-words">{label}</dt>
      <dd className="shrink-0 max-w-[60%] text-right font-semibold text-slate-800 break-words">{value}</dd>
    </div>
  );

  return (
    <div className="pt-2 border-t border-slate-100 space-y-2">
      <button
        type="button"
        aria-label="object-summary-more"
        aria-expanded={open}
        onClick={toggle}
        className="w-full min-h-11 rounded-xl bg-slate-100 px-3 text-sm font-semibold text-slate-800 hover:bg-slate-200"
      >
        <Ico>{open ? '🔼' : '➕'}</Ico>{open ? text.less : text.more}
      </button>
      {open && failed && <p role="alert" className="text-red-600 break-words">{text.more_error}</p>}
      {open && !failed && data === null && <p role="status" className="text-slate-500">{text.loading}</p>}
      {open && data && (
        <div aria-label="object-summary-more-panel" className="space-y-3">
          <div className="space-y-1">
            <span className="block font-semibold text-slate-700">{text.money}</span>
            <dl className="space-y-1">
              {row(
                'estimate',
                t.estimates.title,
                data.estimate
                  ? `${text.version.replace('{n}', String(data.estimate.version))} · ${formatMoney(data.estimate.gross_total ?? data.estimate.total)} · ${statusWord(data.estimate.status)}`
                  : '—',
              )}
              {row('agreed', text.agreed, formatMoney(data.payments?.summary.agreed ?? null))}
              {/* live check 2026-10-31: the stages' "still due" was 0 for an object without stages -- the settlement says agreed less received */}
              {row('received', text.received, formatMoney(data.money?.received ?? data.payments?.summary.received ?? null))}
              {row('to-receive', text.to_receive, formatMoney(data.money ? data.money.to_receive : (data.payments?.summary.to_receive ?? null)))}
            </dl>
          </div>
          <div className="space-y-1">
            <span className="block font-semibold text-slate-700">{text.dates}</span>
            <dl className="space-y-1">
              {row('works', text.works_dates, data.first ? `${formatDay(data.first)} – ${formatDay(data.last)}` : text.not_planned)}
              {row('next-stage', text.next_stage, nextStage ? `${nextStage.title} · ${formatDay(nextStage.due_on)}` : '—')}
            </dl>
          </div>
          <div className="space-y-1">
            <span className="block font-semibold text-slate-700">{text.risks}</span>
            {risks.length === 0 ? (
              <p aria-label="object-summary-no-risks" className="text-slate-600">{text.no_risks}</p>
            ) : (
              <dl className="space-y-1">{risks.map((r) => row(`risk-${r.room_id}`, r.room_name, `⚠ ${r.count}`))}</dl>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
