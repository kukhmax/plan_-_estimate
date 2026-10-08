import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import type { IssuedDocument, PhotoReportSummary } from '../types/document';
import { ProjectDocuments } from './ProjectDocuments';

vi.mock('../api/documents', () => ({
  fetchPhotoReportSummary: vi.fn(),
  listDocuments: vi.fn(),
  issuePhotoReport: vi.fn(),
}));

const SALON = 'r-salon';
const KUCHNIA = 'r-kuchnia';

function summary(over: Partial<PhotoReportSummary> = {}): PhotoReportSummary {
  return {
    photo_count: 5, project_photos: 1, limit: 60, over_limit: false, has_content: true, recommended_count: 0, unpriced_works: [],
    rooms: [
      { room_id: SALON, name: 'Salon', photos: 3, has_inspection_content: true },
      { room_id: KUCHNIA, name: 'Kuchnia', photos: 1, has_inspection_content: false },
    ],
    ...over,
  };
}

function doc(over: Partial<IssuedDocument> = {}): IssuedDocument {
  return {
    id: 'd1', project_id: 'p1', kind: 'ESTIMATE', source_id: 'e1', source_version: 1, title: 'Kosztorys', number: 'KOSZ/2026/10/08/1953',
    project_seq: 1, template_version: '1', status: 'SENT', error_code: null, scope: null, pages: 2, byte_size: 123_456,
    issued_at: '2026-10-08T17:53:00Z', sent_at: '2026-10-08T17:53:20Z', ...over,
  };
}

function renderCard() {
  return render(<I18nProvider><ProjectDocuments projectId="p1" /></I18nProvider>);
}

async function open() {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'toggle-project-documents' })); });
}

describe('ProjectDocuments (Stage 15F.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(documentsApi.fetchPhotoReportSummary).mockResolvedValue(summary());
    vi.mocked(documentsApi.listDocuments).mockResolvedValue({ items: [], total: 0 });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('is closed and silent until it is opened, with a touch-sized toggle', async () => {
    renderCard();
    expect(documentsApi.fetchPhotoReportSummary).not.toHaveBeenCalled();
    const toggle = screen.getByRole('button', { name: 'toggle-project-documents' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle.className).toContain('min-h-11');
    await open();
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(documentsApi.fetchPhotoReportSummary).toHaveBeenCalledWith('p1');
    expect(await screen.findByText('Zdjęć w raporcie: 5 (limit 60)')).toBeInTheDocument();
  });

  it('sends the whole report with one tap and shows the new row of the journal', async () => {
    vi.mocked(documentsApi.issuePhotoReport).mockResolvedValue(doc({ kind: 'PHOTO_REPORT', status: 'PENDING', number: 'FOTO/2026/10/08/1953', pages: null, byte_size: null }));
    vi.mocked(documentsApi.listDocuments).mockResolvedValueOnce({ items: [], total: 0 }).mockResolvedValue({
      items: [doc({ kind: 'PHOTO_REPORT', status: 'PENDING', number: 'FOTO/2026/10/08/1953', pages: null, byte_size: null })], total: 1 });
    renderCard();
    await open();
    await screen.findByLabelText('send-photo-report');
    await act(async () => { fireEvent.click(screen.getByLabelText('send-photo-report')); });
    expect(documentsApi.issuePhotoReport).toHaveBeenCalledWith('p1', undefined);
    const row = await screen.findByLabelText('document-FOTO/2026/10/08/1953');
    expect(within(row).getByText('Raport fotograficzny')).toBeInTheDocument();
    expect(within(row).getByText('Wysyłanie…')).toBeInTheDocument();
    expect(screen.queryByLabelText('send-photo-report-part')).toBeNull();
  });

  it('follows a running document until it ends and then stops asking', async () => {
    vi.useFakeTimers();
    vi.mocked(documentsApi.listDocuments)
      .mockResolvedValueOnce({ items: [doc({ status: 'PENDING', pages: null, byte_size: null })], total: 1 })
      .mockResolvedValueOnce({ items: [doc({ status: 'PENDING', pages: null, byte_size: null })], total: 1 })
      .mockResolvedValue({ items: [doc()], total: 1 });
    renderCard();
    await open();
    expect(screen.getByText('Wysyłanie…')).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
    expect(screen.getByText('Wysyłanie…')).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
    expect(screen.getByText('Wysłano')).toBeInTheDocument();
    const calls = vi.mocked(documentsApi.listDocuments).mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(vi.mocked(documentsApi.listDocuments).mock.calls.length).toBe(calls);
  });

  it('shows what was sent: kind, number, running number, date, pages and size; a failed one with its reason', async () => {
    vi.mocked(documentsApi.listDocuments).mockResolvedValue({
      items: [
        doc({ id: 'd2', number: 'KOSZ/2026/10/08/1953-2', project_seq: 2, status: 'FAILED', error_code: 'TELEGRAM_CHAT_UNAVAILABLE', pages: null, byte_size: null }),
        doc(),
      ],
      total: 2,
    });
    renderCard();
    await open();
    const sent = await screen.findByLabelText('document-KOSZ/2026/10/08/1953');
    expect(within(sent).getByText('Kosztorys')).toBeInTheDocument();
    expect(sent).toHaveTextContent('Nr kolejny: 1');
    expect(sent).toHaveTextContent('08.10.2026');
    expect(sent).toHaveTextContent('2 str.');
    expect(sent).toHaveTextContent('123 KB');
    const failed = screen.getByLabelText('document-KOSZ/2026/10/08/1953-2');
    expect(within(failed).getByText('Nie wysłano')).toBeInTheDocument();
    expect(failed).toHaveTextContent('naciśnij Start');
  });

  it('says so when there is nothing to send', async () => {
    vi.mocked(documentsApi.fetchPhotoReportSummary).mockResolvedValue(summary({ photo_count: 0, project_photos: 0, has_content: false, rooms: [] }));
    renderCard();
    await open();
    expect(await screen.findByText('Brak zdjęć zaznaczonych do raportu i zakończonych badań.')).toBeInTheDocument();
    expect(screen.queryByLabelText('send-photo-report')).toBeNull();
    expect(screen.getByText('Nic jeszcze nie wysłano.')).toBeInTheDocument();
  });

  it('over the limit offers the rooms, counts the choice and sends only a part that fits', async () => {
    vi.mocked(documentsApi.fetchPhotoReportSummary).mockResolvedValue(summary({
      photo_count: 70, project_photos: 4, limit: 60, over_limit: true,
      rooms: [
        { room_id: SALON, name: 'Salon', photos: 40, has_inspection_content: true },
        { room_id: KUCHNIA, name: 'Kuchnia', photos: 26, has_inspection_content: false },
      ],
    }));
    vi.mocked(documentsApi.issuePhotoReport).mockResolvedValue(doc({ kind: 'PHOTO_REPORT', status: 'PENDING' }));
    renderCard();
    await open();
    await screen.findByText(/Zdjęć jest za dużo na jeden dokument \(70 > 60\)/);
    expect(screen.queryByLabelText('send-photo-report')).toBeNull();
    const send = screen.getByLabelText('send-photo-report-part');
    expect(send).toBeDisabled();
    expect(screen.getByText('Zaznacz co najmniej jedno pomieszczenie.')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Salon — 40'));
    expect(screen.getByText('Wybrano: 40 / 60')).toBeInTheDocument();
    expect(send).toBeEnabled();
    fireEvent.click(screen.getByLabelText('Kuchnia — 26'));
    expect(screen.getByText(/Wybrano: 66 \/ 60/)).toHaveTextContent('Wybrano za dużo zdjęć');
    expect(send).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Kuchnia — 26'));
    fireEvent.click(screen.getByLabelText('Dołącz zdjęcia ogólne obiektu (4)'));
    expect(screen.getByText('Wybrano: 44 / 60')).toBeInTheDocument();
    await act(async () => { fireEvent.click(send); });
    expect(documentsApi.issuePhotoReport).toHaveBeenCalledWith('p1', { room_ids: [SALON], include_project_photos: true });
  });

  it('sends a part without the general photos of the object unless they were ticked', async () => {
    vi.mocked(documentsApi.fetchPhotoReportSummary).mockResolvedValue(summary({ photo_count: 90, over_limit: true }));
    vi.mocked(documentsApi.issuePhotoReport).mockResolvedValue(doc({ kind: 'PHOTO_REPORT', status: 'PENDING' }));
    renderCard();
    await open();
    fireEvent.click(await screen.findByLabelText('Kuchnia — 1'));
    await act(async () => { fireEvent.click(screen.getByLabelText('send-photo-report-part')); });
    expect(documentsApi.issuePhotoReport).toHaveBeenCalledWith('p1', { room_ids: [KUCHNIA], include_project_photos: false });
  });

  it('says how many recommended extra works the report lists', async () => {
    vi.mocked(documentsApi.fetchPhotoReportSummary).mockResolvedValue(summary({ recommended_count: 2 }));
    renderCard();
    await open();
    expect(await screen.findByText('Rekomendowane prace dodatkowe: 2')).toBeInTheDocument();
    expect(screen.queryByLabelText('unpriced-works')).toBeNull();
    expect(screen.getByLabelText('send-photo-report')).toBeEnabled();
  });

  it('names the recommended works without a price and does not offer to send until they are settled', async () => {
    vi.mocked(documentsApi.fetchPhotoReportSummary).mockResolvedValue(summary({
      recommended_count: 2, unpriced_works: ['Salon › Ściana A: Gruntowanie gruntem penetrującym (pod szpachlowanie)'] }));
    renderCard();
    await open();
    const alert = await screen.findByLabelText('unpriced-works');
    expect(alert).toHaveTextContent('Brak ceny w kosztorysie — dokument nie zostanie wysłany:');
    expect(alert).toHaveTextContent('Salon › Ściana A: Gruntowanie gruntem penetrującym');
    expect(alert).toHaveTextContent('Zaakceptuj zalecenie w badaniu');
    expect(screen.getByLabelText('send-photo-report')).toBeDisabled();
  });

  it('blocks the part of a report too, and shows the server\'s list when it refuses', async () => {
    vi.mocked(documentsApi.fetchPhotoReportSummary).mockResolvedValue(summary({ photo_count: 90, over_limit: true, unpriced_works: ['Salon › Ściana A: X'] }));
    renderCard();
    await open();
    fireEvent.click(await screen.findByLabelText('Kuchnia — 1'));
    expect(screen.getByLabelText('send-photo-report-part')).toBeDisabled();
  });

  it('every room line is a touch-sized control', async () => {
    vi.mocked(documentsApi.fetchPhotoReportSummary).mockResolvedValue(summary({ over_limit: true, photo_count: 90 }));
    renderCard();
    await open();
    await screen.findByLabelText('Salon — 3');
    for (const name of ['Salon — 3', 'Kuchnia — 1']) {
      expect(screen.getByLabelText(name).closest('label')?.className).toContain('min-h-11');
    }
    expect(screen.getByLabelText('send-photo-report-part').className).toContain('min-h-11');
  });

  it('shows the reason of a refusal by its code and keeps the card usable', async () => {
    vi.mocked(documentsApi.issuePhotoReport).mockRejectedValue(new ApiError('English', 422, 'EXECUTOR_PROFILE_REQUIRED', {}));
    renderCard();
    await open();
    await act(async () => { fireEvent.click(await screen.findByLabelText('send-photo-report')); });
    expect(screen.getByLabelText('photo-report-error')).toHaveTextContent('Uzupełnij profil wykonawcy');
    expect(screen.queryByText('English')).toBeNull();
    expect(screen.getByLabelText('send-photo-report')).toBeEnabled();
  });

  it('offers a retry when the first load fails', async () => {
    vi.mocked(documentsApi.fetchPhotoReportSummary).mockRejectedValueOnce(new Error('net')).mockResolvedValue(summary());
    renderCard();
    await open();
    expect(await screen.findByText('Nie udało się wczytać dokumentów.')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' })); });
    expect(await screen.findByText('Zdjęć w raporcie: 5 (limit 60)')).toBeInTheDocument();
  });

  it('is localised in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(documentsApi.listDocuments).mockResolvedValue({ items: [doc({ status: 'FAILED', error_code: 'DELIVERY_DISABLED' })], total: 1 });
    renderCard();
    expect(screen.getByText('PDF-документы')).toBeInTheDocument();
    await open();
    expect(await screen.findByText('Фото в отчёте: 5 (лимит 60)')).toBeInTheDocument();
    expect(screen.getByText('Не отправлено')).toBeInTheDocument();
    expect(screen.getByText('Отправка документов на этом сервере отключена.')).toBeInTheDocument();
  });
});
