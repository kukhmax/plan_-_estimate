import { FormEvent, useRef, useState } from 'react';
import { createPayment, updatePayment } from '../api/payments';
import { useI18n } from '../hooks/useI18n';
import { newId } from '../offline/ids';
import {
  MAX_COUNTERPARTY_LENGTH,
  MAX_NOTE_LENGTH,
  MAX_NUMBER_LENGTH,
  MAX_TITLE_LENGTH,
  PAYMENT_CATEGORIES,
  type Payment,
  type PaymentCategory,
  type PaymentDocumentKind,
  type PaymentFields,
  type PaymentKind,
} from '../types/payment';
import { localizeApiError } from '../utils/apiErrors';
import { formatDay, formatMoney, optionalAmount, optionalRate, positiveAmount, todayInPoland, toInput, type PaymentTab } from '../utils/paymentFormat';
import { Ico } from './Ico';

interface PaymentFormProps {
  projectId: string;
  tab: PaymentTab;
  /** The record being changed; none for a new one. */
  payment?: Payment;
  /** The invoices an advance or a payment can be tied to. */
  invoices: Payment[];
  onSaved: () => void;
  onCancel: () => void;
}

const HINTS: Record<PaymentTab, string[]> = {
  invoices: ['hint_invoice_1', 'hint_invoice_2', 'hint_invoice_3'],
  client: ['hint_client_1', 'hint_client_2', 'hint_client_3'],
  materials: ['hint_material_1', 'hint_material_2', 'hint_material_3', 'hint_material_4'],
};

type FieldError = 'title' | 'amount' | 'net' | 'vat' | 'due';

const field = 'w-full min-h-11 border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 bg-white';
const label = 'block text-xs font-semibold text-slate-600 mb-1';

/**
 * One form for the three tabs: a new record or a change of one. Only the fields of the kind are shown; the rare ones are under "Opcje".
 * Money is typed as text and checked here for its shape only; the sums are the server's.
 */
export function PaymentForm({ projectId, tab, payment, invoices, onSaved, onCancel }: PaymentFormProps) {
  const { t } = useI18n();
  const text = t.payments;
  const [moneyKind, setMoneyKind] = useState<PaymentKind>(payment && payment.kind !== 'INVOICE' && payment.kind !== 'EXPENSE' ? payment.kind : 'ADVANCE');
  const [title, setTitle] = useState(payment?.title ?? '');
  const [amount, setAmount] = useState(toInput(payment?.amount_gross));
  const [day, setDay] = useState(payment?.occurred_on ?? todayInPoland());
  const [due, setDue] = useState(payment?.due_on ?? '');
  const [number, setNumber] = useState(payment?.number ?? '');
  const [counterparty, setCounterparty] = useState(payment?.counterparty ?? '');
  const [documentKind, setDocumentKind] = useState<PaymentDocumentKind>(payment?.document_kind ?? 'RECEIPT');
  // a new expense is for materials until another is tapped (the usual case, no tap); an old one without a category keeps none
  const [category, setCategory] = useState<PaymentCategory | null>(payment ? (payment.category ?? null) : 'MATERIALS');
  const [net, setNet] = useState(toInput(payment?.amount_net));
  const [vat, setVat] = useState(toInput(payment?.vat_rate));
  const [settles, setSettles] = useState(payment?.settles_id ?? '');
  const [note, setNote] = useState(payment?.note ?? '');
  const hasOptional = [payment?.amount_net, payment?.vat_rate, payment?.settles_id, payment?.note, tab === 'materials' ? payment?.number : null].some(Boolean);
  const [more, setMore] = useState(hasOptional);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  // the same id goes with every try to save one new record, so a repeated tap never makes two
  const newRecordId = useRef(newId());

  const kind: PaymentKind = payment ? payment.kind : tab === 'invoices' ? 'INVOICE' : tab === 'materials' ? 'EXPENSE' : moneyKind;
  const showsNumber = kind === 'INVOICE' || kind === 'EXPENSE';
  const hasNetVat = kind === 'INVOICE' || kind === 'EXPENSE';

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const bad: FieldError[] = [];
    const gross = positiveAmount(amount);
    const netValue = hasNetVat ? optionalAmount(net) : '';
    const vatValue = hasNetVat ? optionalRate(vat) : '';
    if (title.trim() === '') bad.push('title');
    if (gross === null) bad.push('amount');
    if (netValue === null) bad.push('net');
    if (vatValue === null) bad.push('vat');
    if (kind === 'INVOICE' && due !== '' && due < day) bad.push('due');
    setErrors(bad);
    if (bad.length > 0 || gross === null || netValue === null || vatValue === null) return;

    const fields: PaymentFields = {
      title: title.trim(),
      amount_gross: gross,
      occurred_on: day,
      number: showsNumber && number.trim() !== '' ? number.trim() : null,
      amount_net: netValue === '' ? null : netValue,
      vat_rate: vatValue === '' ? null : vatValue,
      due_on: kind === 'INVOICE' && due !== '' ? due : null,
      settles_id: (kind === 'ADVANCE' || kind === 'PAYMENT') && settles !== '' ? settles : null,
      counterparty: kind === 'EXPENSE' && counterparty.trim() !== '' ? counterparty.trim() : null,
      document_kind: kind === 'EXPENSE' ? documentKind : null,
      category: kind === 'EXPENSE' ? category : null,
      note: note.trim() !== '' ? note.trim() : null,
    };
    setBusy(true);
    setFailure(null);
    try {
      if (payment) await updatePayment(projectId, payment.id, fields);
      else await createPayment(projectId, newRecordId.current, kind, fields);
      onSaved();
    } catch (err) {
      const localized = localizeApiError(err, t);
      setFailure(localized && !localized.startsWith('Request failed') ? localized : text.save_error);
      setBusy(false);
    }
  };

  const hints = HINTS[tab];
  const segment = (active: boolean) =>
    `flex-1 min-h-11 px-3 py-2 text-sm rounded-xl border font-semibold break-words ${
      active ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white border-slate-200 text-slate-700'
    }`;
  const dayLabel = tab === 'invoices' ? text.fields.date_invoice : tab === 'materials' ? text.fields.date_expense : text.fields.date_money;
  const titleLabel = tab === 'materials' ? text.fields.title_expense : text.fields.title;
  const heading = payment ? text.edit_title : tab === 'invoices' ? text.add_invoice : tab === 'materials' ? text.add_expense : text.add_client;
  const settleOptions = invoices.filter((invoice) => !invoice.is_archived || invoice.id === payment?.settles_id);

  return (
    <form aria-label="payment-form" onSubmit={submit} noValidate className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="text-sm font-semibold text-slate-900 break-words">{heading}</h3>

      {tab === 'client' && !payment && (
        <div role="group" aria-label="payment-kind" className="flex gap-2">
          {(['ADVANCE', 'PAYMENT'] as const).map((value) => (
            <button key={value} type="button" aria-pressed={moneyKind === value} aria-label={`payment-kind-${value}`} onClick={() => setMoneyKind(value)} className={segment(moneyKind === value)}>
              {text.kind[value]}
            </button>
          ))}
        </div>
      )}

      <div>
        <label htmlFor="payment-title" className={label}>{titleLabel}</label>
        <input
          id="payment-title"
          aria-label="payment-title"
          value={title}
          maxLength={MAX_TITLE_LENGTH}
          onChange={(event) => setTitle(event.target.value)}
          className={field}
        />
        {!payment && (
          <div className="flex flex-wrap gap-2 mt-2">
            {hints.map((key) => (
              <button
                key={key}
                type="button"
                aria-label={`payment-${key}`}
                onClick={() => setTitle(text.hints[key as keyof typeof text.hints])}
                className="min-h-11 px-3 py-1 text-xs rounded-full border border-slate-200 bg-slate-50 text-slate-700 break-words"
              >
                {text.hints[key as keyof typeof text.hints]}
              </button>
            ))}
          </div>
        )}
        {errors.includes('title') && <p role="alert" className="text-xs text-red-600 mt-1">{text.errors.title}</p>}
      </div>

      {kind === 'EXPENSE' && (
        <div>
          <label htmlFor="payment-counterparty" className={label}>{text.fields.counterparty}</label>
          <input
            id="payment-counterparty"
            aria-label="payment-counterparty"
            value={counterparty}
            maxLength={MAX_COUNTERPARTY_LENGTH}
            onChange={(event) => setCounterparty(event.target.value)}
            className={field}
          />
        </div>
      )}

      {kind === 'INVOICE' && (
        <div>
          <label htmlFor="payment-number" className={label}>{text.fields.number}</label>
          <input id="payment-number" aria-label="payment-number" value={number} maxLength={MAX_NUMBER_LENGTH} onChange={(event) => setNumber(event.target.value)} className={field} />
        </div>
      )}

      <div>
        <label htmlFor="payment-amount" className={label}>{text.fields.amount}</label>
        <input
          id="payment-amount"
          aria-label="payment-amount"
          inputMode="decimal"
          autoComplete="off"
          value={amount}
          placeholder="0,00"
          onChange={(event) => setAmount(event.target.value)}
          className={field}
        />
        {errors.includes('amount') && <p role="alert" className="text-xs text-red-600 mt-1">{text.errors.amount}</p>}
      </div>

      <div>
        <label htmlFor="payment-day" className={label}>{dayLabel}</label>
        <input id="payment-day" aria-label="payment-day" type="date" value={day} onChange={(event) => setDay(event.target.value)} className={field} />
      </div>

      {kind === 'INVOICE' && (
        <div>
          <label htmlFor="payment-due" className={label}>{text.fields.due}</label>
          <input id="payment-due" aria-label="payment-due" type="date" value={due} onChange={(event) => setDue(event.target.value)} className={field} />
          {errors.includes('due') && <p role="alert" className="text-xs text-red-600 mt-1">{text.errors.due}</p>}
          <p aria-label="payment-due-hint" className="text-xs text-[var(--tg-theme-hint-color)] mt-1 break-words">{text.fields.due_hint}</p>
        </div>
      )}

      {kind === 'EXPENSE' && (
        <div>
          <span className={label}>{text.fields.document_kind}</span>
          <div role="group" aria-label="payment-document-kind" className="flex gap-2">
            {(['RECEIPT', 'INVOICE'] as const).map((value) => (
              <button key={value} type="button" aria-pressed={documentKind === value} aria-label={`payment-document-${value}`} onClick={() => setDocumentKind(value)} className={segment(documentKind === value)}>
                {text.document_kind[value]}
              </button>
            ))}
          </div>
        </div>
      )}

      {kind === 'EXPENSE' && (
        <div>
          <span className={label}>{text.fields.category}</span>
          <div role="group" aria-label="payment-category" className="flex flex-wrap gap-2">
            {PAYMENT_CATEGORIES.map((value) => (
              <button key={value} type="button" aria-pressed={category === value} aria-label={`payment-category-${value}`} onClick={() => setCategory(value)} className={`${segment(category === value)} flex-none`}>
                {text.category[value]}
              </button>
            ))}
          </div>
        </div>
      )}

      <button
        type="button"
        aria-label="payment-more"
        aria-expanded={more}
        onClick={() => setMore((open) => !open)}
        className="w-full min-h-11 px-3 py-2 text-sm rounded-xl border border-slate-200 bg-slate-50 text-slate-700 font-medium"
      >
        <Ico>{more ? '▾' : '▸'}</Ico>{text.more}
      </button>

      {more && (
        <div aria-label="payment-more-fields" className="space-y-3">
          {kind === 'EXPENSE' && (
            <div>
              <label htmlFor="payment-number" className={label}>{text.fields.number}</label>
              <input id="payment-number" aria-label="payment-number" value={number} maxLength={MAX_NUMBER_LENGTH} onChange={(event) => setNumber(event.target.value)} className={field} />
            </div>
          )}
          {hasNetVat && (
            <>
              <div>
                <label htmlFor="payment-net" className={label}>{text.fields.net}</label>
                <input id="payment-net" aria-label="payment-net" inputMode="decimal" autoComplete="off" value={net} onChange={(event) => setNet(event.target.value)} className={field} />
                {errors.includes('net') && <p role="alert" className="text-xs text-red-600 mt-1">{text.errors.net}</p>}
              </div>
              <div>
                <label htmlFor="payment-vat" className={label}>{text.fields.vat}</label>
                <input id="payment-vat" aria-label="payment-vat" inputMode="decimal" autoComplete="off" value={vat} onChange={(event) => setVat(event.target.value)} className={field} />
                {errors.includes('vat') && <p role="alert" className="text-xs text-red-600 mt-1">{text.errors.vat}</p>}
              </div>
            </>
          )}
          {tab === 'client' && (
            <div>
              <label htmlFor="payment-settles" className={label}>{text.fields.settles}</label>
              <select id="payment-settles" aria-label="payment-settles" value={settles} onChange={(event) => setSettles(event.target.value)} className={field}>
                <option value="">{text.fields.settles_none}</option>
                {settleOptions.map((invoice) => (
                  <option key={invoice.id} value={invoice.id}>
                    {`${invoice.number ? `${invoice.number} · ` : ''}${invoice.title} · ${formatMoney(invoice.amount_gross)} · ${formatDay(invoice.occurred_on)}`}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label htmlFor="payment-note" className={label}>{text.fields.note}</label>
            <textarea id="payment-note" aria-label="payment-note" value={note} maxLength={MAX_NOTE_LENGTH} onChange={(event) => setNote(event.target.value)} className={`${field} min-h-24`} />
          </div>
        </div>
      )}

      {failure && <p role="alert" className="text-sm text-red-600 break-words">{failure}</p>}

      <div className="flex flex-col gap-2">
        <button type="submit" aria-label="payment-save" disabled={busy} className="w-full min-h-11 px-4 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-50">
          <Ico>{busy ? '⏳' : '💾'}</Ico>{busy ? t.common.saving : t.common.save}
        </button>
        <button type="button" aria-label="payment-cancel" onClick={onCancel} className="w-full min-h-11 px-4 py-2 text-sm rounded-xl border border-slate-200 bg-white text-slate-700 font-medium">
          <Ico>✖️</Ico>{t.common.cancel}
        </button>
      </div>
    </form>
  );
}
