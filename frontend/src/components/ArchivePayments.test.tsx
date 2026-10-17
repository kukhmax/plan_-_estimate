import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import type { ArchivedPaymentItem, PaymentPurgePreview } from '../types/payment';
import { ArchiveScreen } from './ArchiveScreen';

vi.mock('../api/clients', () => ({ fetchClients: vi.fn(), restoreClient: vi.fn(), fetchClientDeletePreview: vi.fn(), deleteClient: vi.fn() }));
vi.mock('../api/projects', () => ({ fetchProjects: vi.fn(), restoreProject: vi.fn(), fetchProjectPurgePreview: vi.fn(), purgeProject: vi.fn() }));
vi.mock('../api/archiveStructure', () => ({ fetchArchivedStructure: vi.fn() }));
vi.mock('../api/rooms', () => ({ restoreRoom: vi.fn() }));
vi.mock('../api/surfaces', () => ({ restoreSurface: vi.fn() }));
vi.mock('../api/structurePurge', () => ({ fetchRoomPurgePreview: vi.fn(), purgeRoom: vi.fn(), fetchSurfacePurgePreview: vi.fn(), purgeSurface: vi.fn() }));
vi.mock('../api/payments', () => ({ fetchArchivedPayments: vi.fn(), restorePayment: vi.fn(), fetchPaymentPurgePreview: vi.fn(), purgePayment: vi.fn() }));
vi.mock('../api/photos', async () => ({
  ...(await vi.importActual<typeof import('../api/photos')>('../api/photos')),
  fetchPhotoArchive: vi.fn(),
}));
import { fetchArchivedStructure } from '../api/archiveStructure';
import { fetchClients } from '../api/clients';
import { fetchArchivedPayments, fetchPaymentPurgePreview, purgePayment, restorePayment } from '../api/payments';
import { fetchPhotoArchive } from '../api/photos';
import { fetchProjects } from '../api/projects';

const P1 = '11111111-1111-4111-8111-111111111111';
const P2 = '22222222-2222-4222-8222-222222222222';

const item = (id: string, over: Partial<ArchivedPaymentItem> = {}): ArchivedPaymentItem => ({
  id, project_id: P1, project_name: 'Mieszkanie Mokotów', kind: 'INVOICE', title: 'Faktura za etap 1', number: 'FV 1/2026', amount_gross: '5000.00',
  occurred_on: '2026-10-01', counterparty: null, category: null, photos: 0, ...over,
});
const EXPENSE = item('e1', { kind: 'EXPENSE', title: 'Wiertarka', amount_gross: '300.00', number: null, counterparty: 'Castorama', category: 'TOOLS', photos: 2, project_id: P2, project_name: 'Dom' });
const INVOICE = item('i1');

const preview = (over: Partial<PaymentPurgePreview> = {}): PaymentPurgePreview => ({
  target_id: 'i1', kind: 'INVOICE', title: 'Faktura za etap 1', archived: true, can_purge: true, tied_payments: 0, photos: 0, photo_files: 0, bytes: 0, annotations: 0,
  may_be_in_backups: false, ...over,
});

function renderScreen() {
  return render(<I18nProvider><ArchiveScreen /></I18nProvider>);
}
const openTab = async () => fireEvent.click(await screen.findByLabelText('archive-tab-payments'));

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(fetchClients).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(fetchProjects).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(fetchArchivedStructure).mockResolvedValue({ rooms: [], surfaces: [], rooms_total: 0, surfaces_total: 0 });
  vi.mocked(fetchPhotoArchive).mockResolvedValue({ items: [], archived_total: 0, trashed_total: 0, urls_expire_at: null });
  vi.mocked(fetchArchivedPayments).mockResolvedValue({ items: [INVOICE, EXPENSE], total: 2 });
  vi.mocked(restorePayment).mockResolvedValue({} as never);
  vi.mocked(fetchPaymentPurgePreview).mockResolvedValue(preview());
  vi.mocked(purgePayment).mockResolvedValue({ purged: true, photo_files: 0, storage_pending: 0 });
});

describe('ArchiveScreen: the settlement records "Faktury i zaliczki" (IA-7)', () => {
  it('has a tab with the number the server counted', async () => {
    renderScreen();
    await waitFor(() => expect(screen.getByLabelText('archive-count-payments')).toHaveTextContent('(2)'));
    expect(screen.getByLabelText('archive-tab-payments')).toHaveTextContent('Faktury i zaliczki');
  });

  it('lists each record with its kind, sum, day, number, shop, category, photos and object', async () => {
    renderScreen();
    await openTab();
    const list = await screen.findByLabelText('archive-payments-list');
    const invoice = within(within(list).getByLabelText('archived-payment-i1'));
    expect(invoice.getByText('Faktura')).toBeInTheDocument();
    expect(invoice.getByText('Faktura za etap 1')).toBeInTheDocument();
    expect(invoice.getByText(/5\s?000,00/)).toBeInTheDocument();
    expect(invoice.getByText(/01\.10\.2026 · Numer: FV 1\/2026/)).toBeInTheDocument();
    expect(invoice.getByText('Obiekt: Mieszkanie Mokotów')).toBeInTheDocument();
    const expense = within(within(list).getByLabelText('archived-payment-e1'));
    expect(expense.getByText('Wydatek')).toBeInTheDocument();
    expect(expense.getByText(/Castorama · Narzędzia · Zdjęcia: 2/)).toBeInTheDocument();
    expect(expense.getByText('Obiekt: Dom')).toBeInTheDocument();
  });

  it('says so when there is nothing, and says how many are shown when the list is cut', async () => {
    vi.mocked(fetchArchivedPayments).mockResolvedValue({ items: [], total: 0 });
    const view = renderScreen();
    await openTab();
    expect(await screen.findByLabelText('archive-empty-payments')).toHaveTextContent('Brak zarchiwizowanych wpisów rozliczeń.');
    view.unmount();
    vi.mocked(fetchArchivedPayments).mockResolvedValue({ items: [INVOICE], total: 250 });
    renderScreen();
    await openTab();
    await screen.findByLabelText('archive-payments-list');
    expect(screen.getByLabelText('archive-count-payments')).toHaveTextContent('(250)');
    expect(screen.getByText(/1.*250/)).toBeInTheDocument();
  });

  it('restores a record through the route of its own object and takes it off the list', async () => {
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('restore-payment-e1'));
    await waitFor(() => expect(restorePayment).toHaveBeenCalledWith(P2, 'e1'));
    await waitFor(() => expect(screen.queryByLabelText('archived-payment-e1')).toBeNull());
    expect(screen.getByLabelText('archived-payment-i1')).toBeInTheDocument();
    expect(screen.getByLabelText('archive-count-payments')).toHaveTextContent('(1)');
    expect(screen.getByRole('status')).toHaveTextContent('Wpis przywrócony.');
  });

  it('says so when the restoring fails and keeps the record in the list', async () => {
    vi.mocked(restorePayment).mockRejectedValue(new ApiError('x', 500));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('restore-payment-i1'));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByLabelText('archived-payment-i1')).toBeInTheDocument();
  });

  it('asks first what goes: the photos with their files, the payments that lose the link; nothing is sent before it is confirmed', async () => {
    vi.mocked(fetchPaymentPurgePreview).mockResolvedValue(preview({ photos: 2, photo_files: 2, bytes: 3_145_728, tied_payments: 3, annotations: 1, may_be_in_backups: true }));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-payment-i1'));
    const dialog = await screen.findByRole('alertdialog');
    expect(fetchPaymentPurgePreview).toHaveBeenCalledWith(P1, 'i1');
    const lines = await within(dialog).findByLabelText('payment-delete-lines');
    expect(lines).toHaveTextContent('Zdjęcia: 2; pliki w magazynie: 2');
    expect(lines).toHaveTextContent('Znaczniki na zdjęciach: 1');
    expect(lines).toHaveTextContent('Wpłaty i zaliczki powiązane z tą fakturą: 3');
    expect(within(dialog).getByText(/kopii zapasowej/)).toBeInTheDocument();
    expect(purgePayment).not.toHaveBeenCalled();
    const confirm = within(dialog).getByLabelText('payment-delete-confirm');
    expect(confirm).toBeDisabled();
    fireEvent.click(within(dialog).getByLabelText('payment-delete-understood'));
    expect(confirm).toBeEnabled();
  });

  it('shows "nothing more" for a record without photos and without payments tied to it', async () => {
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-payment-i1'));
    const dialog = await screen.findByRole('alertdialog');
    expect(await within(dialog).findByText('Nie ma tu nic więcej: ani zdjęć, ani powiązanych wpłat.')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('payment-delete-lines')).toBeNull();
  });

  it('deletes after the tick and takes the record off the list, and the photo tab reads its lists again', async () => {
    renderScreen();
    await openTab();
    await waitFor(() => expect(fetchPhotoArchive).toHaveBeenCalled());
    const photoReads = vi.mocked(fetchPhotoArchive).mock.calls.length;
    fireEvent.click(await screen.findByLabelText('delete-payment-i1'));
    const dialog = await screen.findByRole('alertdialog');
    await within(dialog).findByLabelText('payment-delete-understood');
    fireEvent.click(within(dialog).getByLabelText('payment-delete-understood'));
    fireEvent.click(within(dialog).getByLabelText('payment-delete-confirm'));
    await waitFor(() => expect(purgePayment).toHaveBeenCalledWith(P1, 'i1'));
    await waitFor(() => expect(screen.queryByLabelText('archived-payment-i1')).toBeNull());
    expect(screen.getByLabelText('archive-count-payments')).toHaveTextContent('(1)');
    expect(screen.getByRole('status')).toHaveTextContent('Wpis usunięty.');
    await waitFor(() => expect(vi.mocked(fetchPhotoArchive).mock.calls.length).toBeGreaterThan(photoReads));
  });

  it('says the files will follow when the storage was not reached', async () => {
    vi.mocked(purgePayment).mockResolvedValue({ purged: true, photo_files: 1, storage_pending: 1 });
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-payment-i1'));
    const dialog = await screen.findByRole('alertdialog');
    await within(dialog).findByLabelText('payment-delete-understood');
    fireEvent.click(within(dialog).getByLabelText('payment-delete-understood'));
    fireEvent.click(within(dialog).getByLabelText('payment-delete-confirm'));
    expect(await screen.findByText(/Pliki zdjęć w magazynie zostaną usunięte/)).toBeInTheDocument();
  });

  it('keeps the record, asks to try again and reads the preview anew when it changed meanwhile (409)', async () => {
    vi.mocked(purgePayment).mockRejectedValue(new ApiError('x', 409, 'PAYMENT_PURGE_CONFLICT'));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-payment-i1'));
    const dialog = await screen.findByRole('alertdialog');
    await within(dialog).findByLabelText('payment-delete-understood');
    fireEvent.click(within(dialog).getByLabelText('payment-delete-understood'));
    fireEvent.click(within(dialog).getByLabelText('payment-delete-confirm'));
    expect(await within(dialog).findByText(/Zmieniło się w trakcie usuwania/)).toBeInTheDocument();
    expect(fetchPaymentPurgePreview).toHaveBeenCalledTimes(2);
    expect(within(dialog).getByLabelText('payment-delete-understood')).not.toBeChecked();
    expect(screen.getByLabelText('archived-payment-i1')).toBeInTheDocument();
  });

  it('says so when the deletion fails for another reason, and when the preview cannot be read', async () => {
    vi.mocked(purgePayment).mockRejectedValue(new ApiError('x', 500));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-payment-i1'));
    let dialog = await screen.findByRole('alertdialog');
    await within(dialog).findByLabelText('payment-delete-understood');
    fireEvent.click(within(dialog).getByLabelText('payment-delete-understood'));
    fireEvent.click(within(dialog).getByLabelText('payment-delete-confirm'));
    expect(await within(dialog).findByText('Nie udało się usunąć.')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByLabelText('payment-delete-cancel'));
    vi.mocked(fetchPaymentPurgePreview).mockRejectedValue(new ApiError('x', 500));
    fireEvent.click(screen.getByLabelText('delete-payment-i1'));
    dialog = await screen.findByRole('alertdialog');
    expect(await within(dialog).findByText('Nie udało się wczytać archiwum.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('payment-delete-confirm')).toBeDisabled();
  });

  it('cancel closes the question and sends nothing', async () => {
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-payment-i1'));
    fireEvent.click(await screen.findByLabelText('payment-delete-cancel'));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(purgePayment).not.toHaveBeenCalled();
  });

  it('a failing list of the records does not hide the clients, and offers a retry', async () => {
    vi.mocked(fetchArchivedPayments).mockRejectedValueOnce(new ApiError('x', 500));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('archive-retry'));
    expect(await screen.findByLabelText('archive-payments-list')).toBeInTheDocument();
    expect(fetchArchivedPayments).toHaveBeenCalledTimes(2);
  });

  it('shows the tab in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderScreen();
    expect(await screen.findByLabelText('archive-tab-payments')).toHaveTextContent('Счета и авансы');
    await openTab();
    const list = await screen.findByLabelText('archive-payments-list');
    expect(within(list).getByText('Расход')).toBeInTheDocument();
    expect(within(list).getByText('Объект: Dom')).toBeInTheDocument();
  });

  it('keeps the touch targets of the row at 44 px', async () => {
    renderScreen();
    await openTab();
    await screen.findByLabelText('archive-payments-list');
    for (const label of ['restore-payment-i1', 'delete-payment-i1']) expect(screen.getByLabelText(label).className).toContain('min-h-11');
  });
});
