import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { MeasurementsSection, PaymentScheduleSection, ProductionPlanSection, SettlementSection, TechCardSection } from './TechCardSection';

vi.mock('../api/documents', () => ({
  issueTechCard: vi.fn(),
  previewTechCardPdf: vi.fn(),
  issueProductionPlan: vi.fn(),
  previewProductionPlanPdf: vi.fn(),
  issueSettlement: vi.fn(),
  previewSettlementPdf: vi.fn(),
  issueMeasurements: vi.fn(),
  previewMeasurementsPdf: vi.fn(),
  issuePaymentSchedule: vi.fn(),
  previewPaymentSchedulePdf: vi.fn(),
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

describe('ProductionPlanSection (Stage 16D.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });
  afterEach(cleanup);

  const renderPlan = () => render(<I18nProvider><ProductionPlanSection projectId="p1" onIssued={onIssued} /></I18nProvider>);

  it('offers the working version and the numbered plan as two full-width, touch-sized actions', () => {
    renderPlan();
    expect(screen.getByText('Plan produkcji prac')).toBeInTheDocument();
    for (const name of ['preview-production-plan', 'send-production-plan']) {
      const button = screen.getByRole('button', { name });
      expect(button.className).toContain('min-h-11');
      expect(button.className).toContain('w-full');
    }
    expect(screen.getByRole('button', { name: 'preview-production-plan' })).toHaveTextContent('Wersja robocza do wydruku (puste pola)');
    expect(screen.getByRole('button', { name: 'send-production-plan' })).toHaveTextContent('Wyślij plan (PDF)');
  });

  it('sends the working version to the chat and calls only the plan routes', async () => {
    vi.mocked(documentsApi.previewProductionPlanPdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 9000 });
    renderPlan();
    await press('preview-production-plan');
    expect(documentsApi.previewProductionPlanPdf).toHaveBeenCalledWith('p1');
    expect(await screen.findByLabelText('production-plan-note')).toHaveTextContent('Wersja robocza wysłana do czatu z botem');
    expect(documentsApi.previewTechCardPdf).not.toHaveBeenCalled();
    expect(documentsApi.issueProductionPlan).not.toHaveBeenCalled();
  });

  it('starts the numbered plan and tells the card of documents to follow the journal', async () => {
    vi.mocked(documentsApi.issueProductionPlan).mockResolvedValue({} as never);
    renderPlan();
    await press('send-production-plan');
    expect(documentsApi.issueProductionPlan).toHaveBeenCalledWith('p1');
    expect(documentsApi.issueTechCard).not.toHaveBeenCalled();
    expect(onIssued).toHaveBeenCalledTimes(1);
  });

  it('says in words that nothing is planned yet, in Polish and in Russian', async () => {
    vi.mocked(documentsApi.issueProductionPlan).mockRejectedValue(new ApiError('English', 422, 'PRODUCTION_PLAN_EMPTY', { code: 'PRODUCTION_PLAN_EMPTY', details: null }));
    renderPlan();
    await press('send-production-plan');
    expect(await screen.findByLabelText('production-plan-error')).toHaveTextContent('Żadna powierzchnia nie ma jeszcze zaplanowanych prac');
    expect(onIssued).not.toHaveBeenCalled();
    cleanup();
    localStorage.setItem('locale', 'ru');
    renderPlan();
    expect(screen.getByText('План производства работ')).toBeInTheDocument();
    await press('send-production-plan');
    expect(await screen.findByLabelText('production-plan-error')).toHaveTextContent('Ни у одной поверхности пока нет запланированных работ');
  });

  it('ignores a second tap while the first is running', async () => {
    let finish: () => void = () => {};
    vi.mocked(documentsApi.previewProductionPlanPdf).mockReturnValue(new Promise((resolve) => { finish = () => resolve({ sent: true, pages: 1, byte_size: 1 }); }));
    renderPlan();
    await press('preview-production-plan');
    expect(screen.getByRole('button', { name: 'send-production-plan' })).toBeDisabled();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'preview-production-plan' })); });
    expect(documentsApi.previewProductionPlanPdf).toHaveBeenCalledTimes(1);
    await act(async () => { finish(); });
  });
});

describe('SettlementSection (IA-6a)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });
  afterEach(cleanup);

  const renderStatement = () => render(<I18nProvider><SettlementSection projectId="p1" onIssued={onIssued} /></I18nProvider>);

  it('says what the statement is and that the expenses are not in it, with two full-width touch-sized actions', () => {
    renderStatement();
    expect(screen.getByText('Rozliczenie dla klienta')).toBeInTheDocument();
    expect(screen.getByText(/Wydatki na materiały nie trafiają do tego dokumentu/)).toBeInTheDocument();
    for (const name of ['preview-settlement', 'send-settlement']) {
      const button = screen.getByRole('button', { name });
      expect(button.className).toContain('min-h-11');
      expect(button.className).toContain('w-full');
    }
  });

  it('sends the working version to the chat and nothing else', async () => {
    vi.mocked(documentsApi.previewSettlementPdf).mockResolvedValue({ sent: true, pages: 1, byte_size: 9000 });
    renderStatement();
    await press('preview-settlement');
    expect(documentsApi.previewSettlementPdf).toHaveBeenCalledWith('p1');
    expect(await screen.findByLabelText('settlement-note')).toHaveTextContent('Wersja robocza wysłana do czatu z botem');
    expect(documentsApi.issueSettlement).not.toHaveBeenCalled();
    expect(documentsApi.issueTechCard).not.toHaveBeenCalled();
    expect(onIssued).not.toHaveBeenCalled();
  });

  it('starts the numbered statement and tells the journal to follow it', async () => {
    vi.mocked(documentsApi.issueSettlement).mockResolvedValue({} as never);
    renderStatement();
    await press('send-settlement');
    expect(documentsApi.issueSettlement).toHaveBeenCalledWith('p1');
    expect(documentsApi.previewSettlementPdf).not.toHaveBeenCalled();
    expect(onIssued).toHaveBeenCalledTimes(1);
  });

  it('answers an empty object with the words of its code, in both languages, and no list of missing surfaces', async () => {
    vi.mocked(documentsApi.issueSettlement).mockRejectedValue(new ApiError('Request failed', 422, 'SETTLEMENT_EMPTY', { code: 'SETTLEMENT_EMPTY' }));
    renderStatement();
    await press('send-settlement');
    expect(await screen.findByLabelText('settlement-error')).toHaveTextContent('Obiekt nie ma jeszcze faktur ani wpłat do rozliczenia');
    expect(screen.queryByLabelText('settlement-missing')).toBeNull();
    expect(onIssued).not.toHaveBeenCalled();
    cleanup();
    localStorage.setItem('locale', 'ru');
    renderStatement();
    await press('send-settlement');
    expect(await screen.findByLabelText('settlement-error')).toHaveTextContent('В объекте пока нет фактур и оплат для расчёта');
  });

  it('works only on its own button: a card or a plan never calls the statement', async () => {
    vi.mocked(documentsApi.previewTechCardPdf).mockResolvedValue({ sent: true, pages: 1, byte_size: 1 });
    renderSection();
    await press('preview-tech-card');
    expect(documentsApi.previewSettlementPdf).not.toHaveBeenCalled();
  });
});

describe('MeasurementsSection (V2-8c)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });
  afterEach(cleanup);

  const renderMeasurements = () => render(<I18nProvider><MeasurementsSection projectId="p1" onIssued={onIssued} /></I18nProvider>);

  it('says what the document holds and offers two full-width touch-sized actions', () => {
    renderMeasurements();
    expect(screen.getByText('Obmiar obiektu dla klienta')).toBeInTheDocument();
    expect(screen.getByText(/Liczby są takie same jak na ekranach aplikacji/)).toBeInTheDocument();
    for (const name of ['preview-measurements', 'send-measurements']) {
      const button = screen.getByRole('button', { name });
      expect(button.className).toContain('min-h-11');
      expect(button.className).toContain('w-full');
    }
  });

  it('sends the working version to the chat and nothing else', async () => {
    vi.mocked(documentsApi.previewMeasurementsPdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 17000 });
    renderMeasurements();
    await press('preview-measurements');
    expect(documentsApi.previewMeasurementsPdf).toHaveBeenCalledWith('p1', false);
    expect(await screen.findByLabelText('measurements-note')).toHaveTextContent('Wersja robocza wysłana do czatu z botem');
    expect(documentsApi.issueMeasurements).not.toHaveBeenCalled();
    expect(onIssued).not.toHaveBeenCalled();
  });

  it('starts the numbered document and tells the journal to follow it', async () => {
    vi.mocked(documentsApi.issueMeasurements).mockResolvedValue({} as never);
    renderMeasurements();
    await press('send-measurements');
    expect(documentsApi.issueMeasurements).toHaveBeenCalledWith('p1', false);
    expect(documentsApi.previewMeasurementsPdf).not.toHaveBeenCalled();
    expect(onIssued).toHaveBeenCalledTimes(1);
  });

  it('offers "Dodaj zdjęcia" off by default as a touch-sized checkbox and sends the choice with both buttons (V2-8d)', async () => {
    vi.mocked(documentsApi.previewMeasurementsPdf).mockResolvedValue({ sent: true, pages: 3, byte_size: 99000 });
    vi.mocked(documentsApi.issueMeasurements).mockResolvedValue({} as never);
    renderMeasurements();
    const box = screen.getByRole('checkbox', { name: /Dodaj zdjęcia/ });
    expect(box).not.toBeChecked();
    expect(box.closest('label')?.className).toContain('min-h-11');
    expect(screen.getByText(/trafią do PDF pod ich wymiarami/)).toBeInTheDocument();
    fireEvent.click(box);
    expect(box).toBeChecked();
    await press('preview-measurements');
    expect(documentsApi.previewMeasurementsPdf).toHaveBeenLastCalledWith('p1', true);
    await press('send-measurements');
    expect(documentsApi.issueMeasurements).toHaveBeenLastCalledWith('p1', true);
    fireEvent.click(box);
    await press('send-measurements');
    expect(documentsApi.issueMeasurements).toHaveBeenLastCalledWith('p1', false);
  });

  it('has the checkbox only for the measurements', () => {
    renderSection();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('explains too many photos with the counts, in four languages', async () => {
    vi.mocked(documentsApi.issueMeasurements).mockRejectedValue(
      new ApiError('Request failed', 422, 'MEASUREMENTS_PHOTO_LIMIT_EXCEEDED', { code: 'MEASUREMENTS_PHOTO_LIMIT_EXCEEDED', details: { count: 73, limit: 60 } }),
    );
    for (const [lang, words] of [
      ['pl', 'Zdjęć powierzchni jest za dużo na jeden dokument (73 > 60)'],
      ['ru', 'Фото поверхностей слишком много для одного документа (73 > 60)'],
      ['uk', 'Фото поверхонь забагато для одного документа (73 > 60)'],
      ['en', 'There are too many surface photos for one document (73 > 60)'],
    ] as const) {
      localStorage.setItem('locale', lang);
      renderMeasurements();
      await press('send-measurements');
      expect(await screen.findByLabelText('measurements-error')).toHaveTextContent(words);
      cleanup();
    }
  });

  it('answers an object without a room with the words of its code, in four languages', async () => {
    vi.mocked(documentsApi.issueMeasurements).mockRejectedValue(new ApiError('Request failed', 422, 'MEASUREMENTS_EMPTY', { code: 'MEASUREMENTS_EMPTY' }));
    for (const [lang, words] of [
      ['pl', 'Obiekt nie ma jeszcze pomieszczeń do obmiaru'],
      ['ru', 'В объекте пока нет помещений для обмеров'],
      ['uk', 'В об’єкті ще немає приміщень для обмірів'],
      ['en', 'The property has no room to measure yet'],
    ] as const) {
      localStorage.setItem('locale', lang);
      renderMeasurements();
      await press('send-measurements');
      expect(await screen.findByLabelText('measurements-error')).toHaveTextContent(words);
      cleanup();
    }
    expect(onIssued).not.toHaveBeenCalled();
  });

  it('works only on its own buttons: a card or a statement never calls the measurements', async () => {
    vi.mocked(documentsApi.previewTechCardPdf).mockResolvedValue({ sent: true, pages: 1, byte_size: 1 });
    renderSection();
    await press('preview-tech-card');
    expect(documentsApi.previewMeasurementsPdf).not.toHaveBeenCalled();
  });
});

describe('PaymentScheduleSection (V2-9a)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });
  afterEach(cleanup);

  const renderSchedule = () => render(<I18nProvider><PaymentScheduleSection projectId="p1" onIssued={onIssued} /></I18nProvider>);

  it('says what the document holds (and what it never holds) and offers two full-width touch-sized actions, no photos checkbox', () => {
    renderSchedule();
    expect(screen.getByText('Harmonogram płatności dla klienta')).toBeInTheDocument();
    expect(screen.getByText(/Twoje wydatki, godziny i marża nie trafiają do dokumentu/)).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).toBeNull();
    for (const name of ['preview-payment-schedule', 'send-payment-schedule']) {
      const button = screen.getByRole('button', { name });
      expect(button.className).toContain('min-h-11');
      expect(button.className).toContain('w-full');
    }
    expect(screen.getByRole('button', { name: 'send-payment-schedule' })).toHaveTextContent('Wyślij harmonogram (PDF)');
  });

  it('sends the working version to the chat and nothing else', async () => {
    vi.mocked(documentsApi.previewPaymentSchedulePdf).mockResolvedValue({ sent: true, pages: 1, byte_size: 9000 });
    renderSchedule();
    await press('preview-payment-schedule');
    expect(documentsApi.previewPaymentSchedulePdf).toHaveBeenCalledWith('p1');
    expect(await screen.findByLabelText('payment-schedule-note')).toHaveTextContent('Wersja robocza wysłana do czatu z botem');
    expect(documentsApi.issuePaymentSchedule).not.toHaveBeenCalled();
    expect(onIssued).not.toHaveBeenCalled();
  });

  it('starts the numbered document and tells the journal to follow it', async () => {
    vi.mocked(documentsApi.issuePaymentSchedule).mockResolvedValue({} as never);
    renderSchedule();
    await press('send-payment-schedule');
    expect(documentsApi.issuePaymentSchedule).toHaveBeenCalledWith('p1');
    expect(documentsApi.previewPaymentSchedulePdf).not.toHaveBeenCalled();
    expect(onIssued).toHaveBeenCalledTimes(1);
  });

  it('answers an object without a stage and a stage without a known amount with the words of the code, in four languages', async () => {
    for (const [lang, empty, unpriced] of [
      ['pl', 'Obiekt nie ma jeszcze etapów płatności', 'Etap jest udziałem w umówionej kwocie, której jeszcze nie ustawiono (2)'],
      ['ru', 'В объекте пока нет этапов платежей', 'Этап задан долей договорной суммы, которую ещё не указали (2)'],
      ['uk', 'В об’єкті ще немає етапів платежів', 'Етап задано часткою домовленої суми, яку ще не вказано (2)'],
      ['en', 'The property has no payment stage yet', 'A stage is a share of an agreed amount that is not set yet (2)'],
    ] as const) {
      localStorage.setItem('locale', lang);
      vi.mocked(documentsApi.issuePaymentSchedule).mockRejectedValueOnce(new ApiError('Request failed', 422, 'PAYMENT_SCHEDULE_EMPTY', { code: 'PAYMENT_SCHEDULE_EMPTY' }));
      renderSchedule();
      await press('send-payment-schedule');
      expect(await screen.findByLabelText('payment-schedule-error')).toHaveTextContent(empty);
      cleanup();
      vi.mocked(documentsApi.issuePaymentSchedule).mockRejectedValueOnce(
        new ApiError('Request failed', 422, 'PAYMENT_SCHEDULE_UNPRICED', { code: 'PAYMENT_SCHEDULE_UNPRICED', details: { count: 2 } }),
      );
      renderSchedule();
      await press('send-payment-schedule');
      expect(await screen.findByLabelText('payment-schedule-error')).toHaveTextContent(unpriced);
      cleanup();
    }
    expect(onIssued).not.toHaveBeenCalled();
  });
});
