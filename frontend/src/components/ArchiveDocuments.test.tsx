import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import type { ArchivedDocumentItem, DocumentPurgePreview } from '../types/archivedDocument';
import { ArchiveScreen } from './ArchiveScreen';

vi.mock('../api/clients', () => ({ fetchClients: vi.fn(), restoreClient: vi.fn(), fetchClientDeletePreview: vi.fn(), deleteClient: vi.fn() }));
vi.mock('../api/projects', () => ({ fetchProjects: vi.fn(), restoreProject: vi.fn(), fetchProjectPurgePreview: vi.fn(), purgeProject: vi.fn() }));
vi.mock('../api/archiveStructure', () => ({ fetchArchivedStructure: vi.fn() }));
vi.mock('../api/rooms', () => ({ restoreRoom: vi.fn() }));
vi.mock('../api/surfaces', () => ({ restoreSurface: vi.fn() }));
vi.mock('../api/structurePurge', () => ({ fetchRoomPurgePreview: vi.fn(), purgeRoom: vi.fn(), fetchSurfacePurgePreview: vi.fn(), purgeSurface: vi.fn() }));
vi.mock('../api/payments', () => ({ fetchArchivedPayments: vi.fn(), restorePayment: vi.fn(), fetchPaymentPurgePreview: vi.fn(), purgePayment: vi.fn() }));
vi.mock('../api/archivedDocuments', () => ({ fetchArchivedDocuments: vi.fn(), fetchDocumentPurgePreview: vi.fn(), purgeArchivedDocument: vi.fn() }));
vi.mock('../api/photos', async () => ({
  ...(await vi.importActual<typeof import('../api/photos')>('../api/photos')),
  fetchPhotoArchive: vi.fn(),
}));
import { fetchArchivedDocuments, fetchDocumentPurgePreview, purgeArchivedDocument } from '../api/archivedDocuments';
import { fetchArchivedStructure } from '../api/archiveStructure';
import { fetchClients } from '../api/clients';
import { fetchArchivedPayments } from '../api/payments';
import { fetchPhotoArchive } from '../api/photos';
import { fetchProjects } from '../api/projects';

const item = (id: string, over: Partial<ArchivedDocumentItem> = {}): ArchivedDocumentItem => ({
  kind: 'CONTRACT', id, project_id: 'p1', project_name: 'Mieszkanie Mokotów', ordinal: 2, number: 'UM/2026/5',
  issued_at: '2026-10-18T12:00:00Z', archived_at: '2026-10-18T15:30:00Z', ...over,
});
const CONTRACT = item('c1');
const DRAFT = item('h1', { kind: 'HANDOVER', ordinal: 3, number: null, issued_at: null, project_name: 'Dom' });

const preview = (over: Partial<DocumentPurgePreview> = {}): DocumentPurgePreview => ({
  kind: 'CONTRACT', target_id: 'c1', ordinal: 2, archived: true, issued: true, can_purge: true, journal_lines: 0, dependents: 0, ...over,
});

function renderScreen() {
  return render(<I18nProvider><ArchiveScreen /></I18nProvider>);
}
const openTab = async () => fireEvent.click(await screen.findByLabelText('archive-tab-documents'));

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(fetchClients).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(fetchProjects).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(fetchArchivedStructure).mockResolvedValue({ rooms: [], surfaces: [], rooms_total: 0, surfaces_total: 0 });
  vi.mocked(fetchPhotoArchive).mockResolvedValue({ items: [], archived_total: 0, trashed_total: 0, urls_expire_at: null });
  vi.mocked(fetchArchivedPayments).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(fetchArchivedDocuments).mockResolvedValue({ items: [CONTRACT, DRAFT], total: 2 });
  vi.mocked(fetchDocumentPurgePreview).mockResolvedValue(preview());
  vi.mocked(purgeArchivedDocument).mockResolvedValue({ purged: true });
});

describe('ArchiveScreen: the tab "Umowy i protokoły" (AC-6)', () => {
  it('has a tab with the number the server counted', async () => {
    renderScreen();
    await waitFor(() => expect(screen.getByLabelText('archive-count-documents')).toHaveTextContent('(2)'));
    expect(screen.getByLabelText('archive-tab-documents')).toHaveTextContent('Umowy i protokoły');
  });

  it('lists a record with its kind, version, number, object, issue day and archive day; a draft says it was never issued', async () => {
    renderScreen();
    await openTab();
    const list = await screen.findByLabelText('archive-documents-list');
    const contract = within(within(list).getByLabelText('archived-document-c1'));
    expect(contract.getByText('Umowa')).toBeInTheDocument();
    expect(contract.getByText('Wersja 2 · Numer: UM/2026/5')).toBeInTheDocument();
    expect(contract.getByText('Obiekt: Mieszkanie Mokotów')).toBeInTheDocument();
    expect(contract.getByText(/Wystawiony: 18\.10\.2026.*Zarchiwizowany: 18\.10\.2026/)).toBeInTheDocument();
    const draft = within(within(list).getByLabelText('archived-document-h1'));
    expect(draft.getByText('Protokół przekazania pomieszczeń')).toBeInTheDocument();
    expect(draft.getByText('Nr 3')).toBeInTheDocument();
    expect(draft.getByText(/Szkic — nie wystawiony/)).toBeInTheDocument();
  });

  it('speaks Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderScreen();
    await openTab();
    expect(screen.getByLabelText('archive-tab-documents')).toHaveTextContent('Договоры и протоколы');
    const row = within(await screen.findByLabelText('archived-document-c1'));
    expect(row.getByText('Договор')).toBeInTheDocument();
    expect(row.getByText('Версия 2 · Номер: UM/2026/5')).toBeInTheDocument();
  });

  it('says so when there is nothing, and says how many are shown when the list is cut', async () => {
    vi.mocked(fetchArchivedDocuments).mockResolvedValue({ items: [], total: 0 });
    const view = renderScreen();
    await openTab();
    expect(await screen.findByLabelText('archive-empty-documents')).toHaveTextContent('Brak zarchiwizowanych umów i protokołów.');
    view.unmount();
    vi.mocked(fetchArchivedDocuments).mockResolvedValue({ items: [CONTRACT], total: 250 });
    renderScreen();
    await openTab();
    await screen.findByLabelText('archive-documents-list');
    expect(screen.getByText(/1.*250/)).toBeInTheDocument();
  });

  it('a failed load shows a retry that does not hide the other tabs', async () => {
    vi.mocked(fetchArchivedDocuments).mockRejectedValueOnce(new Error('down'));
    renderScreen();
    await openTab();
    expect(await screen.findByLabelText('archive-retry')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('archive-retry'));
    expect(await screen.findByLabelText('archive-documents-list')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('archive-tab-payments'));
    expect(await screen.findByLabelText('archive-empty-payments')).toBeInTheDocument();
  });

  it('has no restore button: the page of a document is not kept for reading', async () => {
    renderScreen();
    await openTab();
    await screen.findByLabelText('archive-documents-list');
    expect(screen.queryByLabelText('restore-document-c1')).not.toBeInTheDocument();
    expect(screen.getByLabelText('delete-document-c1')).toBeInTheDocument();
  });

  it('deleting needs the preview, the tick and the confirmation, and then the record leaves the list and the count goes down', async () => {
    vi.mocked(fetchDocumentPurgePreview).mockResolvedValue(preview({ journal_lines: 1 }));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-document-c1'));
    const dialog = await screen.findByRole('alertdialog');
    expect(await within(dialog).findByLabelText('document-delete-lines')).toHaveTextContent('Wpisy w dzienniku wysłanych dokumentów: 1');
    expect(within(dialog).getByText(/Plik PDF wysłany na czat/)).toBeInTheDocument();
    const confirm = within(dialog).getByLabelText('document-delete-confirm');
    expect(confirm).toBeDisabled();
    fireEvent.click(within(dialog).getByLabelText('document-delete-understood'));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(purgeArchivedDocument).toHaveBeenCalledWith('CONTRACT', 'c1'));
    await waitFor(() => expect(screen.queryByLabelText('archived-document-c1')).not.toBeInTheDocument());
    expect(screen.getByLabelText('archive-count-documents')).toHaveTextContent('(1)');
    expect(screen.getByRole('status')).toHaveTextContent('Zapis usunięty.');
  });

  it('cancelling deletes nothing', async () => {
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-document-c1'));
    fireEvent.click(await screen.findByLabelText('document-delete-cancel'));
    expect(purgeArchivedDocument).not.toHaveBeenCalled();
    expect(screen.getByLabelText('archived-document-c1')).toBeInTheDocument();
  });

  it('a contract that protocols still refer to cannot be confirmed, and says why', async () => {
    vi.mocked(fetchDocumentPurgePreview).mockResolvedValue(preview({ can_purge: false, dependents: 2 }));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-document-c1'));
    const dialog = await screen.findByRole('alertdialog');
    expect(await within(dialog).findByText(/niezarchiwizowanych protokołów: 2/)).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('document-delete-understood')).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText('document-delete-confirm')).toBeDisabled();
  });

  it('when the server refuses at the end (protocols appeared meanwhile) nothing leaves the list', async () => {
    vi.mocked(purgeArchivedDocument).mockRejectedValue(new ApiError('in use', 409, 'DOCUMENT_RECORD_IN_USE'));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-document-c1'));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(await within(dialog).findByLabelText('document-delete-understood'));
    fireEvent.click(within(dialog).getByLabelText('document-delete-confirm'));
    expect(await within(dialog).findByText(/Do tej umowy odnoszą się protokoły/)).toBeInTheDocument();
    expect(screen.getByLabelText('archived-document-c1')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('document-delete-confirm')).toBeDisabled();
  });

  it('a failed preview shows an error and allows no deletion', async () => {
    vi.mocked(fetchDocumentPurgePreview).mockRejectedValue(new Error('down'));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-document-c1'));
    const dialog = await screen.findByRole('alertdialog');
    expect(await within(dialog).findByText('Nie udało się wczytać archiwum.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('document-delete-confirm')).toBeDisabled();
  });
});
