import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as paymentsApi from './api/payments';
import { ApiError } from './api/http';
import { ProjectPayments } from './components/ProjectPayments';
import { I18nProvider } from './hooks/useI18n';
import type { Finance, Payment, PaymentCategory, PaymentList } from './types/payment';
import { formatDay, formatMoney, optionalRate, positiveAmount, todayInPoland } from './utils/paymentFormat';

vi.mock('./api/payments', () => ({
  fetchPayments: vi.fn(),
  createPayment: vi.fn(),
  updatePayment: vi.fn(),
  archivePayment: vi.fn(),
  restorePayment: vi.fn(),
  fetchFinance: vi.fn(),
  saveAgreedAmount: vi.fn(),
}));

const projectId = '11111111-1111-1111-1111-111111111111';

const base = (over: Partial<Payment>): Payment => ({
  id: 'p0',
  project_id: projectId,
  kind: 'INVOICE',
  title: 'Faktura za etap 1',
  number: null,
  amount_gross: '1000.00',
  amount_net: null,
  vat_rate: null,
  occurred_on: '2026-10-01',
  due_on: null,
  settles_id: null,
  counterparty: null,
  document_kind: null,
  note: null,
  is_archived: false,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
  settled: null,
  remaining: null,
  state: null,
  ...over,
});

const INVOICE = base({ id: 'inv1', number: 'FV 1/2026', due_on: '2026-10-15', settled: '400.00', remaining: '600.00', state: 'PARTIAL' });
const ADVANCE = base({ id: 'adv1', kind: 'ADVANCE', title: 'Zaliczka na materiały', amount_gross: '400.00', occurred_on: '2026-09-28', settles_id: 'inv1' });
const EXPENSE = base({
  id: 'exp1', kind: 'EXPENSE', title: 'Gładź i grunt', amount_gross: '250.50', counterparty: 'Leroy Merlin', document_kind: 'RECEIPT', occurred_on: '2026-10-03',
});

// the sums are deliberately not the sums of the rows: the screen shows what the server sent and counts nothing
const listOf = (items: Payment[], over: Partial<PaymentList> = {}): PaymentList => ({
  items,
  total: items.length,
  summary: { invoiced: '1000.00', received: '400.00', expenses: '250.50', invoiced_unpaid: '600.00', to_receive: '39600.00', result: '149.50' },
  agreed_amount: '40000.00',
  ...over,
});

const FINANCE: Finance = {
  agreed_amount: '40000.00',
  currency: 'PLN',
  suggestion: { amount: '38420.00', estimate_id: 'e1', estimate_version: 3, status: 'ACCEPTED' },
};

function renderScreen() {
  return render(<I18nProvider><ProjectPayments projectId={projectId} /></I18nProvider>);
}
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe('ProjectPayments — "Faktury i zaliczki" (IA-2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(listOf([INVOICE, ADVANCE, EXPENSE]));
    vi.mocked(paymentsApi.fetchFinance).mockResolvedValue(FINANCE);
    vi.mocked(paymentsApi.createPayment).mockImplementation(async (_p, id, kind, fields) => base({ id, kind, ...fields } as Partial<Payment>));
    vi.mocked(paymentsApi.updatePayment).mockResolvedValue(INVOICE);
    vi.mocked(paymentsApi.saveAgreedAmount).mockResolvedValue(FINANCE);
  });

  describe('the summary', () => {
    it('shows the sums the server sent and counts none of them', async () => {
      renderScreen();
      const summary = await screen.findByLabelText('payments-summary');
      expect(within(summary).getByLabelText('summary-agreed')).toHaveTextContent('Umówiona kwota40000,00 zł');
      expect(within(summary).getByLabelText('summary-invoiced')).toHaveTextContent('1000,00 zł');
      expect(within(summary).getByLabelText('summary-invoiced_unpaid')).toHaveTextContent('600,00 zł');
      expect(within(summary).getByLabelText('summary-received')).toHaveTextContent('400,00 zł');
      // 40000 − 400 would be 39600 anyway; the proof of "not counted" is the next two rows
      expect(within(summary).getByLabelText('summary-to_receive')).toHaveTextContent('39600,00 zł');
      expect(within(summary).getByLabelText('summary-expenses')).toHaveTextContent('250,50 zł');
      expect(within(summary).getByLabelText('summary-result')).toHaveTextContent('149,50 zł');
    });

    it('prints a sum it was given as sent even when it does not add up (nothing is calculated here)', async () => {
      vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(
        listOf([], { summary: { invoiced: '7.00', received: '1.00', expenses: '2.00', invoiced_unpaid: '3.00', to_receive: '12345.67', result: '-9.99' } }),
      );
      renderScreen();
      const summary = await screen.findByLabelText('payments-summary');
      expect(within(summary).getByLabelText('summary-to_receive')).toHaveTextContent('12345,67 zł');
      expect(within(summary).getByLabelText('summary-result')).toHaveTextContent('-9,99 zł');
      expect(within(summary).getByLabelText('summary-result').querySelector('dd')?.className).toContain('text-red-600');
    });

    it('says "not set" for the amount to receive when there is no agreed amount', async () => {
      vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(
        listOf([], { agreed_amount: null, summary: { invoiced: '0.00', received: '0.00', expenses: '0.00', invoiced_unpaid: '0.00', to_receive: null, result: '0.00' } }),
      );
      renderScreen();
      const summary = await screen.findByLabelText('payments-summary');
      expect(within(summary).getByLabelText('summary-agreed')).toHaveTextContent('nie ustawiono');
      expect(within(summary).getByLabelText('summary-to_receive')).toHaveTextContent('nie ustawiono');
      expect(screen.getByLabelText('agreed-edit')).toHaveTextContent('Ustaw umówioną kwotę');
    });

    it('carries the note that it is a register and not an invoice', async () => {
      renderScreen();
      expect(await screen.findByLabelText('payments-disclaimer')).toHaveTextContent('To nie jest faktura');
    });
  });

  describe('the statement for the client (IA-6a)', () => {
    it('is a button only when the screen can lead to the statement, and tapping it leads there', async () => {
      const lead = vi.fn();
      render(<I18nProvider><ProjectPayments projectId={projectId} onOpenStatement={lead} /></I18nProvider>);
      const button = await screen.findByLabelText('payments-statement');
      expect(button).toHaveTextContent('Rozliczenie dla klienta (PDF)');
      expect(button.className).toContain('min-h-11');
      fireEvent.click(button);
      expect(lead).toHaveBeenCalledTimes(1);
    });

    it('is not shown without a way to it', async () => {
      renderScreen();
      await screen.findByLabelText('payments-summary');
      expect(screen.queryByLabelText('payments-statement')).toBeNull();
    });
  });

  describe('the agreed amount', () => {
    it('offers the amount of the accepted estimate as a suggestion that becomes the value only when tapped, and saves it', async () => {
      renderScreen();
      fireEvent.click(await screen.findByLabelText('agreed-edit'));
      expect(await screen.findByLabelText('agreed-suggestion')).toHaveTextContent('Z kosztorysu (wersja 3): 38420,00 zł');
      expect((screen.getByLabelText('agreed-amount') as HTMLInputElement).value).toBe('40000,00');
      fireEvent.click(screen.getByLabelText('agreed-suggestion'));
      expect((screen.getByLabelText('agreed-amount') as HTMLInputElement).value).toBe('38420,00');
      fireEvent.click(screen.getByLabelText('agreed-save'));
      await waitFor(() => expect(paymentsApi.saveAgreedAmount).toHaveBeenCalledWith(projectId, '38420.00'));
      await waitFor(() => expect(screen.queryByLabelText('agreed-form')).toBeNull());
      expect(paymentsApi.fetchPayments).toHaveBeenCalledTimes(2);
    });

    it('takes a comma and refuses zero or text before anything is sent', async () => {
      renderScreen();
      fireEvent.click(await screen.findByLabelText('agreed-edit'));
      for (const bad of ['0', '0,00', 'abc', '1,234', '']) {
        type('agreed-amount', bad);
        fireEvent.click(screen.getByLabelText('agreed-save'));
        expect(await screen.findByRole('alert')).toHaveTextContent('Wpisz kwotę większą od zera');
        expect(paymentsApi.saveAgreedAmount).not.toHaveBeenCalled();
      }
      type('agreed-amount', '39500,5');
      fireEvent.click(screen.getByLabelText('agreed-save'));
      await waitFor(() => expect(paymentsApi.saveAgreedAmount).toHaveBeenCalledWith(projectId, '39500.5'));
    });

    it('clears the amount with null and works without a suggestion when the estimate cannot be read', async () => {
      vi.mocked(paymentsApi.fetchFinance).mockRejectedValue(new Error('offline'));
      renderScreen();
      fireEvent.click(await screen.findByLabelText('agreed-edit'));
      expect(screen.queryByLabelText('agreed-suggestion')).toBeNull();
      fireEvent.click(screen.getByLabelText('agreed-clear'));
      await waitFor(() => expect(paymentsApi.saveAgreedAmount).toHaveBeenCalledWith(projectId, null));
    });

    it('keeps the form open and says so when the server refuses', async () => {
      vi.mocked(paymentsApi.saveAgreedAmount).mockRejectedValue(new ApiError('Request failed (500)', 500));
      renderScreen();
      fireEvent.click(await screen.findByLabelText('agreed-edit'));
      fireEvent.click(screen.getByLabelText('agreed-save'));
      expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zapisać kwoty.');
      expect(screen.getByLabelText('agreed-form')).toBeInTheDocument();
    });
  });

  describe('the tabs', () => {
    it('opens on the invoices, with its row, its state and what is settled; the other kinds are on their own tabs', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      expect(screen.getByLabelText('payments-tab-invoices')).toHaveAttribute('aria-selected', 'true');
      expect(screen.getByLabelText('payment-inv1')).toHaveTextContent('Faktura za etap 1');
      expect(screen.getByLabelText('payment-amount-inv1')).toHaveTextContent('1000,00 zł');
      expect(screen.getByLabelText('payment-state-inv1')).toHaveTextContent('Częściowo');
      expect(screen.getByLabelText('payment-settled-inv1')).toHaveTextContent('Zapłacono: 400,00 zł · Pozostało: 600,00 zł');
      expect(screen.getByLabelText('payment-inv1')).toHaveTextContent('Termin płatności: 15.10.2026');
      expect(screen.getByLabelText('payment-inv1')).toHaveTextContent('FV 1/2026');
      expect(screen.queryByLabelText('payment-adv1')).toBeNull();
      expect(screen.queryByLabelText('payment-exp1')).toBeNull();
    });

    it('lists the money from the client on its tab and the materials on theirs, each with its own empty state', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payments-tab-client'));
      expect(screen.getByLabelText('payment-adv1')).toHaveTextContent('Zaliczka');
      expect(screen.getByLabelText('payment-adv1')).toHaveTextContent('28.09.2026');
      expect(screen.queryByLabelText('payment-state-adv1')).toBeNull();
      fireEvent.click(screen.getByLabelText('payments-tab-materials'));
      expect(screen.getByLabelText('payment-exp1')).toHaveTextContent('Leroy Merlin');
      expect(screen.getByLabelText('payment-exp1')).toHaveTextContent('Paragon');
      expect(screen.getByLabelText('payment-amount-exp1')).toHaveTextContent('250,50 zł');

      vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(listOf([]));
      fireEvent.click(screen.getByLabelText('payments-show-archived'));
      expect(await screen.findByLabelText('payments-empty')).toHaveTextContent('Brak wydatków na materiały');
      fireEvent.click(screen.getByLabelText('payments-tab-client'));
      expect(screen.getByLabelText('payments-empty')).toHaveTextContent('Brak wpłat od klienta');
      fireEvent.click(screen.getByLabelText('payments-tab-invoices'));
      expect(screen.getByLabelText('payments-empty')).toHaveTextContent('Brak faktur');
    });

    it('closes an open form when the tab changes, so a record is never saved under the wrong kind', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect(screen.getByLabelText('payment-form')).toBeInTheDocument();
      fireEvent.click(screen.getByLabelText('payments-tab-materials'));
      expect(screen.queryByLabelText('payment-form')).toBeNull();
      expect(screen.getByLabelText('payment-add')).toHaveTextContent('Dodaj wydatek na materiały');
    });
  });

  describe('adding an invoice', () => {
    it('starts with today and the fields of an invoice; a blank title, a zero or a malformed amount are refused where they are typed', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect((screen.getByLabelText('payment-day') as HTMLInputElement).value).toBe(todayInPoland());
      expect(screen.getByLabelText('payment-number')).toBeInTheDocument();
      expect(screen.getByLabelText('payment-due')).toBeInTheDocument();
      expect(screen.queryByLabelText('payment-counterparty')).toBeNull();
      expect(screen.getByLabelText('payment-amount')).toHaveAttribute('inputmode', 'decimal');

      fireEvent.click(screen.getByLabelText('payment-save'));
      const alerts = (await screen.findAllByRole('alert')).map((node) => node.textContent);
      expect(alerts).toEqual(['Wpisz, za co.', expect.stringContaining('Wpisz kwotę większą od zera')]);
      type('payment-title', 'Etap 2');
      for (const bad of ['0', '0,00', '12,345', '-5', 'x']) {
        type('payment-amount', bad);
        fireEvent.click(screen.getByLabelText('payment-save'));
        expect(await screen.findByRole('alert')).toHaveTextContent('Wpisz kwotę większą od zera');
      }
      expect(paymentsApi.createPayment).not.toHaveBeenCalled();
    });

    it('sends the record with a new id, the kind, the comma turned into a point and the empty fields as null; then shows the list again', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      type('payment-title', '  Etap 2  ');
      type('payment-number', 'FV 2/2026');
      type('payment-amount', '1 500,5'.replace(' ', ''));
      type('payment-day', '2026-10-10');
      type('payment-due', '2026-10-24');
      fireEvent.click(screen.getByLabelText('payment-save'));

      await waitFor(() => expect(paymentsApi.createPayment).toHaveBeenCalledTimes(1));
      const [project, id, kind, fields] = vi.mocked(paymentsApi.createPayment).mock.calls[0];
      expect(project).toBe(projectId);
      expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
      expect(kind).toBe('INVOICE');
      expect(fields).toEqual({
        title: 'Etap 2', amount_gross: '1500.5', occurred_on: '2026-10-10', number: 'FV 2/2026', amount_net: null, vat_rate: null,
        due_on: '2026-10-24', settles_id: null, counterparty: null, document_kind: null, category: null, note: null,
      });
      await waitFor(() => expect(screen.queryByLabelText('payment-form')).toBeNull());
      expect(screen.getByRole('status')).toHaveTextContent('Zapisano.');
      expect(paymentsApi.fetchPayments).toHaveBeenCalledTimes(2);
    });

    it('tells the owner that the due day becomes a reminder of the calendar (IA-5), on an invoice only', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect(screen.getByLabelText('payment-due-hint')).toHaveTextContent('O terminie przypomnimy w kalendarzu: 3 dni wcześniej i w dniu terminu');
      fireEvent.click(screen.getByLabelText('payment-cancel'));
      fireEvent.click(screen.getByLabelText('payments-tab-client'));
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect(screen.queryByLabelText('payment-due-hint')).toBeNull();
    });

    it('refuses a due date before the date of issue', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      type('payment-title', 'Etap 2');
      type('payment-amount', '100');
      type('payment-day', '2026-10-10');
      type('payment-due', '2026-10-09');
      fireEvent.click(screen.getByLabelText('payment-save'));
      expect(await screen.findByRole('alert')).toHaveTextContent('Termin płatności nie może być przed datą wystawienia.');
      expect(paymentsApi.createPayment).not.toHaveBeenCalled();
    });

    it('keeps one id for one new record across failed tries, so a repeated tap cannot make two', async () => {
      vi.mocked(paymentsApi.createPayment).mockRejectedValueOnce(new ApiError('Request failed (500)', 500));
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      type('payment-title', 'Etap 2');
      type('payment-amount', '100');
      fireEvent.click(screen.getByLabelText('payment-save'));
      expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zapisać wpisu.');
      expect(screen.getByLabelText('payment-form')).toBeInTheDocument();
      fireEvent.click(screen.getByLabelText('payment-save'));
      await waitFor(() => expect(paymentsApi.createPayment).toHaveBeenCalledTimes(2));
      const ids = vi.mocked(paymentsApi.createPayment).mock.calls.map((call) => call[1]);
      expect(ids[0]).toBe(ids[1]);
    });

    it('shows the localized text of a refusal with a code', async () => {
      vi.mocked(paymentsApi.createPayment).mockRejectedValueOnce(new ApiError('only an invoice has a due date', 422, 'PAYMENT_INVALID'));
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      type('payment-title', 'Etap 2');
      type('payment-amount', '100');
      fireEvent.click(screen.getByLabelText('payment-save'));
      expect(await screen.findByRole('alert')).toHaveTextContent('Nie można zapisać wpisu');
    });

    it('fills the title from a hint and leaves it free to change', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      fireEvent.click(screen.getByLabelText('payment-hint_invoice_2'));
      expect((screen.getByLabelText('payment-title') as HTMLInputElement).value).toBe('Faktura końcowa');
      type('payment-title', 'Faktura końcowa — łazienka');
      expect((screen.getByLabelText('payment-title') as HTMLInputElement).value).toBe('Faktura końcowa — łazienka');
    });

    it('keeps the rare fields (net, VAT, note) under "Opcje" and sends them when filled', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect(screen.queryByLabelText('payment-net')).toBeNull();
      fireEvent.click(screen.getByLabelText('payment-more'));
      expect(screen.getByLabelText('payment-more')).toHaveAttribute('aria-expanded', 'true');
      type('payment-title', 'Etap 2');
      type('payment-amount', '123');
      type('payment-net', '100');
      type('payment-vat', '23');
      type('payment-note', 'Do 14 dni');
      fireEvent.click(screen.getByLabelText('payment-save'));
      await waitFor(() => expect(paymentsApi.createPayment).toHaveBeenCalled());
      expect(vi.mocked(paymentsApi.createPayment).mock.calls[0][3]).toMatchObject({ amount_net: '100', vat_rate: '23', note: 'Do 14 dni' });
    });

    it('refuses a VAT above 100 and a malformed net amount', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      fireEvent.click(screen.getByLabelText('payment-more'));
      type('payment-title', 'Etap 2');
      type('payment-amount', '123');
      type('payment-net', '1,234');
      type('payment-vat', '101');
      fireEvent.click(screen.getByLabelText('payment-save'));
      const alerts = (await screen.findAllByRole('alert')).map((node) => node.textContent);
      expect(alerts).toEqual([expect.stringContaining('Kwota netto'), expect.stringContaining('VAT')]);
      expect(paymentsApi.createPayment).not.toHaveBeenCalled();
    });
  });

  describe('money from the client', () => {
    it('is an advance by default and a payment when chosen; it can be tied to an invoice under "Opcje"', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payments-tab-client'));
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect(screen.getByLabelText('payment-kind-ADVANCE')).toHaveAttribute('aria-pressed', 'true');
      expect(screen.queryByLabelText('payment-due')).toBeNull();
      expect(screen.queryByLabelText('payment-counterparty')).toBeNull();
      fireEvent.click(screen.getByLabelText('payment-kind-PAYMENT'));
      expect(screen.getByLabelText('payment-kind-PAYMENT')).toHaveAttribute('aria-pressed', 'true');

      fireEvent.click(screen.getByLabelText('payment-more'));
      const select = screen.getByLabelText('payment-settles') as HTMLSelectElement;
      expect(Array.from(select.options).map((option) => option.textContent)).toEqual([
        'Bez faktury', 'FV 1/2026 · Faktura za etap 1 · 1000,00 zł · 01.10.2026',
      ]);
      type('payment-title', 'Płatność za etap 1');
      type('payment-amount', '600');
      fireEvent.change(select, { target: { value: 'inv1' } });
      fireEvent.click(screen.getByLabelText('payment-save'));
      await waitFor(() => expect(paymentsApi.createPayment).toHaveBeenCalled());
      const [, , kind, fields] = vi.mocked(paymentsApi.createPayment).mock.calls[0];
      expect(kind).toBe('PAYMENT');
      expect(fields).toMatchObject({ settles_id: 'inv1', due_on: null, counterparty: null, document_kind: null, amount_net: null, vat_rate: null });
    });

    it('lists no archived invoice among those a payment can be tied to', async () => {
      vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(listOf([INVOICE, base({ id: 'inv2', title: 'Stara', is_archived: true })]));
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payments-tab-client'));
      fireEvent.click(screen.getByLabelText('payment-add'));
      fireEvent.click(screen.getByLabelText('payment-more'));
      const select = screen.getByLabelText('payment-settles') as HTMLSelectElement;
      expect(select.options).toHaveLength(2);
    });
  });

  describe('expenses on materials', () => {
    it('asks where it was bought and whether it is a receipt or an invoice (a receipt by default)', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payments-tab-materials'));
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect(screen.getByLabelText('payment-document-RECEIPT')).toHaveAttribute('aria-pressed', 'true');
      expect(screen.queryByLabelText('payment-due')).toBeNull();
      expect(screen.queryByLabelText('payment-number')).toBeNull();

      fireEvent.click(screen.getByLabelText('payment-hint_material_2'));
      type('payment-counterparty', 'Castorama');
      type('payment-amount', '89,99');
      fireEvent.click(screen.getByLabelText('payment-document-INVOICE'));
      fireEvent.click(screen.getByLabelText('payment-more'));
      type('payment-number', 'FV/55');
      fireEvent.click(screen.getByLabelText('payment-save'));
      await waitFor(() => expect(paymentsApi.createPayment).toHaveBeenCalled());
      const [, , kind, fields] = vi.mocked(paymentsApi.createPayment).mock.calls[0];
      expect(kind).toBe('EXPENSE');
      expect(fields).toMatchObject({
        title: 'Farba', counterparty: 'Castorama', document_kind: 'INVOICE', number: 'FV/55', amount_gross: '89.99', due_on: null, settles_id: null,
      });
    });
  });

  describe('the category of an expense (IA-6b)', () => {
    const TOOLS_EXPENSE = base({
      id: 'exp2', kind: 'EXPENSE', title: 'Wiertarka', amount_gross: '300.00', counterparty: null, document_kind: 'RECEIPT', category: 'TOOLS', occurred_on: '2026-10-04',
    });
    const summaryWith = (parts: { category: PaymentCategory | null; total: string }[]) => ({
      ...listOf([]).summary, expenses: '550.50', expenses_by_category: parts,
    });

    it('offers the five categories on a new expense with materials chosen, and sends the one that is chosen', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payments-tab-materials'));
      fireEvent.click(screen.getByLabelText('payment-add'));
      for (const name of ['MATERIALS', 'TOOLS', 'TRANSPORT', 'SERVICES', 'OTHER']) expect(screen.getByLabelText(`payment-category-${name}`)).toBeInTheDocument();
      expect(screen.getByLabelText('payment-category-MATERIALS')).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByLabelText('payment-category-TOOLS')).toHaveAttribute('aria-pressed', 'false');
      fireEvent.click(screen.getByLabelText('payment-category-TRANSPORT'));
      expect(screen.getByLabelText('payment-category-TRANSPORT')).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByLabelText('payment-category-MATERIALS')).toHaveAttribute('aria-pressed', 'false');
      type('payment-title', 'Dostawa');
      type('payment-amount', '80');
      fireEvent.click(screen.getByLabelText('payment-save'));
      await waitFor(() => expect(paymentsApi.createPayment).toHaveBeenCalled());
      expect(vi.mocked(paymentsApi.createPayment).mock.calls[0][3]).toMatchObject({ category: 'TRANSPORT' });
    });

    it('sends materials when nothing was tapped, and no category on an invoice or on money from the client', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payments-tab-materials'));
      fireEvent.click(screen.getByLabelText('payment-add'));
      type('payment-title', 'Farba');
      type('payment-amount', '10');
      fireEvent.click(screen.getByLabelText('payment-save'));
      await waitFor(() => expect(paymentsApi.createPayment).toHaveBeenCalledTimes(1));
      expect(vi.mocked(paymentsApi.createPayment).mock.calls[0][3]).toMatchObject({ category: 'MATERIALS' });

      fireEvent.click(await screen.findByLabelText('payments-tab-invoices'));
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect(screen.queryByLabelText('payment-category')).toBeNull();
      type('payment-title', 'Faktura');
      type('payment-amount', '10');
      fireEvent.click(screen.getByLabelText('payment-save'));
      await waitFor(() => expect(paymentsApi.createPayment).toHaveBeenCalledTimes(2));
      expect(vi.mocked(paymentsApi.createPayment).mock.calls[1][3]).toMatchObject({ category: null });
    });

    it('opens an expense with its own category, and an old expense with none keeps none until one is tapped', async () => {
      vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(listOf([EXPENSE, TOOLS_EXPENSE]));
      renderScreen();
      await screen.findByLabelText('payments-tabs');
      fireEvent.click(screen.getByLabelText('payments-tab-materials'));
      fireEvent.click(screen.getByLabelText('payment-edit-exp2'));
      expect(screen.getByLabelText('payment-category-TOOLS')).toHaveAttribute('aria-pressed', 'true');
      fireEvent.click(screen.getByLabelText('payment-cancel'));

      fireEvent.click(screen.getByLabelText('payment-edit-exp1'));
      for (const name of ['MATERIALS', 'TOOLS', 'TRANSPORT', 'SERVICES', 'OTHER']) expect(screen.getByLabelText(`payment-category-${name}`)).toHaveAttribute('aria-pressed', 'false');
      fireEvent.click(screen.getByLabelText('payment-save'));
      await waitFor(() => expect(paymentsApi.updatePayment).toHaveBeenCalledTimes(1));
      expect(vi.mocked(paymentsApi.updatePayment).mock.calls[0][2]).toMatchObject({ category: null });
    });

    it('names the category on the card of an expense and says nothing for one that has none', async () => {
      vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(listOf([EXPENSE, TOOLS_EXPENSE]));
      renderScreen();
      await screen.findByLabelText('payments-tabs');
      fireEvent.click(screen.getByLabelText('payments-tab-materials'));
      expect(within(screen.getByLabelText('payment-exp2')).getByText(/Narzędzia/)).toBeInTheDocument();
      expect(within(screen.getByLabelText('payment-exp1')).queryByText(/Narzędzia|Materiały|Transport|Usługi|Inne/)).toBeNull();
    });

    it('shows the parts the server sent under the expenses, in its order and with its sums, and adds nothing', async () => {
      vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(listOf([EXPENSE, TOOLS_EXPENSE], {
        summary: summaryWith([{ category: 'MATERIALS', total: '1.00' }, { category: 'TOOLS', total: '300.00' }, { category: null, total: '5.50' }]),
      }));
      renderScreen();
      await screen.findByLabelText('payments-summary');
      const parts = screen.getByLabelText('summary-expenses-parts');
      expect(within(parts).getAllByRole('definition').map((node) => node.textContent?.replace(/\s/g, ' '))).toEqual([formatMoney('1.00'), formatMoney('300.00'), formatMoney('5.50')].map((value) => value.replace(/\s/g, ' ')));
      expect(within(screen.getByLabelText('summary-expenses-MATERIALS')).getByText('Materiały')).toBeInTheDocument();
      expect(within(screen.getByLabelText('summary-expenses-none')).getByText('Bez kategorii')).toBeInTheDocument();
    });

    it('shows no breakdown when no expense has a category, when there is no expense, or when the list was kept from before the categories', async () => {
      for (const summary of [summaryWith([{ category: null, total: '250.50' }]), summaryWith([]), listOf([]).summary]) {
        vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(listOf([EXPENSE], { summary }));
        const view = renderScreen();
        await screen.findByLabelText('payments-summary');
        expect(screen.queryByLabelText('summary-expenses-parts')).toBeNull();
        view.unmount();
      }
    });

    it('shows the categories in Russian', async () => {
      localStorage.setItem('locale', 'ru');
      vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(listOf([TOOLS_EXPENSE], { summary: summaryWith([{ category: 'TOOLS', total: '300.00' }, { category: null, total: '1.00' }]) }));
      renderScreen();
      await screen.findByLabelText('payments-summary');
      expect(within(screen.getByLabelText('summary-expenses-TOOLS')).getByText('Инструмент')).toBeInTheDocument();
      expect(within(screen.getByLabelText('summary-expenses-none')).getByText('Без категории')).toBeInTheDocument();
      fireEvent.click(screen.getByLabelText('payments-tab-materials'));
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect(screen.getByLabelText('payment-category-MATERIALS')).toHaveTextContent('Материалы');
    });
  });

  describe('changing, archiving and restoring', () => {
    it('opens a record filled in, shows no choice of kind, and sends the whole form to the change', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payments-tab-client'));
      fireEvent.click(screen.getByLabelText('payment-edit-adv1'));
      expect(screen.queryByLabelText('payment-kind')).toBeNull();
      expect((screen.getByLabelText('payment-title') as HTMLInputElement).value).toBe('Zaliczka na materiały');
      expect((screen.getByLabelText('payment-amount') as HTMLInputElement).value).toBe('400,00');
      expect((screen.getByLabelText('payment-day') as HTMLInputElement).value).toBe('2026-09-28');
      // a record with a tied invoice shows its "Opcje" open
      expect((screen.getByLabelText('payment-settles') as HTMLSelectElement).value).toBe('inv1');
      type('payment-amount', '450');
      fireEvent.click(screen.getByLabelText('payment-save'));
      await waitFor(() => expect(paymentsApi.updatePayment).toHaveBeenCalledTimes(1));
      const [project, id, fields] = vi.mocked(paymentsApi.updatePayment).mock.calls[0];
      expect([project, id]).toEqual([projectId, 'adv1']);
      expect(fields).toMatchObject({ title: 'Zaliczka na materiały', amount_gross: '450', settles_id: 'inv1' });
      expect(paymentsApi.createPayment).not.toHaveBeenCalled();
      await waitFor(() => expect(screen.queryByLabelText('payment-form')).toBeNull());
    });

    it('archives a record and shows the list again; nothing is erased', async () => {
      vi.mocked(paymentsApi.archivePayment).mockResolvedValue({ ...INVOICE, is_archived: true });
      renderScreen();
      await screen.findByLabelText('payments-list');
      expect(screen.getByLabelText('payment-archive-inv1')).toHaveTextContent('Archiwizuj');
      fireEvent.click(screen.getByLabelText('payment-archive-inv1'));
      await waitFor(() => expect(paymentsApi.archivePayment).toHaveBeenCalledWith(projectId, 'inv1'));
      expect(await screen.findByRole('status')).toHaveTextContent('Wpis zarchiwizowany.');
      expect(paymentsApi.fetchPayments).toHaveBeenCalledTimes(2);
    });

    it('asks the server for the archived ones too when asked, marks them, and restores one', async () => {
      const archived = { ...INVOICE, is_archived: true };
      vi.mocked(paymentsApi.fetchPayments).mockImplementation(async (_p, includeArchived) => listOf(includeArchived ? [archived] : []));
      vi.mocked(paymentsApi.restorePayment).mockResolvedValue(INVOICE);
      renderScreen();
      expect(await screen.findByLabelText('payments-empty')).toBeInTheDocument();
      fireEvent.click(screen.getByLabelText('payments-show-archived'));
      await waitFor(() => expect(paymentsApi.fetchPayments).toHaveBeenLastCalledWith(projectId, true));
      const card = await screen.findByLabelText('payment-inv1');
      expect(card).toHaveTextContent('Zarchiwizowany');
      expect(screen.queryByLabelText('payment-state-inv1')).toBeNull();
      expect(screen.getByLabelText('payment-archive-inv1')).toHaveTextContent('Przywróć');
      fireEvent.click(screen.getByLabelText('payment-archive-inv1'));
      await waitFor(() => expect(paymentsApi.restorePayment).toHaveBeenCalledWith(projectId, 'inv1'));
      expect(await screen.findByRole('status')).toHaveTextContent('Wpis przywrócony.');
    });

    it('says so when archiving fails and leaves the list as it was', async () => {
      vi.mocked(paymentsApi.archivePayment).mockRejectedValue(new ApiError('Request failed (500)', 500));
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-archive-inv1'));
      expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zmienić wpisu.');
      expect(screen.getByLabelText('payment-inv1')).toBeInTheDocument();
    });
  });

  describe('loading', () => {
    it('shows the loading text first and then the screen', async () => {
      renderScreen();
      expect(screen.getByText('Ładowanie rozliczeń…')).toBeInTheDocument();
      expect(await screen.findByLabelText('payments-summary')).toBeInTheDocument();
      expect(screen.queryByText('Ładowanie rozliczeń…')).toBeNull();
    });

    it('offers to try again when the list cannot be read, and shows the screen after a good try', async () => {
      vi.mocked(paymentsApi.fetchPayments).mockRejectedValueOnce(new Error('offline'));
      renderScreen();
      expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać rozliczeń.');
      expect(screen.queryByLabelText('payments-summary')).toBeNull();
      fireEvent.click(screen.getByLabelText('payments-retry'));
      expect(await screen.findByLabelText('payments-summary')).toBeInTheDocument();
      expect(screen.queryByRole('alert')).toBeNull();
    });
  });

  describe('Russian', () => {
    beforeEach(() => localStorage.setItem('locale', 'ru'));

    it('shows the tabs, the summary and the form in Russian', async () => {
      renderScreen();
      expect(await screen.findByLabelText('payments-tab-invoices')).toHaveTextContent('Фактуры');
      expect(screen.getByLabelText('payments-tab-client')).toHaveTextContent('От клиента');
      expect(screen.getByLabelText('payments-tab-materials')).toHaveTextContent('Материалы');
      expect(screen.getByLabelText('summary-to_receive')).toHaveTextContent('Осталось получить');
      expect(screen.getByLabelText('payment-state-inv1')).toHaveTextContent('Частично');
      expect(screen.getByLabelText('payments-disclaimer')).toHaveTextContent('Это не фактура');
      fireEvent.click(screen.getByLabelText('payment-add'));
      expect(screen.getByLabelText('payment-form')).toHaveTextContent('За что');
      fireEvent.click(screen.getByLabelText('payment-save'));
      expect(await screen.findAllByRole('alert')).toHaveLength(2);
      expect(screen.getAllByRole('alert')[0]).toHaveTextContent('Укажите, за что.');
    });
  });

  describe('the touch targets', () => {
    it('gives every button, the tabs and the inputs of the form at least 44 px of height', async () => {
      renderScreen();
      await screen.findByLabelText('payments-list');
      fireEvent.click(screen.getByLabelText('payment-add'));
      fireEvent.click(screen.getByLabelText('payment-more'));
      const form = screen.getByLabelText('payment-form');
      const controls = [
        ...Array.from(form.querySelectorAll('button')),
        ...Array.from(form.querySelectorAll('input:not([type=hidden]), select')),
        ...Array.from(screen.getByLabelText('payments-tabs').querySelectorAll('button')),
        screen.getByLabelText('agreed-edit'),
        screen.getByLabelText('payment-edit-inv1'),
        screen.getByLabelText('payment-archive-inv1'),
      ];
      for (const control of controls) expect(control.className, control.getAttribute('aria-label') ?? '').toMatch(/min-h-11|min-h-24/);
    });
  });
});

describe('the formatting of settlements', () => {
  it('prints a sum with two places and a comma, and a day as day.month.year without a time zone', () => {
    expect(formatMoney('40000.00')).toBe('40000,00 zł');
    expect(formatMoney('-9.99')).toBe('-9,99 zł');
    expect(formatMoney(null)).toBe('—');
    expect(formatDay('2026-10-01')).toBe('01.10.2026');
    expect(formatDay('2026-12-31T23:30:00Z')).toBe('31.12.2026');
    expect(formatDay(null)).toBe('—');
  });

  it('takes today in Warsaw, not in the zone of the machine', () => {
    expect(todayInPoland(new Date('2026-06-30T22:30:00Z'))).toBe('2026-07-01');
    expect(todayInPoland(new Date('2026-12-31T22:30:00Z'))).toBe('2026-12-31');
    expect(todayInPoland(new Date('2026-12-31T23:30:00Z'))).toBe('2027-01-01');
  });

  it('accepts a positive amount only, with at most two places', () => {
    expect(positiveAmount('12,5')).toBe('12.5');
    expect(positiveAmount(' 100 ')).toBe('100');
    for (const bad of ['', '0', '0,00', '-1', '1,234', 'abc', '1.2.3']) expect(positiveAmount(bad)).toBeNull();
  });

  it('accepts a rate from 0 to 100 and an empty one', () => {
    expect(optionalRate('')).toBe('');
    expect(optionalRate('23')).toBe('23');
    expect(optionalRate('0')).toBe('0');
    expect(optionalRate('100')).toBe('100');
    expect(optionalRate('100,01')).toBeNull();
    expect(optionalRate('x')).toBeNull();
  });
});
