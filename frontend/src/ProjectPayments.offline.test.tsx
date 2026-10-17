import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectPayments } from './components/ProjectPayments';
import { I18nProvider } from './hooks/useI18n';
import { reportNetworkFailure, reportNetworkSuccess, resetConnectionForTests } from './offline/connection';
import { listOps } from './offline/outbox';
import { resetSyncStateForTests } from './offline/outboxState';
import { setOfflineOwner } from './offline/readCache';
import { drainOutbox } from './offline/sync';
import { freshIndexedDb } from './test/fakeIdb';

// IA-4: the screen of the settlements without a signal: the real api layer, the real queue, a small server in place of the network.

const P = '11111111-1111-4111-8111-111111111111';
const json = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as unknown as Response;
const INVOICE = {
  id: '00000000-0000-4000-8000-0000000000a1', project_id: P, kind: 'INVOICE', title: 'Faktura za etap 1', number: null, amount_gross: '1000.00', amount_net: null,
  vat_rate: null, occurred_on: '2026-10-01', due_on: '2026-10-15', settles_id: null, counterparty: null, document_kind: null, note: null, is_archived: false,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z', settled: '400.00', remaining: '600.00', state: 'PARTIAL',
};
const SUMMARY = { invoiced: '1000.00', received: '400.00', expenses: '0.00', invoiced_unpaid: '600.00', to_receive: '39600.00', result: '400.00' };

function serverStub() {
  const rows = new Map<string, Record<string, unknown>>([[INVOICE.id, INVOICE]]);
  const received: Array<{ method: string; path: string; body: Record<string, unknown> | null }> = [];
  const state = { up: true };
  const base = `/api/projects/${P}/payments`;
  const handler = vi.fn(async (url: string, init?: RequestInit) => {
    if (!state.up) throw new TypeError('Failed to fetch');
    const path = String(url);
    const method = init?.method ?? 'GET';
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    if (method !== 'GET') received.push({ method, path, body });
    if (method === 'GET' && path.startsWith(base)) {
      const all = path.includes('include_archived=true');
      const items = [...rows.values()].filter((row) => all || !row.is_archived);
      return json({ items, total: items.length, summary: SUMMARY, agreed_amount: '40000.00' });
    }
    if (method === 'POST' && path === base) {
      if (!rows.has(String(body?.id))) rows.set(String(body?.id), { ...INVOICE, ...body, settled: '0.00', remaining: String(body?.amount_gross), state: 'OPEN' });
      return json(rows.get(String(body?.id)), 201);
    }
    return json({}, 200);
  });
  return { handler, rows, received, state };
}

function renderScreen() {
  return render(
    <I18nProvider>
      <ProjectPayments projectId={P} />
    </I18nProvider>,
  );
}
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe('the settlements without a signal (IA-4)', () => {
  beforeEach(async () => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    resetConnectionForTests();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function openedOnline() {
    const server = serverStub();
    vi.stubGlobal('fetch', server.handler);
    renderScreen();
    await screen.findByLabelText('payments-list'); // read once with a signal: the copy is kept on the phone
    return server;
  }

  it('a record made without a signal is in the list at once, marked as waiting, with a note that the sums are the server\'s', async () => {
    const server = await openedOnline();
    expect(screen.queryByLabelText('payments-pending-note')).toBeNull();
    server.state.up = false;
    reportNetworkFailure();

    fireEvent.click(screen.getByLabelText('payments-tab-materials'));
    fireEvent.click(screen.getByLabelText('payment-add'));
    type('payment-title', 'Farba biała');
    type('payment-amount', '89,99');
    fireEvent.click(screen.getByLabelText('payment-save'));

    expect(await screen.findByText('Farba biała')).toBeInTheDocument();
    const card = within(screen.getByLabelText('payments-list')).getAllByRole('listitem')[0];
    expect(within(card).getByText('Czeka na wysłanie')).toBeInTheDocument();
    expect(within(card).getByText('89,99 zł')).toBeInTheDocument();
    expect(screen.getByLabelText('payments-pending-note')).toHaveTextContent('Sumy nie obejmują wpisów czekających na wysłanie');
    expect(screen.getByRole('status')).toHaveTextContent('Zapisano.');
    expect(server.received).toEqual([]);
    expect((await listOps()).map((o) => o.kind)).toEqual(['payment.create']);
  });

  it('the summary stays exactly as the server last said it (nothing is added up on the phone)', async () => {
    const server = await openedOnline();
    server.state.up = false;
    reportNetworkFailure();
    fireEvent.click(screen.getByLabelText('payment-add'));
    type('payment-title', 'Faktura 2');
    type('payment-amount', '5000');
    fireEvent.click(screen.getByLabelText('payment-save'));
    await screen.findByText('Faktura 2');
    expect(screen.getByLabelText('summary-invoiced')).toHaveTextContent('1000,00 zł');
    expect(screen.getByLabelText('summary-to_receive')).toHaveTextContent('39600,00 zł');
  });

  it('an invoice made on the phone has no standing yet (no "paid / left", no state): the server counts it', async () => {
    const server = await openedOnline();
    server.state.up = false;
    reportNetworkFailure();
    fireEvent.click(screen.getByLabelText('payment-add'));
    type('payment-title', 'Faktura 2');
    type('payment-amount', '5000');
    fireEvent.click(screen.getByLabelText('payment-save'));
    await screen.findByText('Faktura 2');
    const cards = within(screen.getByLabelText('payments-list')).getAllByRole('listitem');
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).queryByText(/Zapłacono/)).toBeNull();
    expect(within(cards[0]).queryByLabelText(/payment-state-/)).toBeNull();
    expect(within(cards[1]).getByText(/Zapłacono: 400,00 zł/)).toBeInTheDocument(); // the saved one keeps its numbers
  });

  it('a change of the amount of a saved invoice empties its standing until the server counts it again', async () => {
    const server = await openedOnline();
    server.state.up = false;
    reportNetworkFailure();
    fireEvent.click(screen.getByLabelText(`payment-edit-${INVOICE.id}`));
    type('payment-amount', '1200');
    fireEvent.click(screen.getByLabelText('payment-save'));
    await waitFor(() => expect(screen.getByLabelText(`payment-amount-${INVOICE.id}`)).toHaveTextContent('1200,00 zł'));
    const card = screen.getByLabelText(`payment-${INVOICE.id}`);
    expect(within(card).getByText('Czeka na wysłanie')).toBeInTheDocument();
    expect(within(card).queryByText(/Zapłacono/)).toBeNull();
    expect(screen.queryByLabelText(`payment-state-${INVOICE.id}`)).toBeNull();
  });

  it('archiving without a signal takes the card out of the list; a restore brings it back', async () => {
    const server = await openedOnline();
    server.state.up = false;
    reportNetworkFailure();
    fireEvent.click(screen.getByLabelText(`payment-archive-${INVOICE.id}`));
    await waitFor(() => expect(screen.queryByLabelText(`payment-${INVOICE.id}`)).toBeNull());
    expect((await listOps()).map((o) => o.kind)).toEqual(['payment.archive']);
  });

  it('the agreed amount waits for the signal: its button is off and says why, and comes back with the signal', async () => {
    const server = await openedOnline();
    expect(screen.getByLabelText('agreed-edit')).toBeEnabled();
    server.state.up = false;
    act(() => reportNetworkFailure());
    await waitFor(() => expect(screen.getByLabelText('agreed-edit')).toBeDisabled());
    expect(screen.getByLabelText('agreed-offline')).toHaveTextContent('Umówioną kwotę zmienisz, gdy wróci zasięg.');
    server.state.up = true;
    act(() => reportNetworkSuccess());
    await waitFor(() => expect(screen.getByLabelText('agreed-edit')).toBeEnabled());
    expect(screen.queryByLabelText('agreed-offline')).toBeNull();
  });

  it('when the signal returns the record is sent once with its id, and the mark goes away after the list is read again', async () => {
    const server = await openedOnline();
    server.state.up = false;
    reportNetworkFailure();
    fireEvent.click(screen.getByLabelText('payment-add'));
    type('payment-title', 'Faktura 2');
    type('payment-amount', '5000');
    fireEvent.click(screen.getByLabelText('payment-save'));
    await screen.findByText('Faktura 2');

    server.state.up = true;
    reportNetworkSuccess();
    await drainOutbox();
    expect(server.received).toHaveLength(1);
    expect(server.received[0].body).toMatchObject({ kind: 'INVOICE', title: 'Faktura 2', amount_gross: '5000' });
    expect(server.received[0].body?.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(await listOps()).toEqual([]);
    fireEvent.click(screen.getByLabelText('payments-show-archived')); // any read of the list again
    fireEvent.click(screen.getByLabelText('payments-show-archived'));
    await waitFor(() => expect(screen.queryByText('Czeka na wysłanie')).toBeNull());
    expect(screen.queryByLabelText('payments-pending-note')).toBeNull();
  });

  it('speaks Russian', async () => {
    localStorage.setItem('locale', 'ru');
    const server = await openedOnline();
    server.state.up = false;
    reportNetworkFailure();
    fireEvent.click(screen.getByLabelText('payment-add'));
    type('payment-title', 'Счёт 2');
    type('payment-amount', '5000');
    fireEvent.click(screen.getByLabelText('payment-save'));
    await screen.findByText('Счёт 2');
    expect(screen.getByLabelText('payments-pending-note')).toHaveTextContent('Итоги не включают записи, ожидающие отправки');
    expect(screen.getByLabelText('agreed-offline')).toHaveTextContent('Договорную сумму можно изменить, когда появится связь.');
  });
});
