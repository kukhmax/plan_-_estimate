import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { KnowledgeBase } from './KnowledgeBase';
import { I18nProvider } from '../hooks/useI18n';
import * as api from '../api/knowledge';
import type { KnowledgeEntryDetail, KnowledgeEntryItem, KnowledgeMeta, KnowledgeSituation } from '../types/knowledge';

vi.mock('../api/knowledge', () => ({
  fetchKnowledgeMeta: vi.fn(),
  listKnowledgeEntries: vi.fn(),
  fetchKnowledgeEntry: vi.fn(),
  listKnowledgeSituations: vi.fn(),
  fetchKnowledgeSituation: vi.fn(),
}));

const META: KnowledgeMeta = {
  version: 2, updated_on: '2026-10-11', disclaimer_pl: null, disclaimer_ru: null, disclaimer_status: 'DRAFT',
  sources: 1, entries: 2, situations: 0,
};

const ITEM = (code: string, overrides: Partial<KnowledgeEntryItem> = {}): KnowledgeEntryItem => ({
  code, kind: 'STATUTE', source: 'KC', source_designation: 'KC', locator: 'art. 640', title_pl: `Tytuł ${code}`,
  title_ru: `Название ${code}`, status: 'DRAFT', tags: [], ...overrides,
});

const DETAIL = (overrides: Partial<KnowledgeEntryDetail['entry']> = {}, url: string | null = 'https://example.org/kc'): KnowledgeEntryDetail => ({
  entry: {
    code: 'KC.640', source: 'KC', locator: 'art. 640', title_pl: 'Brak współdziałania zamawiającego', title_ru: 'Отсутствие содействия заказчика',
    summary_pl: 'Wykonawca wyznacza termin z zagrożeniem odstąpienia.', explanation_ru: 'Дайте клиенту срок и предупредите об отказе.',
    tags: [], status: 'DRAFT', approved_by: null, approved_on: null, checked_on: null,
    review_notes: [{ ref: 'UNVERIFIED', text: 'Sprawdzić z ISAP.', status: 'OPEN' }, { ref: 'DONE', text: 'Zamknięte.', status: 'RESOLVED' }],
    ...overrides,
  },
  source: { code: 'KC', kind: 'STATUTE', title_pl: 'Kodeks cywilny', designation: 'Dz.U. 1964 nr 16 poz. 93', url, status: 'DRAFT' },
  linked_from: [{ target_kind: 'CLAUSE', target: 'downtime.5', entries: ['KC.640'] }],
  places: [
    { target_kind: 'CLAUSE', target: 'downtime.5', section_number: 10, clause_number: 5, section_title_pl: 'Przestój z przyczyn dotyczących Zamawiającego' },
    { target_kind: 'DOCUMENT', target: 'DOWNTIME_NOTICE', section_number: null, clause_number: null, section_title_pl: null },
    { target_kind: 'RISK', target: 'MOISTURE_BLOCK_FINISHING', section_number: null, clause_number: null, section_title_pl: null },
    { target_kind: 'RISK', target: 'CRACK_RECURRENCE', section_number: null, clause_number: null, section_title_pl: null },
    { target_kind: 'PHRASE', target: 'COMM_RISK_CRACK_RECURRENCE', section_number: null, clause_number: null, section_title_pl: null },
  ],
});

const SITUATION: KnowledgeSituation = {
  code: 'SIT.PRIMER', status: 'DRAFT', title_pl: 'Klient odmawia gruntowania', title_ru: 'Клиент отказывается от грунтовки', start: 'q1',
  questions: [
    { id: 'q1', text_pl: 'Czy klient podpisze protokół?', text_ru: 'Подпишет ли клиент протокол?',
      answers: [{ text_pl: 'Tak', text_ru: 'Да', next: 'signs' }, { text_pl: 'Nie', text_ru: 'Нет', next: 'q2' }] },
    { id: 'q2', text_pl: 'Czy jest świadek?', text_ru: 'Есть ли свидетель?',
      answers: [{ text_pl: 'Tak', text_ru: 'Да', next: 'witness' }, { text_pl: 'Nie', text_ru: 'Нет', next: 'signs' }] },
  ],
  outcomes: [
    { id: 'signs', steps_pl: ['Wydaj protokół decyzji.'], steps_ru: ['Выдайте протокол решений.'], entries: ['KC.640'], phrases: ['PHRASE_X'], documents: ['DECISION_PROTOCOL'], lawyer: false },
    { id: 'witness', steps_pl: ['Zapisz świadka.'], steps_ru: ['Запишите свидетеля.'], entries: [], phrases: [], documents: [], lawyer: true },
  ],
};

function renderScreen() {
  return render(<I18nProvider><KnowledgeBase /></I18nProvider>);
}

describe('KnowledgeBase (Stage 17D)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchKnowledgeMeta).mockResolvedValue(META);
    vi.mocked(api.listKnowledgeSituations).mockResolvedValue({ items: [] });
    vi.mocked(api.listKnowledgeEntries).mockResolvedValue({ items: [ITEM('KC.640'), ITEM('KC.644', { locator: 'art. 644' })], total: 2 });
    vi.mocked(api.fetchKnowledgeEntry).mockResolvedValue(DETAIL());
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('opens on a list of titles with the place in the act and the mark of a draft, not on the details (Q6, Q7)', async () => {
    renderScreen();
    const list = await screen.findByLabelText('knowledge-entries');
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    const row = screen.getByLabelText('knowledge-entry-KC.640');
    expect(row).toHaveTextContent('Tytuł KC.640');
    expect(row).toHaveTextContent('KC · art. 640');
    expect(row).toHaveTextContent('Wersja robocza');
    expect(screen.getByLabelText('knowledge-draft-notice')).toHaveTextContent('Widzisz ją tylko Ty');
    expect(screen.getByLabelText('knowledge-count')).toHaveTextContent('Znaleziono: 2');
    expect(api.fetchKnowledgeEntry).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('knowledge-situations')).toBeNull(); // no situations in the catalogue: no empty heading
  });

  it('shows the titles in the language of the application', async () => {
    localStorage.setItem('locale', 'ru');
    renderScreen();
    expect(await screen.findByLabelText('knowledge-entry-KC.640')).toHaveTextContent('Название KC.640');
    expect(screen.getByLabelText('knowledge-entry-KC.640')).toHaveTextContent('Черновик');
  });

  it('tap opens the card: the key points, then the source with its link at the end (Q4)', async () => {
    renderScreen();
    fireEvent.click(await screen.findByLabelText('knowledge-entry-KC.640'));
    const card = await screen.findByLabelText('knowledge-card-KC.640');
    expect(api.fetchKnowledgeEntry).toHaveBeenCalledWith('KC.640');
    expect(within(card).getByLabelText('knowledge-summary')).toHaveTextContent('Wykonawca wyznacza termin');
    // the Russian explanation belongs to the Russian interface only
    expect(within(card).queryByLabelText('knowledge-explanation')).toBeNull();
    // where in the application, in words a person recognises: the paragraph of the contract, the name of the document, a count
    const linked = within(card).getByLabelText('knowledge-linked');
    expect(linked).toHaveTextContent('Umowa § 10 ust. 5 — Przestój z przyczyn dotyczących Zamawiającego');
    expect(linked).toHaveTextContent('Dokument: Zawiadomienie o przestoju');
    expect(linked).toHaveTextContent('Ryzyka z badania podłoża: 2');
    expect(linked).toHaveTextContent('Zwroty dla klienta: 1');
    for (const code of ['downtime.5', 'DOWNTIME_NOTICE', 'MOISTURE_BLOCK_FINISHING', 'COMM_RISK']) expect(linked).not.toHaveTextContent(code);
    const source = within(card).getByLabelText('knowledge-source');
    expect(source).toHaveTextContent('Kodeks cywilny');
    expect(source).toHaveTextContent('Omówienie przygotowane przez AI, nie sprawdzone przez prawnika.');
    expect(within(card).getByLabelText('knowledge-current-text')).toHaveTextContent('Obowiązujący tekst: Dz.U. 1964 nr 16 poz. 93');
    const link = within(card).getByLabelText('knowledge-source-link');
    expect(link).toHaveAttribute('href', 'https://example.org/kc');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    // the source is the last block of the card
    expect(card.lastElementChild).toBe(source);
    expect(screen.queryByLabelText('knowledge-entries')).toBeNull();
  });

  it('the Russian interface adds the explanation for the contractor', async () => {
    localStorage.setItem('locale', 'ru');
    renderScreen();
    fireEvent.click(await screen.findByLabelText('knowledge-entry-KC.640'));
    const explanation = await screen.findByLabelText('knowledge-explanation');
    expect(explanation).toHaveTextContent('Дайте клиенту срок');
    expect(screen.getByLabelText('knowledge-summary')).toHaveTextContent('Wykonawca wyznacza termin'); // the key points stay Polish
  });

  it('only the open notes for the lawyer are listed, folded', async () => {
    renderScreen();
    fireEvent.click(await screen.findByLabelText('knowledge-entry-KC.640'));
    const notes = await screen.findByLabelText('knowledge-notes');
    expect(notes).toHaveTextContent('Do sprawdzenia przez prawnika (1)');
    expect(notes).toHaveTextContent('Sprawdzić z ISAP.');
    expect(notes).not.toHaveTextContent('Zamknięte.');
    expect(notes.tagName).toBe('DETAILS');
    expect(notes).not.toHaveAttribute('open');
  });

  it('an entry without key points or without a link says so instead of leaving a hole', async () => {
    vi.mocked(api.fetchKnowledgeEntry).mockResolvedValue(DETAIL({ summary_pl: null, explanation_ru: null }, null));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('knowledge-entry-KC.640'));
    const card = await screen.findByLabelText('knowledge-card-KC.640');
    expect(within(card).getByLabelText('knowledge-summary')).toHaveTextContent('Jeszcze bez omówienia.');
    expect(within(card).queryByLabelText('knowledge-source-link')).toBeNull();
    expect(within(card).getByLabelText('knowledge-source')).toHaveTextContent('Źródło bez linku.');
  });

  it('an approved entry shows who approved it and when it was checked, with no draft mark', async () => {
    vi.mocked(api.fetchKnowledgeEntry).mockResolvedValue(
      DETAIL({ status: 'APPROVED', approved_by: 'Adw. Kowalski', approved_on: '2026-10-12', checked_on: '2026-10-10', review_notes: [] }),
    );
    renderScreen();
    fireEvent.click(await screen.findByLabelText('knowledge-entry-KC.640'));
    const card = await screen.findByLabelText('knowledge-card-KC.640');
    expect(card).toHaveTextContent('Zatwierdzone');
    expect(card).toHaveTextContent('Stan na dzień sprawdzenia: 2026-10-10');
    expect(card).toHaveTextContent('Zatwierdził: Adw. Kowalski, 2026-10-12');
    expect(card).not.toHaveTextContent('Wersja robocza');
    expect(within(card).queryByLabelText('knowledge-notes')).toBeNull();
  });

  it('search asks the server after a short pause, once for a typed word, and shows what it answers', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderScreen();
    await screen.findByLabelText('knowledge-entries');
    vi.mocked(api.listKnowledgeEntries).mockClear();
    vi.mocked(api.listKnowledgeEntries).mockResolvedValue({ items: [ITEM('KC.558')], total: 1 });
    const input = screen.getByLabelText('knowledge-search');
    fireEvent.change(input, { target: { value: 'rek' } });
    fireEvent.change(input, { target: { value: 'rekoj' } });
    expect(api.listKnowledgeEntries).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(api.listKnowledgeEntries).toHaveBeenCalledTimes(1);
    expect(api.listKnowledgeEntries).toHaveBeenCalledWith('rekoj');
    expect(await screen.findByLabelText('knowledge-entry-KC.558')).toBeInTheDocument();
    expect(screen.queryByLabelText('knowledge-entry-KC.640')).toBeNull();
  });

  it('an empty answer to a query says what to try; an empty catalogue says it is empty', async () => {
    vi.mocked(api.listKnowledgeEntries).mockResolvedValue({ items: [], total: 0 });
    renderScreen();
    expect(await screen.findByLabelText('knowledge-empty')).toHaveTextContent('Baza wiedzy jest jeszcze pusta.');
    fireEvent.change(screen.getByLabelText('knowledge-search'), { target: { value: 'xyz' } });
    await waitFor(() => expect(screen.getByLabelText('knowledge-empty')).toHaveTextContent('Brak wyników.'));
  });

  it('a slow answer to an earlier query never replaces the list of a later one', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let resolveSlow: (value: { items: KnowledgeEntryItem[]; total: number }) => void = () => undefined;
    renderScreen();
    await screen.findByLabelText('knowledge-entries');
    vi.mocked(api.listKnowledgeEntries)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSlow = resolve; }))
      .mockResolvedValueOnce({ items: [ITEM('NEW.1')], total: 1 });
    const input = screen.getByLabelText('knowledge-search');
    fireEvent.change(input, { target: { value: 'a' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    fireEvent.change(input, { target: { value: 'ab' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    expect(await screen.findByLabelText('knowledge-entry-NEW.1')).toBeInTheDocument();
    await act(async () => { resolveSlow({ items: [ITEM('OLD.1')], total: 1 }); });
    expect(screen.queryByLabelText('knowledge-entry-OLD.1')).toBeNull();
    expect(screen.getByLabelText('knowledge-entry-NEW.1')).toBeInTheDocument();
  });

  it('a list that does not load shows a retry that works', async () => {
    vi.mocked(api.listKnowledgeEntries).mockRejectedValueOnce(new Error('x'));
    renderScreen();
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać bazy wiedzy.');
    fireEvent.click(screen.getByLabelText('knowledge-retry'));
    expect(await screen.findByLabelText('knowledge-entry-KC.640')).toBeInTheDocument();
  });

  it('a card that does not load can be retried', async () => {
    vi.mocked(api.fetchKnowledgeEntry).mockRejectedValueOnce(new Error('x'));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('knowledge-entry-KC.640'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać bazy wiedzy.');
    fireEvent.click(screen.getByLabelText('knowledge-retry'));
    expect(await screen.findByLabelText('knowledge-card-KC.640')).toBeInTheDocument();
  });

  it('the back button leads from the card to the list that was open, with its query', async () => {
    renderScreen();
    fireEvent.click(await screen.findByLabelText('knowledge-entry-KC.640'));
    await screen.findByLabelText('knowledge-card-KC.640');
    fireEvent.click(screen.getByLabelText('knowledge-back'));
    expect(await screen.findByLabelText('knowledge-entries')).toBeInTheDocument();
    expect(screen.queryByLabelText('knowledge-back')).toBeNull();
  });

  it('the Telegram BackButton is shown on a card and takes the owner back to the list', async () => {
    const show = vi.fn();
    const hide = vi.fn();
    const handlers: Array<() => void> = [];
    window.Telegram = { WebApp: { BackButton: { show, hide, onClick: (cb: () => void) => handlers.push(cb), offClick: vi.fn() } } } as never;
    try {
      renderScreen();
      await screen.findByLabelText('knowledge-entries');
      expect(show).not.toHaveBeenCalled();
      fireEvent.click(screen.getByLabelText('knowledge-entry-KC.640'));
      await screen.findByLabelText('knowledge-card-KC.640');
      expect(show).toHaveBeenCalled();
      act(() => handlers[handlers.length - 1]());
      expect(await screen.findByLabelText('knowledge-entries')).toBeInTheDocument();
    } finally {
      delete (window as { Telegram?: unknown }).Telegram;
    }
  });

  describe('situations', () => {
    beforeEach(() => {
      vi.mocked(api.listKnowledgeSituations).mockResolvedValue({
        items: [{ code: 'SIT.PRIMER', title_pl: SITUATION.title_pl, title_ru: SITUATION.title_ru, status: 'DRAFT' }],
      });
      vi.mocked(api.fetchKnowledgeSituation).mockResolvedValue(SITUATION);
    });

    it('are offered above the topics and hidden while a query is typed', async () => {
      renderScreen();
      const block = await screen.findByLabelText('knowledge-situations');
      expect(within(block).getByLabelText('knowledge-situation-SIT.PRIMER')).toHaveTextContent('Klient odmawia gruntowania');
      fireEvent.change(screen.getByLabelText('knowledge-search'), { target: { value: 'kc' } });
      await waitFor(() => expect(screen.queryByLabelText('knowledge-situations')).toBeNull());
    });

    it('go one question at a time to an outcome with steps, the basis, the phrase and the document', async () => {
      renderScreen();
      fireEvent.click(await screen.findByLabelText('knowledge-situation-SIT.PRIMER'));
      const question = await screen.findByLabelText('knowledge-question');
      expect(question).toHaveTextContent('Czy klient podpisze protokół?');
      expect(screen.queryByLabelText('knowledge-situation-previous')).toBeNull();
      fireEvent.click(within(question).getByLabelText('knowledge-answer-0'));
      const outcome = await screen.findByLabelText('knowledge-outcome');
      expect(outcome).toHaveTextContent('Wydaj protokół decyzji.');
      expect(outcome).toHaveTextContent('PHRASE_X');
      expect(outcome).toHaveTextContent('Protokół informacji i decyzji');
      expect(within(outcome).queryByText('Tu skonsultuj się z prawnikiem.')).toBeNull();
      expect(screen.queryByLabelText('knowledge-question')).toBeNull();
    });

    it('can step back one question and start again', async () => {
      renderScreen();
      fireEvent.click(await screen.findByLabelText('knowledge-situation-SIT.PRIMER'));
      fireEvent.click(await screen.findByLabelText('knowledge-answer-1'));
      expect(await screen.findByLabelText('knowledge-question')).toHaveTextContent('Czy jest świadek?');
      fireEvent.click(screen.getByLabelText('knowledge-situation-previous'));
      expect(screen.getByLabelText('knowledge-question')).toHaveTextContent('Czy klient podpisze protokół?');
      fireEvent.click(screen.getByLabelText('knowledge-answer-1'));
      fireEvent.click(screen.getByLabelText('knowledge-answer-0'));
      expect(screen.getByLabelText('knowledge-outcome')).toHaveTextContent('Zapisz świadka.');
      expect(screen.getByLabelText('knowledge-outcome')).toHaveTextContent('Tu skonsultuj się z prawnikiem.');
      fireEvent.click(screen.getByLabelText('knowledge-situation-restart'));
      expect(screen.getByLabelText('knowledge-question')).toHaveTextContent('Czy klient podpisze protokół?');
      expect(screen.queryByLabelText('knowledge-situation-restart')).toBeNull();
    });

    it('an entry of the outcome is named by its title (its code until the titles arrive) and opens its card; back returns to the same outcome', async () => {
      renderScreen();
      fireEvent.click(await screen.findByLabelText('knowledge-situation-SIT.PRIMER'));
      fireEvent.click(await screen.findByLabelText('knowledge-answer-0'));
      const button = await screen.findByLabelText('knowledge-outcome-entry-KC.640');
      await waitFor(() => expect(button).toHaveTextContent('Tytuł KC.640'));
      fireEvent.click(button);
      expect(await screen.findByLabelText('knowledge-card-KC.640')).toBeInTheDocument();
      fireEvent.click(screen.getByLabelText('knowledge-back'));
      expect(await screen.findByLabelText('knowledge-situation-card-SIT.PRIMER')).toBeInTheDocument();
    });

    it('speak Russian in the Russian interface', async () => {
      localStorage.setItem('locale', 'ru');
      renderScreen();
      fireEvent.click(await screen.findByLabelText('knowledge-situation-SIT.PRIMER'));
      expect(await screen.findByLabelText('knowledge-question')).toHaveTextContent('Подпишет ли клиент протокол?');
      fireEvent.click(screen.getByLabelText('knowledge-answer-0'));
      const outcome = await screen.findByLabelText('knowledge-outcome');
      expect(outcome).toHaveTextContent('Выдайте протокол решений.');
      expect(outcome).toHaveTextContent('Протокол информирования и решений заказчика');
    });

    it('without the titles the entries of the outcome still open by their codes', async () => {
      vi.mocked(api.listKnowledgeEntries).mockResolvedValueOnce({ items: [], total: 0 }).mockRejectedValue(new Error('x'));
      renderScreen();
      fireEvent.click(await screen.findByLabelText('knowledge-situation-SIT.PRIMER'));
      fireEvent.click(await screen.findByLabelText('knowledge-answer-0'));
      expect(await screen.findByLabelText('knowledge-outcome-entry-KC.640')).toHaveTextContent('KC.640');
    });

    it('a situation that does not load can be retried', async () => {
      vi.mocked(api.fetchKnowledgeSituation).mockRejectedValueOnce(new Error('x'));
      renderScreen();
      fireEvent.click(await screen.findByLabelText('knowledge-situation-SIT.PRIMER'));
      expect(await screen.findByRole('alert')).toBeInTheDocument();
      fireEvent.click(screen.getByLabelText('knowledge-retry'));
      expect(await screen.findByLabelText('knowledge-question')).toBeInTheDocument();
    });
  });
});
