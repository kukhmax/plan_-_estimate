import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import type { IssuedDocument } from '../types/document';
import { EstimateDocumentActions } from './EstimateDocumentActions';

vi.mock('../api/documents', () => ({
  issueEstimateDocument: vi.fn(),
  getDocument: vi.fn(),
  previewEstimatePdf: vi.fn(),
}));

function document(over: Partial<IssuedDocument> = {}): IssuedDocument {
  return {
    id: 'd1', project_id: 'p1', kind: 'ESTIMATE', source_id: 'e1', source_version: 1, title: 'Kosztorys — wersja 1',
    number: 'KOSZ/2026/10/08/1953', project_seq: 1, template_version: '1', status: 'PENDING', error_code: null, scope: null,
    pages: null, byte_size: null, issued_at: '2026-10-08T17:53:00Z', sent_at: null, ...over,
  };
}

function renderActions(status: 'DRAFT' | 'FINAL' | 'ACCEPTED' | 'ARCHIVED' = 'FINAL') {
  return render(
    <I18nProvider>
      <EstimateDocumentActions projectId="p1" estimateId="e1" status={status} />
    </I18nProvider>,
  );
}

async function press(name: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name }));
  });
}

describe('EstimateDocumentActions (Stage 15F.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('offers "Wyślij PDF" for a finished estimate and "Podgląd PDF" for a draft, and nothing for an archived one', () => {
    const { unmount } = renderActions('FINAL');
    expect(screen.getByRole('button', { name: 'estimate-send-pdf' })).toHaveTextContent('Wyślij PDF');
    expect(screen.queryByRole('button', { name: 'estimate-preview-pdf' })).toBeNull();
    unmount();
    const draft = renderActions('DRAFT');
    expect(screen.getByRole('button', { name: 'estimate-preview-pdf' })).toHaveTextContent('Podgląd PDF (wersja robocza)');
    draft.unmount();
    expect(renderActions('ACCEPTED').container).not.toBeEmptyDOMElement();
    const archived = renderActions('ARCHIVED');
    expect(archived.container.querySelector('[aria-label="estimate-documents"]')).toBeNull();
  });

  it('is a mobile-sized control that says where the file goes', () => {
    renderActions('FINAL');
    expect(screen.getByRole('button', { name: 'estimate-send-pdf' }).className).toContain('min-h-[44px]');
    expect(screen.getByText('Plik PDF trafi do czatu z botem.')).toBeInTheDocument();
  });

  it('issues, follows the document and reports the number when it was sent', async () => {
    vi.mocked(documentsApi.issueEstimateDocument).mockResolvedValue(document());
    vi.mocked(documentsApi.getDocument).mockResolvedValueOnce(document()).mockResolvedValueOnce(document({ status: 'SENT', pages: 1, byte_size: 9000 }));
    renderActions('FINAL');
    await press('estimate-send-pdf');
    expect(documentsApi.issueEstimateDocument).toHaveBeenCalledWith('p1', 'e1');
    expect(screen.getByLabelText('estimate-document-working')).toHaveTextContent('KOSZ/2026/10/08/1953');
    expect(screen.getByRole('button', { name: 'estimate-send-pdf' })).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(screen.getByLabelText('estimate-document-working')).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(screen.getByLabelText('estimate-document-sent')).toHaveTextContent('Wysłano do czatu z botem: KOSZ/2026/10/08/1953');
    expect(screen.getByRole('button', { name: 'estimate-send-pdf' })).toBeEnabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(documentsApi.getDocument).toHaveBeenCalledTimes(2); // it stops asking once the document ended
  });

  it('says why a document was not sent, in words, by the code of the failed row', async () => {
    vi.mocked(documentsApi.issueEstimateDocument).mockResolvedValue(document());
    vi.mocked(documentsApi.getDocument).mockResolvedValue(document({ status: 'FAILED', error_code: 'TELEGRAM_CHAT_UNAVAILABLE' }));
    renderActions('FINAL');
    await press('estimate-send-pdf');
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    const failed = screen.getByLabelText('estimate-document-failed');
    expect(failed).toHaveTextContent('Nie wysłano dokumentu KOSZ/2026/10/08/1953.');
    expect(failed).toHaveTextContent('naciśnij Start');
  });

  it('shows the words of a refusal made in the request, by its code', async () => {
    vi.mocked(documentsApi.issueEstimateDocument).mockRejectedValue(new ApiError('English', 422, 'EXECUTOR_PROFILE_REQUIRED', {}));
    renderActions('FINAL');
    await press('estimate-send-pdf');
    expect(screen.getByLabelText('estimate-document-error')).toHaveTextContent('Uzupełnij profil wykonawcy');
    expect(screen.queryByText('English')).toBeNull();
    expect(screen.getByRole('button', { name: 'estimate-send-pdf' })).toBeEnabled();
  });

  it('sends the preview of a draft at once and says so', async () => {
    vi.mocked(documentsApi.previewEstimatePdf).mockResolvedValue({ sent: true, pages: 1, byte_size: 9000 });
    renderActions('DRAFT');
    await press('estimate-preview-pdf');
    expect(documentsApi.previewEstimatePdf).toHaveBeenCalledWith('p1', 'e1');
    expect(documentsApi.issueEstimateDocument).not.toHaveBeenCalled();
    expect(screen.getByLabelText('estimate-preview-sent')).toHaveTextContent('Podgląd wysłany do czatu z botem.');
  });

  it('does not start a second request while one is running', async () => {
    let release: (value: IssuedDocument) => void = () => undefined;
    vi.mocked(documentsApi.issueEstimateDocument).mockReturnValue(new Promise((resolve) => { release = resolve; }));
    renderActions('FINAL');
    await press('estimate-send-pdf');
    fireEvent.click(screen.getByRole('button', { name: 'estimate-send-pdf' }));
    expect(documentsApi.issueEstimateDocument).toHaveBeenCalledTimes(1);
    await act(async () => { release(document({ status: 'SENT' })); });
  });

  it('is localised in Russian', () => {
    localStorage.setItem('locale', 'ru');
    renderActions('FINAL');
    expect(screen.getByRole('button', { name: 'estimate-send-pdf' })).toHaveTextContent('Отправить PDF');
    expect(screen.getByText('PDF-файл придёт в чат с ботом.')).toBeInTheDocument();
  });
});
