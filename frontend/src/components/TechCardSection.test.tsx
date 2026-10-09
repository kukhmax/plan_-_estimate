import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { TechCardSection } from './TechCardSection';

vi.mock('../api/documents', () => ({
  issueTechCard: vi.fn(),
  previewTechCardPdf: vi.fn(),
}));

const onIssued = vi.fn();

function renderSection() {
  return render(<I18nProvider><TechCardSection projectId="p1" onIssued={onIssued} /></I18nProvider>);
}

const press = async (name: string) => {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name })); });
};

describe('TechCardSection (Stage 16C)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });
  afterEach(cleanup);

  it('offers the working version with empty fields and the numbered card as two full-width, touch-sized actions', () => {
    renderSection();
    expect(screen.getByText('Karta technologiczna')).toBeInTheDocument();
    for (const name of ['preview-tech-card', 'send-tech-card']) {
      const button = screen.getByRole('button', { name });
      expect(button.className).toContain('min-h-11');
      expect(button.className).toContain('w-full');
    }
    expect(screen.getByRole('button', { name: 'preview-tech-card' })).toHaveTextContent('Wersja robocza do wydruku (puste pola)');
  });

  it('sends the working version to the chat and says what to do with it', async () => {
    vi.mocked(documentsApi.previewTechCardPdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 9000 });
    renderSection();
    await press('preview-tech-card');
    expect(documentsApi.previewTechCardPdf).toHaveBeenCalledWith('p1');
    expect(await screen.findByLabelText('tech-card-note')).toHaveTextContent('Wersja robocza wysłana do czatu z botem');
    expect(documentsApi.issueTechCard).not.toHaveBeenCalled();
    expect(onIssued).not.toHaveBeenCalled();
  });

  it('starts the numbered card and tells the card of documents to follow the journal', async () => {
    vi.mocked(documentsApi.issueTechCard).mockResolvedValue({} as never);
    renderSection();
    await press('send-tech-card');
    expect(documentsApi.issueTechCard).toHaveBeenCalledWith('p1');
    expect(onIssued).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('names every surface that lacks something, in the language of the interface, and keeps the preview within reach', async () => {
    const items = [
      { room: 'Salon', surface: 'Wall 1', surface_type: 'WALL', missing: ['QUALITY_TARGET'] },
      { room: 'Kuchnia', surface: 'Floor', surface_type: 'FLOOR', missing: ['QUALITY_TARGET', 'INSPECTION'] },
    ];
    vi.mocked(documentsApi.issueTechCard).mockRejectedValue(new ApiError('English', 422, 'TECH_CARD_INCOMPLETE', { code: 'TECH_CARD_INCOMPLETE', details: { items } }));
    renderSection();
    await press('send-tech-card');
    expect(await screen.findByLabelText('tech-card-error')).toHaveTextContent('Wersję roboczą z pustymi polami możesz wydrukować już teraz');
    const list = screen.getByLabelText('tech-card-missing');
    expect(within(list).getByText('Salon › Ściana 1')).toBeInTheDocument();
    expect(list).toHaveTextContent('ustal docelowy standard wykończenia (plan prac); zakończ badanie podłoża');
    expect(screen.getByRole('button', { name: 'preview-tech-card' })).toBeEnabled();
    expect(onIssued).not.toHaveBeenCalled();
  });

  it('shows the same list in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    const items = [{ room: 'Salon', surface: 'Wall 1', surface_type: 'WALL', missing: ['INSPECTION'] }];
    vi.mocked(documentsApi.issueTechCard).mockRejectedValue(new ApiError('English', 422, 'TECH_CARD_INCOMPLETE', { code: 'TECH_CARD_INCOMPLETE', details: { items } }));
    renderSection();
    await press('send-tech-card');
    const list = await screen.findByLabelText('tech-card-missing');
    expect(list).toHaveTextContent('Salon › Стена 1');
    expect(list).toHaveTextContent('завершите осмотр основания');
    expect(screen.getByLabelText('tech-card-error')).toHaveTextContent('Рабочую версию с пустыми полями');
  });

  it('says there is nothing planned yet when no surface has works', async () => {
    vi.mocked(documentsApi.issueTechCard).mockRejectedValue(new ApiError('English', 422, 'TECH_CARD_EMPTY', { code: 'TECH_CARD_EMPTY', details: null }));
    renderSection();
    await press('send-tech-card');
    expect(await screen.findByLabelText('tech-card-error')).toHaveTextContent('Żadna powierzchnia nie ma jeszcze zaplanowanych prac');
    expect(screen.queryByLabelText('tech-card-missing')).toBeNull();
  });

  it('ignores a second tap while the first is running', async () => {
    let finish: () => void = () => {};
    vi.mocked(documentsApi.previewTechCardPdf).mockReturnValue(new Promise((resolve) => { finish = () => resolve({ sent: true, pages: 1, byte_size: 1 }); }));
    renderSection();
    await press('preview-tech-card');
    expect(screen.getByRole('button', { name: 'preview-tech-card' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'send-tech-card' })).toBeDisabled();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'preview-tech-card' })); });
    expect(documentsApi.previewTechCardPdf).toHaveBeenCalledTimes(1);
    await act(async () => { finish(); });
  });

  it('shows a chat error with its own sentence, not the English text', async () => {
    vi.mocked(documentsApi.previewTechCardPdf).mockRejectedValue(new ApiError('English text', 409, 'TELEGRAM_CHAT_UNAVAILABLE', { code: 'TELEGRAM_CHAT_UNAVAILABLE' }));
    renderSection();
    await press('preview-tech-card');
    const alert = await screen.findByLabelText('tech-card-error');
    expect(alert).toHaveTextContent('Bot nie może napisać na Twój czat');
    expect(alert).not.toHaveTextContent('English text');
  });
});
