import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as paymentsApi from './api/payments';
import * as moneyApi from './api/paymentSchedule';
import { ApiError } from './api/http';
import { ProjectPayments } from './components/ProjectPayments';
import { I18nProvider } from './hooks/useI18n';
import { reportNetworkFailure, resetConnectionForTests } from './offline/connection';
import type { Payment, PaymentList } from './types/payment';
import type { Margin, PaymentStage, Schedule, WorkHours } from './types/paymentSchedule';
import { todayInPoland } from './utils/paymentFormat';

vi.mock('./api/payments', () => ({
  fetchPayments: vi.fn(),
  createPayment: vi.fn(),
  updatePayment: vi.fn(),
  archivePayment: vi.fn(),
  restorePayment: vi.fn(),
  fetchFinance: vi.fn(),
  saveAgreedAmount: vi.fn(),
}));
vi.mock('./api/paymentSchedule', () => ({
  fetchSchedule: vi.fn(),
  createStage: vi.fn(),
  updateStage: vi.fn(),
  deleteStage: vi.fn(),
  receiveStage: vi.fn(),
  fetchHours: vi.fn(),
  createHours: vi.fn(),
  updateHours: vi.fn(),
  deleteHours: vi.fn(),
  fetchMargin: vi.fn(),
}));

// V2-9 — the screen "Faktury i zaliczki" with the schedule of the stages, the work hours and the margin: the screen shows what the server sent and counts nothing.

const projectId = '11111111-1111-1111-1111-111111111111';
const stage = (over: Partial<PaymentStage>): PaymentStage => ({
  id: 's1', project_id: projectId, title: 'Zaliczka', percent: '30.00', amount_fixed: null, due_on: '2026-11-05', amount: '12000.00', received: '5000.00', remaining: '7000.00',
  state: 'PARTIAL', created_at: '2026-10-28T10:00:00Z', updated_at: '2026-10-28T10:00:00Z', ...over,
});
const PARTIAL = stage({});
const PAID = stage({ id: 's2', title: 'Po gładziach', percent: null, amount_fixed: '5000.00', amount: '5000.00', received: '5000.00', remaining: '0.00', state: 'PAID', due_on: null });
const WAITING = stage({ id: 's3', title: 'Odbiór', amount: null, remaining: null, received: '0.00', state: 'OPEN', due_on: null, percent: '20.00' });
const SCHEDULE = (items: PaymentStage[], over: Partial<Schedule['summary']> = {}): Schedule => ({
  items,
  summary: { agreed: '40000.00', stages_total: '17000.00', unpriced: 0, difference: '23000.00', received: '10000.00', to_receive: '7000.00', ...over },
});
const MARGIN: Margin = {
  basis: '40000.00', basis_source: 'AGREED', expenses: '12000.50', hours: '120.00', hourly_rate: '100.00', labor_cost: '12000.00', labor_included: true,
  margin: '15999.50', percent: '40.00', per_hour: '233.33',
};
const HOURS: WorkHours = {
  items: [
    { id: 'h1', project_id: projectId, worked_on: '2026-10-27', hours: '7.50', note: 'gładź salon', created_at: '2026-10-27T10:00:00Z', updated_at: '2026-10-27T10:00:00Z' },
    { id: 'h2', project_id: projectId, worked_on: '2026-10-26', hours: '4.00', note: null, created_at: '2026-10-26T10:00:00Z', updated_at: '2026-10-26T10:00:00Z' },
  ],
  total_hours: '11.50',
  hourly_rate: null,
};
const payment: Payment = {
  id: 'p1', project_id: projectId, kind: 'ADVANCE', title: 'Zaliczka', number: null, amount_gross: '5000.00', amount_net: null, vat_rate: null, occurred_on: '2026-10-20', due_on: null,
  settles_id: null, stage_id: 's1', counterparty: null, document_kind: null, note: null, is_archived: false, created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-20T10:00:00Z',
  settled: null, remaining: null, state: null,
};
const LIST: PaymentList = {
  items: [payment],
  total: 1,
  summary: { invoiced: '0.00', received: '5000.00', expenses: '12000.50', invoiced_unpaid: '0.00', to_receive: '35000.00', result: '-7000.50' },
  agreed_amount: '40000.00',
};

function renderScreen() {
  return render(<I18nProvider><ProjectPayments projectId={projectId} /></I18nProvider>);
}
const tab = async (id: string) => {
  await screen.findByLabelText('payments-tabs');
  fireEvent.click(screen.getByLabelText(`payments-tab-${id}`));
};
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  resetConnectionForTests();
  vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(LIST);
  vi.mocked(paymentsApi.fetchFinance).mockResolvedValue({ agreed_amount: '40000.00', currency: 'PLN', suggestion: null });
  vi.mocked(moneyApi.fetchSchedule).mockResolvedValue(SCHEDULE([PARTIAL, PAID]));
  vi.mocked(moneyApi.fetchMargin).mockResolvedValue(MARGIN);
  vi.mocked(moneyApi.fetchHours).mockResolvedValue(HOURS);
});
afterEach(cleanup);

describe('the tabs', () => {
  it('has five tabs, touch-sized, and opens the schedule and the hours without touching the records', async () => {
    renderScreen();
    const tabs = await screen.findByLabelText('payments-tabs');
    const buttons = within(tabs).getAllByRole('tab');
    expect(buttons.map((b) => b.textContent)).toEqual(['Faktury', 'Od klienta', 'Materiały', 'Etapy', 'Godziny']);
    buttons.forEach((b) => expect(b.className).toContain('min-h-11'));
    fireEvent.click(screen.getByLabelText('payments-tab-schedule'));
    expect(await screen.findByLabelText('schedule-tab')).toBeInTheDocument();
    expect(screen.queryByLabelText('payment-add')).toBeNull();
    expect(screen.queryByLabelText('payments-list')).toBeNull();
    expect(screen.queryByLabelText('payments-show-archived')).toBeNull();
    fireEvent.click(screen.getByLabelText('payments-tab-hours'));
    expect(await screen.findByLabelText('hours-tab')).toBeInTheDocument();
    expect(screen.queryByLabelText('schedule-tab')).toBeNull();
    fireEvent.click(screen.getByLabelText('payments-tab-client'));
    expect(await screen.findByLabelText('payments-list')).toBeInTheDocument();
  });
});

describe('the margin', () => {
  it('shows the numbers the server counted and no sum of its own', async () => {
    renderScreen();
    const card = await screen.findByLabelText('margin-card');
    expect(within(card).getByLabelText('margin-basis')).toHaveTextContent('Podstawa: umówiona kwota40000,00 zł');
    expect(within(card).getByLabelText('margin-expenses')).toHaveTextContent('12000,50 zł');
    expect(within(card).getByLabelText('margin-hours')).toHaveTextContent('120 h');
    expect(within(card).getByLabelText('margin-labor')).toHaveTextContent('12000,00 zł');
    expect(within(card).getByLabelText('margin-margin')).toHaveTextContent('Marża15999,50 zł');
    expect(within(card).getByLabelText('margin-percent')).toHaveTextContent('40%');
    expect(within(card).getByLabelText('margin-per_hour')).toHaveTextContent('233,33 zł / h');
    expect(within(card).queryByLabelText('margin-rate-hint')).toBeNull();
    expect(card).toHaveTextContent('bez rozliczenia VAT');
  });

  it('is before the cost of work and asks for the rate when there is none, and shows a loss in red', async () => {
    vi.mocked(moneyApi.fetchMargin).mockResolvedValue({ ...MARGIN, basis_source: 'ESTIMATE', hourly_rate: null, labor_cost: null, labor_included: false, margin: '-300.00', percent: '-3.00' });
    renderScreen();
    const card = await screen.findByLabelText('margin-card');
    expect(within(card).getByLabelText('margin-basis')).toHaveTextContent('Podstawa: kosztorys (brak umówionej kwoty)');
    expect(within(card).getByLabelText('margin-labor')).toHaveTextContent('brak stawki');
    const row = within(card).getByLabelText('margin-margin');
    expect(row).toHaveTextContent('Marża przed kosztem pracy-300,00 zł');
    expect(row.querySelector('dd')?.className).toContain('text-red-600');
    expect(within(card).getByLabelText('margin-percent')).toHaveTextContent('-3%');
    expect(within(card).getByLabelText('margin-rate-hint')).toHaveTextContent('profilu wykonawcy');
  });

  it('says what is missing when there is nothing to count from', async () => {
    vi.mocked(moneyApi.fetchMargin).mockResolvedValue({ ...MARGIN, basis: null, basis_source: null, margin: null, percent: null, per_hour: null, labor_cost: null, labor_included: false });
    renderScreen();
    const card = await screen.findByLabelText('margin-card');
    expect(within(card).getByLabelText('margin-no-basis')).toHaveTextContent('Ustaw umówioną kwotę albo przygotuj kosztorys');
    expect(within(card).queryByLabelText('margin-margin')).toBeNull();
  });

  it('shows nothing when it cannot be read and never blocks the records', async () => {
    vi.mocked(moneyApi.fetchMargin).mockRejectedValue(new Error('down'));
    renderScreen();
    expect(await screen.findByLabelText('payments-summary')).toBeInTheDocument();
    await waitFor(() => expect(moneyApi.fetchMargin).toHaveBeenCalled());
    expect(screen.queryByLabelText('margin-card')).toBeNull();
  });

  it('is read again after the money changed', async () => {
    renderScreen();
    await screen.findByLabelText('margin-card');
    expect(moneyApi.fetchMargin).toHaveBeenCalledTimes(1);
    vi.mocked(moneyApi.receiveStage).mockResolvedValue(payment);
    await tab('schedule');
    fireEvent.click(await screen.findByLabelText('stage-receive-s1'));
    await waitFor(() => expect(moneyApi.fetchMargin).toHaveBeenCalledTimes(2));
  });
});

describe('the schedule', () => {
  it('lists the stages with the amount, the share, the day, what was received and the state of the server', async () => {
    vi.mocked(moneyApi.fetchSchedule).mockResolvedValue(SCHEDULE([PARTIAL, PAID, WAITING], { unpriced: 1, difference: '-1500.00' }));
    renderScreen();
    await tab('schedule');
    const summary = await screen.findByLabelText('schedule-summary');
    expect(within(summary).getByLabelText('schedule-summary-total')).toHaveTextContent('17000,00 zł');
    expect(within(summary).getByLabelText('schedule-difference')).toHaveTextContent('Etapy przekraczają umówioną kwotę o 1500,00 zł');
    expect(within(summary).getByLabelText('schedule-unpriced')).toHaveTextContent('Etapy czekające na umówioną kwotę: 1');
    const first = screen.getByLabelText('stage-s1');
    expect(within(first).getByLabelText('stage-amount-s1')).toHaveTextContent('12000,00 zł');
    expect(first).toHaveTextContent('30% umówionej kwoty');
    expect(first).toHaveTextContent('Termin: 05.11.2026');
    expect(within(first).getByLabelText('stage-received-s1')).toHaveTextContent('Otrzymano: 5000,00 zł · Pozostało: 7000,00 zł');
    expect(within(first).getByLabelText('stage-state-s1')).toHaveTextContent('Częściowo');
    expect(within(screen.getByLabelText('stage-s2')).getByLabelText('stage-state-s2')).toHaveTextContent('Zapłacony');
    expect(screen.getByLabelText('stage-waits-s3')).toHaveTextContent('Udział czeka na umówioną kwotę.');
  });

  it('says the stages cover the agreed amount, or what is not scheduled yet', async () => {
    vi.mocked(moneyApi.fetchSchedule).mockResolvedValue(SCHEDULE([PARTIAL], { difference: '0.00' }));
    renderScreen();
    await tab('schedule');
    expect(await screen.findByLabelText('schedule-difference')).toHaveTextContent('Etapy pokrywają umówioną kwotę.');
    cleanup();
    vi.mocked(moneyApi.fetchSchedule).mockResolvedValue(SCHEDULE([PARTIAL], { difference: '23000.00' }));
    renderScreen();
    await tab('schedule');
    expect(await screen.findByLabelText('schedule-difference')).toHaveTextContent('Nie rozplanowano: 23000,00 zł');
  });

  it('offers "Otrzymano" only for a stage with something left, and books it in one tap', async () => {
    vi.mocked(moneyApi.receiveStage).mockResolvedValue(payment);
    renderScreen();
    await tab('schedule');
    expect(await screen.findByLabelText('stage-receive-s1')).toBeInTheDocument();
    expect(screen.queryByLabelText('stage-receive-s2')).toBeNull(); // paid
    const button = screen.getByLabelText('stage-receive-s1');
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('w-full');
    fireEvent.click(button);
    await waitFor(() => expect(moneyApi.receiveStage).toHaveBeenCalledWith(projectId, 's1'));
    expect(await screen.findByRole('status')).toHaveTextContent('Wpłata na resztę etapu zapisana.');
    expect(vi.mocked(moneyApi.fetchSchedule).mock.calls.length).toBeGreaterThanOrEqual(2); // read again
    expect(paymentsApi.fetchPayments).toHaveBeenCalledTimes(2); // the records and their totals too
  });

  it('answers a refused receipt with the words of its code', async () => {
    vi.mocked(moneyApi.receiveStage).mockRejectedValue(new ApiError('Request failed', 422, 'STAGE_NOTHING_LEFT', { code: 'STAGE_NOTHING_LEFT' }));
    renderScreen();
    await tab('schedule');
    fireEvent.click(await screen.findByLabelText('stage-receive-s1'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Ten etap jest już w całości opłacony.');
  });

  it('adds a stage as a share: the comma, the hint, the day, and nothing is sent when it is wrong', async () => {
    vi.mocked(moneyApi.createStage).mockResolvedValue(PARTIAL);
    renderScreen();
    await tab('schedule');
    fireEvent.click(await screen.findByLabelText('stage-add'));
    expect(screen.getByLabelText('stage-value')).toHaveAttribute('inputmode', 'decimal');
    fireEvent.click(screen.getByLabelText('stage-save'));
    expect((await screen.findAllByRole('alert')).map((n) => n.textContent)).toEqual(['Wpisz nazwę etapu.', expect.stringContaining('Wpisz udział (od 0,01 do 100)')]);
    for (const bad of ['0', '100,5', '101', 'x', '12,345']) {
      type('stage-value', bad);
      fireEvent.click(screen.getByLabelText('stage-save'));
      expect(await screen.findByText(/Wpisz udział/)).toBeInTheDocument();
    }
    expect(moneyApi.createStage).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('stage-hint_2'));
    expect((screen.getByLabelText('stage-title') as HTMLInputElement).value).toBe('Po gładziach');
    type('stage-value', '33,5');
    type('stage-due', '2026-12-01');
    fireEvent.click(screen.getByLabelText('stage-save'));
    await waitFor(() => expect(moneyApi.createStage).toHaveBeenCalledWith(projectId, { title: 'Po gładziach', percent: '33.5', due_on: '2026-12-01' }));
    await waitFor(() => expect(screen.queryByLabelText('stage-form')).toBeNull());
    expect(screen.getByRole('status')).toHaveTextContent('Etap zapisany.');
  });

  it('adds a stage as a fixed amount with no day', async () => {
    vi.mocked(moneyApi.createStage).mockResolvedValue(PAID);
    renderScreen();
    await tab('schedule');
    fireEvent.click(await screen.findByLabelText('stage-add'));
    type('stage-title', '  Odbiór  ');
    fireEvent.click(screen.getByLabelText('stage-mode-amount'));
    type('stage-value', '5 000'.replace(' ', ''));
    fireEvent.click(screen.getByLabelText('stage-save'));
    await waitFor(() => expect(moneyApi.createStage).toHaveBeenCalledWith(projectId, { title: 'Odbiór', amount: '5000', due_on: null }));
  });

  it('changes a stage: the form opens with its values and a switch of the kind sends the other field', async () => {
    vi.mocked(moneyApi.updateStage).mockResolvedValue(PARTIAL);
    renderScreen();
    await tab('schedule');
    fireEvent.click(await screen.findByLabelText('stage-edit-s1'));
    expect((screen.getByLabelText('stage-title') as HTMLInputElement).value).toBe('Zaliczka');
    expect((screen.getByLabelText('stage-value') as HTMLInputElement).value).toBe('30,00');
    expect((screen.getByLabelText('stage-due') as HTMLInputElement).value).toBe('2026-11-05');
    fireEvent.click(screen.getByLabelText('stage-mode-amount'));
    type('stage-value', '1500');
    type('stage-due', '');
    fireEvent.click(screen.getByLabelText('stage-save'));
    await waitFor(() => expect(moneyApi.updateStage).toHaveBeenCalledWith(projectId, 's1', { title: 'Zaliczka', amount: '1500', due_on: null }));
  });

  it('deletes a stage only after a second tap, and says the money stays', async () => {
    vi.mocked(moneyApi.deleteStage).mockResolvedValue(undefined);
    renderScreen();
    await tab('schedule');
    fireEvent.click(await screen.findByLabelText('stage-delete-s1'));
    expect(moneyApi.deleteStage).not.toHaveBeenCalled();
    expect(screen.getByLabelText('stage-confirm-s1')).toHaveTextContent('Wpłaty zostaną, bez etapu.');
    fireEvent.click(screen.getByLabelText('stage-delete-no-s1'));
    expect(screen.queryByLabelText('stage-confirm-s1')).toBeNull();
    fireEvent.click(screen.getByLabelText('stage-delete-s1'));
    fireEvent.click(screen.getByLabelText('stage-delete-yes-s1'));
    await waitFor(() => expect(moneyApi.deleteStage).toHaveBeenCalledWith(projectId, 's1'));
    expect(await screen.findByRole('status')).toHaveTextContent('Etap usunięty.');
  });

  it('is empty with a hint, and offers a retry when it cannot be read', async () => {
    vi.mocked(moneyApi.fetchSchedule).mockResolvedValueOnce(SCHEDULE([], { agreed: null, difference: null, to_receive: '0.00' })); // the form's own read
    vi.mocked(moneyApi.fetchSchedule).mockResolvedValueOnce(SCHEDULE([], { agreed: null, difference: null, to_receive: '0.00' }));
    renderScreen();
    await tab('schedule');
    expect(await screen.findByLabelText('schedule-empty')).toHaveTextContent('Brak etapów.');
    expect(screen.getByLabelText('schedule-summary-agreed')).toHaveTextContent('nie ustawiono');
    cleanup();
    vi.mocked(moneyApi.fetchSchedule).mockRejectedValue(new Error('down'));
    renderScreen();
    await tab('schedule');
    expect(await screen.findByLabelText('schedule-retry')).toBeInTheDocument();
    vi.mocked(moneyApi.fetchSchedule).mockResolvedValue(SCHEDULE([PARTIAL]));
    fireEvent.click(screen.getByLabelText('schedule-retry'));
    expect(await screen.findByLabelText('stage-s1')).toBeInTheDocument();
  });

  it('cannot be changed without the connection', async () => {
    renderScreen();
    await tab('schedule');
    await screen.findByLabelText('stage-s1');
    reportNetworkFailure();
    await waitFor(() => expect(screen.getByLabelText('stage-add')).toBeDisabled());
    expect(screen.getByLabelText('stage-edit-s1')).toBeDisabled();
    expect(screen.getByLabelText('stage-receive-s1')).toBeDisabled();
    expect(screen.getByLabelText('stage-delete-s1')).toBeDisabled();
    expect(screen.getByLabelText('schedule-offline')).toHaveTextContent('Harmonogram zmienisz, gdy wróci zasięg.');
  });
});

describe('the stage of a payment', () => {
  it('is chosen under "Opcje" of an advance or a payment and goes with it', async () => {
    vi.mocked(paymentsApi.createPayment).mockResolvedValue(payment);
    renderScreen();
    await tab('client');
    fireEvent.click(await screen.findByLabelText('payment-add'));
    type('payment-title', 'Zaliczka');
    type('payment-amount', '500');
    expect(screen.queryByLabelText('payment-stage')).toBeNull(); // a rare field: under "Opcje"
    fireEvent.click(screen.getByLabelText('payment-more'));
    const select = screen.getByLabelText('payment-stage') as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(['Bez etapu', 'Zaliczka · 12000,00 zł', 'Po gładziach · 5000,00 zł']);
    fireEvent.change(select, { target: { value: 's1' } });
    fireEvent.click(screen.getByLabelText('payment-save'));
    await waitFor(() => expect(paymentsApi.createPayment).toHaveBeenCalledTimes(1));
    expect(vi.mocked(paymentsApi.createPayment).mock.calls[0][3]).toMatchObject({ stage_id: 's1', title: 'Zaliczka', amount_gross: '500' });
  });

  it('is not offered for an invoice or an expense, nor when there is no schedule', async () => {
    renderScreen();
    await screen.findByLabelText('payments-tabs');
    fireEvent.click(screen.getByLabelText('payment-add'));
    fireEvent.click(screen.getByLabelText('payment-more'));
    expect(screen.queryByLabelText('payment-stage')).toBeNull(); // the invoices tab
    cleanup();
    vi.mocked(moneyApi.fetchSchedule).mockResolvedValue(SCHEDULE([]));
    renderScreen();
    await tab('client');
    fireEvent.click(await screen.findByLabelText('payment-add'));
    fireEvent.click(screen.getByLabelText('payment-more'));
    expect(screen.queryByLabelText('payment-stage')).toBeNull();
  });

  it('keeps the stage of a record that is changed', async () => {
    vi.mocked(paymentsApi.updatePayment).mockResolvedValue(payment);
    renderScreen();
    await tab('client');
    fireEvent.click(await screen.findByLabelText('payment-edit-p1'));
    expect(screen.getByLabelText('payment-more-fields')).toBeInTheDocument(); // a record with a stage opens its options
    expect((screen.getByLabelText('payment-stage') as HTMLSelectElement).value).toBe('s1');
    fireEvent.change(screen.getByLabelText('payment-stage'), { target: { value: '' } });
    fireEvent.click(screen.getByLabelText('payment-save'));
    await waitFor(() => expect(paymentsApi.updatePayment).toHaveBeenCalledTimes(1));
    expect(vi.mocked(paymentsApi.updatePayment).mock.calls[0][2]).toMatchObject({ stage_id: null });
  });
});

describe('the hours', () => {
  it('shows the log, the sum and the rate the server sent', async () => {
    renderScreen();
    await tab('hours');
    expect(await screen.findByLabelText('hours-total')).toHaveTextContent('11,5 h');
    expect(screen.getByLabelText('hours-rate')).toHaveTextContent('nie ustawiono — ustaw w profilu wykonawcy');
    expect(screen.getByLabelText('hour-value-h1')).toHaveTextContent('7,5 h');
    expect(screen.getByLabelText('hour-h1')).toHaveTextContent('27.10.2026');
    expect(screen.getByLabelText('hour-h1')).toHaveTextContent('gładź salon');
    cleanup();
    vi.mocked(moneyApi.fetchHours).mockResolvedValue({ ...HOURS, hourly_rate: '90.00' });
    renderScreen();
    await tab('hours');
    expect(await screen.findByLabelText('hours-rate')).toHaveTextContent('90,00 zł / h');
  });

  it('adds hours: today by default, the comma, and nothing is sent for zero, more than a day or text', async () => {
    vi.mocked(moneyApi.createHours).mockResolvedValue(HOURS.items[0]);
    renderScreen();
    await tab('hours');
    fireEvent.click(await screen.findByLabelText('hours-add'));
    expect((screen.getByLabelText('hours-day') as HTMLInputElement).value).toBe(todayInPoland());
    expect(screen.getByLabelText('hours-value')).toHaveAttribute('inputmode', 'decimal');
    for (const bad of ['', '0', '24,5', '25', 'x', '1,234']) {
      type('hours-value', bad);
      fireEvent.click(screen.getByLabelText('hours-save'));
      expect(await screen.findByRole('alert')).toHaveTextContent('Wpisz godziny większe od zera, najwyżej 24');
    }
    expect(moneyApi.createHours).not.toHaveBeenCalled();
    type('hours-value', '7,5');
    type('hours-note', '  gładź  ');
    fireEvent.click(screen.getByLabelText('hours-save'));
    await waitFor(() => expect(moneyApi.createHours).toHaveBeenCalledWith(projectId, { worked_on: todayInPoland(), hours: '7.5', note: 'gładź' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Wpis zapisany.');
  });

  it('changes and deletes an entry, the delete after a second tap', async () => {
    vi.mocked(moneyApi.updateHours).mockResolvedValue(HOURS.items[0]);
    vi.mocked(moneyApi.deleteHours).mockResolvedValue(undefined);
    renderScreen();
    await tab('hours');
    fireEvent.click(await screen.findByLabelText('hour-edit-h1'));
    expect((screen.getByLabelText('hours-value') as HTMLInputElement).value).toBe('7,50');
    type('hours-value', '8');
    type('hours-note', '');
    fireEvent.click(screen.getByLabelText('hours-save'));
    await waitFor(() => expect(moneyApi.updateHours).toHaveBeenCalledWith(projectId, 'h1', { worked_on: '2026-10-27', hours: '8', note: null }));
    await screen.findByLabelText('hour-h2');
    fireEvent.click(screen.getByLabelText('hour-delete-h2'));
    expect(moneyApi.deleteHours).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('hour-delete-yes-h2'));
    await waitFor(() => expect(moneyApi.deleteHours).toHaveBeenCalledWith(projectId, 'h2'));
  });

  it('is empty with a hint and cannot be changed without the connection', async () => {
    vi.mocked(moneyApi.fetchHours).mockResolvedValue({ items: [], total_hours: '0.00', hourly_rate: null });
    renderScreen();
    await tab('hours');
    expect(await screen.findByLabelText('hours-empty')).toHaveTextContent('Brak godzin.');
    reportNetworkFailure();
    await waitFor(() => expect(screen.getByLabelText('hours-add')).toBeDisabled());
    expect(screen.getByLabelText('hours-offline')).toBeInTheDocument();
  });
});

describe('the words in four languages', () => {
  it.each([
    ['pl', ['Faktury', 'Od klienta', 'Materiały', 'Etapy', 'Godziny'], 'Marża obiektu'],
    ['ru', ['Фактуры', 'От клиента', 'Материалы', 'Этапы', 'Часы'], 'Маржа объекта'],
    ['uk', ['Рахунки', 'Від клієнта', 'Матеріали', 'Етапи', 'Години'], 'Маржа об’єкта'],
    ['en', ['Invoices', 'From the client', 'Materials', 'Stages', 'Hours'], 'Margin of the property'],
  ] as const)('%s', async (lang, tabs, marginTitle) => {
    localStorage.setItem('locale', lang);
    renderScreen();
    const tablist = await screen.findByLabelText('payments-tabs');
    expect(within(tablist).getAllByRole('tab').map((b) => b.textContent)).toEqual(tabs);
    expect(await screen.findByLabelText('margin-card')).toHaveTextContent(marginTitle);
    fireEvent.click(screen.getByLabelText('payments-tab-schedule'));
    expect((await screen.findByLabelText('stage-state-s1')).textContent?.length).toBeGreaterThan(2);
  });
});
