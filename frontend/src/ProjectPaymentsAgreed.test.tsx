import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as paymentsApi from './api/payments';
import * as moneyApi from './api/paymentSchedule';
import { ProjectPayments } from './components/ProjectPayments';
import { I18nProvider } from './hooks/useI18n';
import { reportNetworkFailure, resetConnectionForTests } from './offline/connection';
import type { Payment, PaymentList } from './types/payment';
import type { Margin, PaymentStage, Schedule, WorkHours } from './types/paymentSchedule';

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

const projectId = '11111111-1111-1111-1111-111111111111';
const stage = (over: Partial<PaymentStage>): PaymentStage => ({
  id: 's1', project_id: projectId, title: 'Zaliczka', percent: '30.00', amount_fixed: null, due_on: '2026-11-05', amount: '12000.00', received: '5000.00', remaining: '7000.00',
  state: 'PARTIAL', created_at: '2026-10-28T10:00:00Z', updated_at: '2026-10-28T10:00:00Z', ...over,
});
const PARTIAL = stage({});
const PAID = stage({ id: 's2', title: 'Po gładziach', percent: null, amount_fixed: '5000.00', amount: '5000.00', received: '5000.00', remaining: '0.00', state: 'PAID', due_on: null });
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


// B5 — the agreed amount from the accepted estimate, one tap on the summary.
const SUGGESTION = { amount: '14581.02', estimate_id: 'e1', estimate_version: 3, status: 'ACCEPTED' };

const renderScreen = () => render(<I18nProvider><ProjectPayments projectId={projectId} /></I18nProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  resetConnectionForTests();
  vi.mocked(paymentsApi.fetchPayments).mockResolvedValue({ ...LIST, agreed_amount: null });
  vi.mocked(paymentsApi.fetchFinance).mockResolvedValue({ agreed_amount: null, currency: 'PLN', suggestion: SUGGESTION });
  vi.mocked(paymentsApi.saveAgreedAmount).mockResolvedValue({ agreed_amount: '14581.02', currency: 'PLN', suggestion: SUGGESTION });
  vi.mocked(moneyApi.fetchSchedule).mockResolvedValue(SCHEDULE([PARTIAL, PAID]));
  vi.mocked(moneyApi.fetchMargin).mockResolvedValue(MARGIN);
  vi.mocked(moneyApi.fetchHours).mockResolvedValue(HOURS);
});
afterEach(cleanup);

describe('B5: the agreed amount from the estimate on the summary', () => {
  it('offers the amount of the accepted estimate while none is set and saves it with one tap', async () => {
    renderScreen();
    const take = await screen.findByLabelText('agreed-from-estimate');
    expect(take).toHaveTextContent('Przyjmij kwotę netto z kosztorysu (wersja 3): 14581,02 zł');
    expect(take.className).toContain('min-h-11');
    expect(within(screen.getByLabelText('agreed-from-estimate-box')).queryByText(/różni się/)).toBeNull();
    vi.mocked(paymentsApi.fetchPayments).mockResolvedValue({ ...LIST, agreed_amount: '14581.02' });
    fireEvent.click(take);
    await waitFor(() => expect(paymentsApi.saveAgreedAmount).toHaveBeenCalledWith(projectId, '14581.02'));
    await waitFor(() => expect(screen.getByLabelText('summary-agreed')).toHaveTextContent('14581,02 zł'));
    expect(screen.queryByLabelText('agreed-from-estimate')).toBeNull(); // the amount is the estimate's now
  });

  it('says so when the agreed amount differs from the estimate, and is silent when they match or there is no estimate', async () => {
    vi.mocked(paymentsApi.fetchPayments).mockResolvedValue({ ...LIST, agreed_amount: '14000.00' });
    const view = renderScreen();
    expect(await screen.findByLabelText('agreed-from-estimate-box')).toHaveTextContent('Umówiona kwota różni się od kosztorysu (wersja 3).');
    view.unmount();

    vi.mocked(paymentsApi.fetchPayments).mockResolvedValue({ ...LIST, agreed_amount: '14581.020' });
    const same = renderScreen();
    await screen.findByLabelText('summary-agreed');
    await waitFor(() => expect(paymentsApi.fetchFinance).toHaveBeenCalled());
    expect(screen.queryByLabelText('agreed-from-estimate')).toBeNull();
    same.unmount();

    vi.mocked(paymentsApi.fetchPayments).mockResolvedValue({ ...LIST, agreed_amount: null });
    vi.mocked(paymentsApi.fetchFinance).mockResolvedValue({ agreed_amount: null, currency: 'PLN', suggestion: null });
    renderScreen();
    await screen.findByLabelText('summary-agreed');
    expect(screen.queryByLabelText('agreed-from-estimate')).toBeNull();
  });

  it('cannot be used without the connection', async () => {
    renderScreen();
    const take = await screen.findByLabelText('agreed-from-estimate');
    reportNetworkFailure();
    await waitFor(() => expect(take).toBeDisabled());
  });
});
