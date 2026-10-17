import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { SentDocuments } from './SentDocuments';
import { I18nProvider } from '../hooks/useI18n';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import type { OwnerDocument } from '../types/document';

vi.mock('../api/documents', () => ({ listAllDocuments: vi.fn(), deleteDocument: vi.fn() }));

const doc = (n: number, overrides: Partial<OwnerDocument> = {}): OwnerDocument => ({
  id: `d${n}`, project_id: `p${n}`, kind: 'ESTIMATE', source_id: null, source_version: null, title: `Dokument ${n}`,
  number: `KOSZ/2026/10/0${n}/1200`, project_seq: n, template_version: '1', status: 'SENT', error_code: null, scope: null,
  pages: 3, byte_size: 52_000, issued_at: `2026-10-0${n}T10:00:00Z`, sent_at: `2026-10-0${n}T10:00:05Z`, project_name: `Obiekt ${n}`, ...overrides,
});

function renderScreen() {
  return render(<I18nProvider><SentDocuments /></I18nProvider>);
}

describe('SentDocuments (Stage 16K.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('shows what was sent from every object: the kind, the object, the number, the date, the size', async () => {
    vi.mocked(documentsApi.listAllDocuments).mockResolvedValue({
      items: [doc(2, { kind: 'CONTRACT', number: 'UMOWA/2026/10/02/1200' }), doc(1)], total: 2,
    });
    renderScreen();
    const list = await screen.findByLabelText('sent-documents-list');
    expect(documentsApi.listAllDocuments).toHaveBeenCalledWith(30, 0);
    const contract = within(list).getByLabelText('document-UMOWA/2026/10/02/1200');
    expect(contract).toHaveTextContent('Umowa');
    expect(contract).toHaveTextContent('Obiekt 2');
    expect(contract).toHaveTextContent('Wysłano');
    expect(contract).toHaveTextContent('3 str.');
    expect(contract).toHaveTextContent('52 KB');
    expect(contract).toHaveTextContent('02.10.2026');
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByLabelText('sent-documents-shown')).toHaveTextContent('Pokazano 2 z 2');
    expect(screen.queryByLabelText('sent-documents-more')).toBeNull();
  });

  it('names every kind of a document in the language of the screen', async () => {
    const kinds = ['ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', 'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL'] as const;
    vi.mocked(documentsApi.listAllDocuments).mockResolvedValue({
      items: kinds.map((kind, index) => doc(index + 1, { kind, number: `N/${index}` })), total: kinds.length,
    });
    localStorage.setItem('locale', 'ru');
    renderScreen();
    const list = await screen.findByLabelText('sent-documents-list');
    const labels = within(list).getAllByRole('listitem').map((item) => item.querySelector('span')?.textContent);
    expect(new Set(labels).size).toBe(kinds.length); // no two kinds share a name, none is empty
    expect(labels.every((label) => label && !label.startsWith('documents.'))).toBe(true);
    expect(labels).toContain('Договор');
  });

  it('a failed document shows why, a running one shows that it is running', async () => {
    vi.mocked(documentsApi.listAllDocuments).mockResolvedValue({
      items: [
        doc(1, { status: 'FAILED', error_code: 'TELEGRAM_CHAT_UNAVAILABLE', number: 'F/1', sent_at: null }),
        doc(2, { status: 'PENDING', number: 'P/1', sent_at: null }),
      ],
      total: 2,
    });
    renderScreen();
    const failed = await screen.findByLabelText('document-F/1');
    expect(failed).toHaveTextContent('Nie wysłano');
    expect(failed.textContent).toMatch(/Start/);
    expect(screen.getByLabelText('document-P/1')).toHaveTextContent('Wysyłanie…');
  });

  it('loads the next page when there are more and adds it to the list', async () => {
    const first = Array.from({ length: 30 }, (_, i) => doc(1, { id: `a${i}`, number: `A/${i}`, project_name: `Pierwszy ${i}` }));
    vi.mocked(documentsApi.listAllDocuments)
      .mockResolvedValueOnce({ items: first, total: 32 })
      .mockResolvedValueOnce({ items: [doc(2, { id: 'b1', number: 'B/1' }), doc(3, { id: 'b2', number: 'B/2' })], total: 32 });
    renderScreen();
    await screen.findByLabelText('sent-documents-list');
    expect(screen.getByLabelText('sent-documents-shown')).toHaveTextContent('Pokazano 30 z 32');
    fireEvent.click(screen.getByLabelText('sent-documents-more'));
    await waitFor(() => expect(screen.getByLabelText('document-B/2')).toBeInTheDocument());
    expect(documentsApi.listAllDocuments).toHaveBeenLastCalledWith(30, 30);
    expect(screen.getByLabelText('document-A/0')).toBeInTheDocument();
    expect(screen.getByLabelText('sent-documents-shown')).toHaveTextContent('Pokazano 32 z 32');
    expect(screen.queryByLabelText('sent-documents-more')).toBeNull();
  });

  it('refresh reads the first page again', async () => {
    vi.mocked(documentsApi.listAllDocuments).mockResolvedValueOnce({ items: [doc(1)], total: 1 });
    renderScreen();
    await screen.findByLabelText('sent-documents-list');
    vi.mocked(documentsApi.listAllDocuments).mockResolvedValueOnce({ items: [doc(2, { number: 'NEW/1' }), doc(1)], total: 2 });
    fireEvent.click(screen.getByLabelText('sent-documents-refresh'));
    expect(await screen.findByLabelText('document-NEW/1')).toBeInTheDocument();
    expect(documentsApi.listAllDocuments).toHaveBeenLastCalledWith(30, 0);
    expect(within(screen.getByLabelText('sent-documents-list')).getAllByRole('listitem')).toHaveLength(2);
  });

  it('says when nothing was sent, and when the list cannot be loaded', async () => {
    vi.mocked(documentsApi.listAllDocuments).mockResolvedValueOnce({ items: [], total: 0 });
    renderScreen();
    expect(await screen.findByLabelText('sent-documents-empty')).toHaveTextContent('Nic jeszcze nie wysłano.');
    vi.mocked(documentsApi.listAllDocuments).mockRejectedValueOnce(new Error('offline'));
    fireEvent.click(screen.getByLabelText('sent-documents-refresh'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać listy dokumentów.');
  });

  it('the buttons are 44 px and a long object name and number wrap inside the card', async () => {
    vi.mocked(documentsApi.listAllDocuments).mockResolvedValue({
      items: [doc(1, { project_name: 'Mieszkanie na Mokotowie ul. Bardzo Długa Nazwa Ulicy 12/34 m. 56', number: 'KOSZ/2026/10/01/1200-2' })], total: 40,
    });
    renderScreen();
    await screen.findByLabelText('sent-documents-list');
    expect(screen.getByLabelText('sent-documents-refresh').className).toContain('min-h-11');
    expect(screen.getByLabelText('sent-documents-more').className).toContain('min-h-11');
    expect(screen.getByText(/Mieszkanie na Mokotowie/).parentElement?.className).toContain('break-words');
    expect(screen.getByText('KOSZ/2026/10/01/1200-2').className).toContain('break-all');
  });

  describe('deleting a row of the journal (DJ-1)', () => {
    const open = async (items = [doc(2), doc(1)]) => {
      vi.mocked(documentsApi.listAllDocuments).mockResolvedValue({ items, total: items.length });
      vi.mocked(documentsApi.deleteDocument).mockResolvedValue(undefined);
      renderScreen();
      await screen.findByLabelText('sent-documents-list');
    };

    it('offers the button on a sent and on a failed row and not on one that is still being made', async () => {
      await open([doc(1), doc(2, { status: 'FAILED', error_code: 'INTERRUPTED' }), doc(3, { status: 'PENDING' })]);
      expect(screen.getByLabelText('journal-delete-KOSZ/2026/10/01/1200')).toBeInTheDocument();
      expect(screen.getByLabelText('journal-delete-KOSZ/2026/10/02/1200')).toBeInTheDocument();
      expect(screen.queryByLabelText('journal-delete-KOSZ/2026/10/03/1200')).toBeNull();
      expect(screen.getByLabelText('journal-delete-KOSZ/2026/10/01/1200').className).toContain('min-h-11');
    });

    it('asks first, says what goes and what stays, and sends nothing before the tick and the confirmation', async () => {
      await open();
      fireEvent.click(screen.getByLabelText('journal-delete-KOSZ/2026/10/01/1200'));
      const dialog = await screen.findByRole('alertdialog');
      expect(dialog).toHaveTextContent('Usunąć wpis z dziennika?');
      expect(dialog).toHaveTextContent('Kosztorys KOSZ/2026/10/01/1200');
      expect(dialog).toHaveTextContent('Sam dokument');
      expect(dialog).toHaveTextContent('plik PDF w czacie z botem zostają');
      const confirm = within(dialog).getByLabelText('journal-delete-confirm');
      expect(confirm).toBeDisabled();
      expect(documentsApi.deleteDocument).not.toHaveBeenCalled();
      fireEvent.click(within(dialog).getByLabelText('journal-delete-understood'));
      expect(confirm).toBeEnabled();
    });

    it('deletes on the route of the row\'s own object, takes the row off the list and the number down', async () => {
      await open();
      fireEvent.click(screen.getByLabelText('journal-delete-KOSZ/2026/10/01/1200'));
      const dialog = await screen.findByRole('alertdialog');
      fireEvent.click(within(dialog).getByLabelText('journal-delete-understood'));
      fireEvent.click(within(dialog).getByLabelText('journal-delete-confirm'));
      await waitFor(() => expect(documentsApi.deleteDocument).toHaveBeenCalledWith('p1', 'd1'));
      await waitFor(() => expect(screen.queryByLabelText('document-KOSZ/2026/10/01/1200')).toBeNull());
      expect(screen.getByLabelText('document-KOSZ/2026/10/02/1200')).toBeInTheDocument();
      expect(screen.getByLabelText('sent-documents-shown')).toHaveTextContent('Pokazano 1 z 1');
      expect(screen.getByRole('status')).toHaveTextContent('Wpis usunięty z dziennika.');
      expect(screen.queryByRole('alertdialog')).toBeNull();
    });

    it('cancel closes the question and sends nothing', async () => {
      await open();
      fireEvent.click(screen.getByLabelText('journal-delete-KOSZ/2026/10/01/1200'));
      fireEvent.click(await screen.findByLabelText('journal-delete-cancel'));
      expect(screen.queryByRole('alertdialog')).toBeNull();
      expect(documentsApi.deleteDocument).not.toHaveBeenCalled();
      expect(screen.getByLabelText('document-KOSZ/2026/10/01/1200')).toBeInTheDocument();
    });

    it('says why when the server refuses (the document is still being made) and keeps the row', async () => {
      await open();
      vi.mocked(documentsApi.deleteDocument).mockRejectedValue(new ApiError('x', 409, 'DOCUMENT_IN_PROGRESS'));
      fireEvent.click(screen.getByLabelText('journal-delete-KOSZ/2026/10/01/1200'));
      const dialog = await screen.findByRole('alertdialog');
      fireEvent.click(within(dialog).getByLabelText('journal-delete-understood'));
      fireEvent.click(within(dialog).getByLabelText('journal-delete-confirm'));
      expect(await within(dialog).findByText(/jest jeszcze przygotowywany/)).toBeInTheDocument();
      expect(screen.getByLabelText('document-KOSZ/2026/10/01/1200')).toBeInTheDocument();
      expect(within(dialog).getByLabelText('journal-delete-confirm')).toBeEnabled();
    });

    it('speaks Russian', async () => {
      localStorage.setItem('locale', 'ru');
      await open();
      expect(screen.getByLabelText('journal-delete-KOSZ/2026/10/01/1200')).toHaveTextContent('Удалить из журнала…');
      fireEvent.click(screen.getByLabelText('journal-delete-KOSZ/2026/10/01/1200'));
      expect(await screen.findByRole('alertdialog')).toHaveTextContent('Удалить запись из журнала?');
    });
  });
});
