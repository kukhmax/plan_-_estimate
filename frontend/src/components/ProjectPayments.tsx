import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { archivePayment, fetchFinance, fetchPayments, restorePayment, saveAgreedAmount } from '../api/payments';
import { useI18n } from '../hooks/useI18n';
import type { Finance, InvoiceState, Payment, PaymentList } from '../types/payment';
import { localizeApiError } from '../utils/apiErrors';
import { formatDay, formatMoney, positiveAmount, tabOf, toInput, type PaymentTab } from '../utils/paymentFormat';
import { useConnection } from '../offline/connection';
import { Ico } from './Ico';
import { PaymentForm } from './PaymentForm';
import { PendingMark } from './PendingMark';
import { PhotoCardButton, PhotoCardPanel } from './PhotoCard';

interface ProjectPaymentsProps {
  projectId: string;
}

const TABS: PaymentTab[] = ['invoices', 'client', 'materials'];
const STATE_STYLE: Record<InvoiceState, string> = {
  PAID: 'bg-emerald-100 text-emerald-800',
  PARTIAL: 'bg-amber-100 text-amber-900',
  OVERDUE: 'bg-red-100 text-red-800',
  OPEN: 'bg-slate-100 text-slate-700',
};

const primary = 'w-full min-h-11 px-4 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50';
const secondary = 'flex-1 min-h-11 px-3 py-2 text-sm rounded-xl border border-slate-200 bg-white text-slate-700 font-medium hover:bg-slate-50 disabled:opacity-50';

/**
 * "Faktury i zaliczki" (a backlog item, not a roadmap stage): what the client was invoiced and paid, and what the owner spent on materials.
 * A register for reference: nothing here issues an invoice. Every sum is the server's; the phone only shows them.
 */
export function ProjectPayments({ projectId }: ProjectPaymentsProps) {
  const { t } = useI18n();
  const text = t.payments;
  const [list, setList] = useState<PaymentList | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [tab, setTab] = useState<PaymentTab>('invoices');
  const [showArchived, setShowArchived] = useState(false);
  const [form, setForm] = useState<{ payment?: Payment } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    try {
      setList(await fetchPayments(projectId, showArchived));
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [projectId, showArchived]);

  useEffect(() => {
    void load();
  }, [load]);

  const items = list?.items ?? [];
  const inTab = useMemo(() => items.filter((item) => tabOf(item.kind) === tab), [items, tab]);
  // the invoices an advance or a payment can be tied to: the active ones of the whole object, whatever tab is open
  const invoices = useMemo(() => items.filter((item) => item.kind === 'INVOICE'), [items]);

  const changeArchive = async (payment: Payment) => {
    if (busyId) return;
    setBusyId(payment.id);
    setMessage(null);
    try {
      await (payment.is_archived ? restorePayment(projectId, payment.id) : archivePayment(projectId, payment.id));
      setMessage({ kind: 'ok', text: payment.is_archived ? text.restored : text.archived });
      await load();
    } catch (err) {
      const localized = localizeApiError(err, t);
      setMessage({ kind: 'error', text: localized && !localized.startsWith('Request failed') ? localized : text.archive_error });
    } finally {
      setBusyId(null);
    }
  };

  const saved = async () => {
    setForm(null);
    setMessage({ kind: 'ok', text: text.saved });
    await load();
  };

  const addLabel = tab === 'invoices' ? text.add_invoice : tab === 'materials' ? text.add_expense : text.add_client;
  const emptyLabel = tab === 'invoices' ? text.empty_invoices : tab === 'materials' ? text.empty_materials : text.empty_client;

  return (
    <section aria-label="project-payments" className="space-y-3">
      <p aria-label="payments-disclaimer" className="text-xs text-[var(--tg-theme-hint-color)] break-words">{text.disclaimer}</p>

      {loading && <p className="text-sm text-slate-500 text-center py-3">{text.loading}</p>}
      {!loading && loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
          <button type="button" aria-label="payments-retry" onClick={() => void load()} className={primary}><Ico>🔄</Ico>{text.retry}</button>
        </div>
      )}

      {list && (
        <>
          <SummaryCard projectId={projectId} list={list} onChanged={load} />
          {items.some((item) => item._pending) && (
            <p aria-label="payments-pending-note" className="text-xs text-sky-900 bg-sky-50 border border-sky-100 rounded-xl px-3 py-2 break-words">
              {text.pending_totals}
            </p>
          )}

          <div role="tablist" aria-label="payments-tabs" className="grid grid-cols-3 gap-2">
            {TABS.map((id) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                aria-label={`payments-tab-${id}`}
                onClick={() => {
                  setTab(id);
                  setForm(null);
                  setMessage(null);
                }}
                className={`min-h-11 px-1 py-2 text-xs font-semibold rounded-xl border break-words ${
                  tab === id ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white border-slate-200 text-slate-700'
                }`}
              >
                {text.tabs[id]}
              </button>
            ))}
          </div>

          {form === null ? (
            <button type="button" aria-label="payment-add" onClick={() => setForm({})} className={primary}>
              <Ico>➕</Ico>{addLabel}
            </button>
          ) : (
            <PaymentForm
              key={form.payment?.id ?? `new-${tab}`}
              projectId={projectId}
              tab={tab}
              payment={form.payment}
              invoices={invoices}
              onSaved={() => void saved()}
              onCancel={() => setForm(null)}
            />
          )}

          {message && (
            <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>
              {message.text}
            </p>
          )}

          <label className="flex items-center gap-2 min-h-11 text-sm text-[var(--tg-theme-text-color)]">
            <input type="checkbox" aria-label="payments-show-archived" checked={showArchived} onChange={(event) => setShowArchived(event.target.checked)} className="h-5 w-5" />
            <span className="min-w-0 break-words">{text.show_archived}</span>
          </label>

          {inTab.length === 0 ? (
            <p aria-label="payments-empty" className="text-sm text-slate-500 text-center py-4">{emptyLabel}</p>
          ) : (
            <ul aria-label="payments-list" className="space-y-2">
              {inTab.map((payment) => (
                <PaymentCard
                  key={payment.id}
                  payment={payment}
                  busy={busyId === payment.id}
                  onEdit={() => {
                    setMessage(null);
                    setForm({ payment });
                  }}
                  onArchive={() => void changeArchive(payment)}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function PaymentCard({ payment, busy, onEdit, onArchive }: { payment: Payment; busy: boolean; onEdit: () => void; onArchive: () => void }) {
  const { t } = useI18n();
  const text = t.payments;
  const meta: string[] = [formatDay(payment.occurred_on)];
  if (payment.number) meta.push(`${text.fields.number}: ${payment.number}`);
  if (payment.counterparty) meta.push(payment.counterparty);
  if (payment.kind === 'EXPENSE' && payment.document_kind) meta.push(text.document_kind[payment.document_kind]);
  return (
    <li aria-label={`payment-${payment.id}`} className={`bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-2 ${payment.is_archived ? 'opacity-70' : ''}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <span className="text-xs font-semibold text-slate-500">{text.kind[payment.kind]}</span>
          <PendingMark record={payment} id={payment.id} />
          {payment.is_archived && <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">{t.common.archived_badge}</span>}
          {payment.state && !payment.is_archived && (
            <span aria-label={`payment-state-${payment.id}`} className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATE_STYLE[payment.state]}`}>
              {text.state[payment.state]}
            </span>
          )}
        </div>
        {/* the receipt or the invoice of the record: the photos of the object's own pipeline (IA-3) */}
        <PhotoCardButton context="PAYMENT" targetId={payment.id} />
      </div>
      <PhotoCardPanel context="PAYMENT" targetId={payment.id} locationSegments={[text.title, payment.title]} />
      <p className="text-sm font-semibold text-slate-900 break-words">{payment.title}</p>
      <p aria-label={`payment-amount-${payment.id}`} className="text-lg font-bold text-slate-900 break-words">{formatMoney(payment.amount_gross)}</p>
      <p className="text-xs text-slate-600 break-words">{meta.join(' · ')}</p>
      {payment.kind === 'INVOICE' && (
        <div className="text-xs text-slate-600 space-y-0.5">
          {payment.due_on && <p>{text.fields.due}: {formatDay(payment.due_on)}</p>}
          {/* what is settled and what is left is the server's to count: a waiting invoice has none yet */}
          {payment.settled !== null && <p aria-label={`payment-settled-${payment.id}`}>{text.settled}: {formatMoney(payment.settled)} · {text.remaining}: {formatMoney(payment.remaining)}</p>}
        </div>
      )}
      {payment.note && <p className="text-xs text-slate-600 whitespace-pre-wrap break-words">{payment.note}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" aria-label={`payment-edit-${payment.id}`} onClick={onEdit} className={secondary}>
          <Ico>✏️</Ico>{t.common.edit}
        </button>
        <button type="button" aria-label={`payment-archive-${payment.id}`} disabled={busy} onClick={onArchive} className={secondary}>
          <Ico>{payment.is_archived ? '♻️' : '🗃️'}</Ico>{payment.is_archived ? t.common.restore : t.common.archive}
        </button>
      </div>
    </li>
  );
}

function SummaryCard({ projectId, list, onChanged }: { projectId: string; list: PaymentList; onChanged: () => Promise<void> }) {
  const { t } = useI18n();
  const text = t.payments;
  const { summary } = list;
  const [editing, setEditing] = useState(false);
  const [finance, setFinance] = useState<Finance | null>(null);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // the agreed amount is the server's (the estimate suggests it, the totals follow it): it is changed with a signal only
  const { offline } = useConnection();

  const open = async () => {
    setEditing(true);
    setError(null);
    setValue(toInput(list.agreed_amount));
    try {
      setFinance(await fetchFinance(projectId));
    } catch {
      setFinance(null);
    }
  };

  const persist = async (amount: string | null) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await saveAgreedAmount(projectId, amount);
      setEditing(false);
      await onChanged();
    } catch (err) {
      const localized = localizeApiError(err, t);
      setError(localized && !localized.startsWith('Request failed') ? localized : text.agreed.save_error);
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const amount = positiveAmount(value);
    if (amount === null) {
      setError(text.errors.amount);
      return;
    }
    void persist(amount);
  };

  const rows: { key: string; label: string; value: string | null; negative?: boolean }[] = [
    { key: 'agreed', label: text.summary.agreed, value: list.agreed_amount },
    { key: 'invoiced', label: text.summary.invoiced, value: summary.invoiced },
    { key: 'invoiced_unpaid', label: text.summary.invoiced_unpaid, value: summary.invoiced_unpaid },
    { key: 'received', label: text.summary.received, value: summary.received },
    { key: 'to_receive', label: text.summary.to_receive, value: summary.to_receive },
    { key: 'expenses', label: text.summary.expenses, value: summary.expenses },
    { key: 'result', label: text.summary.result, value: summary.result, negative: summary.result.startsWith('-') },
  ];

  return (
    <article aria-label="payments-summary" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
      <dl className="space-y-1.5 text-sm">
        {rows.map((row) => (
          <div key={row.key} aria-label={`summary-${row.key}`} className="flex flex-wrap items-baseline justify-between gap-x-3">
            <dt className="text-slate-500 min-w-0 break-words">{row.label}</dt>
            <dd className={`font-semibold break-words ${row.negative ? 'text-red-600' : 'text-slate-900'}`}>
              {row.value === null ? text.summary.not_set : formatMoney(row.value)}
            </dd>
          </div>
        ))}
      </dl>

      {!editing ? (
        <>
          <button type="button" aria-label="agreed-edit" disabled={offline} onClick={() => void open()} className={secondary.replace('flex-1', 'w-full')}>
            <Ico>✏️</Ico>{list.agreed_amount === null ? text.agreed.set : text.agreed.change}
          </button>
          {offline && <p aria-label="agreed-offline" className="text-xs text-slate-500 break-words">{text.agreed.needs_connection}</p>}
        </>
      ) : (
        <form aria-label="agreed-form" onSubmit={submit} noValidate className="space-y-2">
          <label htmlFor="agreed-amount" className="block text-xs font-semibold text-slate-600">{text.agreed.label}</label>
          <input
            id="agreed-amount"
            aria-label="agreed-amount"
            inputMode="decimal"
            autoComplete="off"
            value={value}
            placeholder="0,00"
            onChange={(event) => setValue(event.target.value)}
            className="w-full min-h-11 border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 bg-white"
          />
          {finance?.suggestion && (
            <button type="button" aria-label="agreed-suggestion" onClick={() => setValue(toInput(finance.suggestion?.amount))} className={secondary.replace('flex-1', 'w-full')}>
              {text.agreed.suggestion
                .replace('{amount}', formatMoney(finance.suggestion.amount))
                .replace('{version}', String(finance.suggestion.estimate_version))}
            </button>
          )}
          {error && <p role="alert" className="text-sm text-red-600 break-words">{error}</p>}
          <div className="flex flex-col gap-2">
            <button type="submit" aria-label="agreed-save" disabled={busy} className={primary}>
              <Ico>💾</Ico>{busy ? t.common.saving : t.common.save}
            </button>
            {list.agreed_amount !== null && (
              <button type="button" aria-label="agreed-clear" disabled={busy} onClick={() => void persist(null)} className={secondary.replace('flex-1', 'w-full')}>
                <Ico>🧹</Ico>{text.agreed.clear}
              </button>
            )}
            <button type="button" aria-label="agreed-cancel" onClick={() => setEditing(false)} className={secondary.replace('flex-1', 'w-full')}>
              <Ico>✖️</Ico>{t.common.cancel}
            </button>
          </div>
        </form>
      )}
    </article>
  );
}
