import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as catalogApi from '../api/contractCatalog';
import * as api from '../api/contracts';
import { ApiError } from '../api/http';
import * as peopleApi from '../api/representatives';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import { I18nProvider } from '../hooks/useI18n';
import type { Contract } from '../types/contract';
import type { ContractCatalog } from '../types/contractCatalog';
import type { ProjectRepresentative } from '../types/representative';
import { ProjectContract } from './ProjectContract';

vi.mock('../api/contracts', () => ({
  fetchContracts: vi.fn(),
  openContractDraft: vi.fn(),
  saveContractAnswers: vi.fn(),
  abandonContractDraft: vi.fn(),
}));
vi.mock('../api/contractCatalog', () => ({ fetchContractCatalog: vi.fn() }));
vi.mock('../api/representatives', () => ({ fetchRepresentatives: vi.fn() }));

// the real catalogues of the server: the screen must draw every question and requirement they hold
const files = import.meta.glob('../../../backend/app/domain/contracts/catalog/*.json', { eager: true, import: 'default' }) as Record<string, unknown>;
const read = (name: string) => {
  const entry = Object.entries(files).find(([path]) => path.endsWith(`/${name}`));
  if (!entry) throw new Error(`catalogue ${name} not found`);
  return entry[1];
};
const CATALOG = {
  requirements: read('premises_requirements.json'),
  instruments: read('assessment_instruments.json'),
  evaluation: read('evaluation_conditions.json'),
  defects: read('defect_classes.json'),
  tolerances: read('tolerances.json'),
  questionnaire: read('questionnaire.json'),
} as ContractCatalog;
const REQUIRED = ['who_accepts', 'contract_date', 'contract_place', 'partial_acceptance'];

function person(over: Partial<ProjectRepresentative> = {}): ProjectRepresentative {
  return {
    id: 'rep1', project_id: 'p1', side: 'CUSTOMER', name: 'Anna Nowak', role_title: 'Właścicielka', phone: null, email: null,
    may_accept_and_sign: true, is_archived: false, created_at: 'x', updated_at: 'x', ...over,
  };
}

function contract(over: Partial<Contract> = {}): Contract {
  return {
    id: 'c1', project_id: 'p1', version: 1, status: 'DRAFT', answers: {}, effective_answers: { customer_appearance_days: 3, partial_acceptance: true },
    missing_required: ['who_accepts', 'contract_date', 'contract_place'], questionnaire_version: 1, created_at: 'x', updated_at: 'x', ...over,
  };
}

function renderCard() {
  return render(<I18nProvider><ProjectContract projectId="p1" /></I18nProvider>);
}

async function compose() {
  const button = await screen.findByLabelText('compose-contract');
  await act(async () => { fireEvent.click(button); });
  return screen.findByLabelText('contract-form');
}

describe('ProjectContract (Stage 16E.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchContracts).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.openContractDraft).mockResolvedValue(contract());
    vi.mocked(catalogApi.fetchContractCatalog).mockResolvedValue(CATALOG);
    vi.mocked(peopleApi.fetchRepresentatives).mockResolvedValue({ items: [person(), person({ id: 'rep2', name: 'Bez uprawnień', may_accept_and_sign: false })], total: 2 });
  });
  afterEach(cleanup);

  it('offers to compose the contract with a full-width, touch-sized button and opens the draft on demand', async () => {
    renderCard();
    const button = await screen.findByLabelText('compose-contract');
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('w-full');
    expect(button).toHaveTextContent('Skomponuj umowę');
    expect(api.openContractDraft).not.toHaveBeenCalled();
    await compose();
    expect(api.openContractDraft).toHaveBeenCalledWith('p1');
  });

  it('draws every question of the server catalogue, grouped, with required and optional marked and the progress of the required ones', async () => {
    renderCard();
    const form = await compose();
    for (const question of CATALOG.questionnaire.items) {
      expect(form.textContent).toContain(pl.contractCatalog.questions[question.key as keyof typeof pl.contractCatalog.questions]);
    }
    for (const requirement of CATALOG.requirements.items) {
      expect(form.textContent).toContain(pl.contractCatalog.requirements[requirement.key as keyof typeof pl.contractCatalog.requirements]);
    }
    expect(within(form).getByText('Strony i osoby')).toBeInTheDocument();
    expect(within(form).getByText('Odbiór prac')).toBeInTheDocument();
    expect(screen.getByLabelText('contract-progress')).toHaveTextContent('Wymagane odpowiedzi: 1 z 4');
    const missing = screen.getByLabelText('contract-missing');
    expect(missing).toHaveTextContent('Data zawarcia umowy');
    expect(missing.querySelectorAll('li')).toHaveLength(3);
    expect(form.textContent?.match(/wymagane/g)?.length).toBeGreaterThanOrEqual(REQUIRED.length);
    expect(form).toHaveTextContent('Puste pole opcjonalne nie blokuje umowy');
  });

  it('shows the two defaults the owner accepted and nothing else prefilled', async () => {
    renderCard();
    await compose();
    expect(screen.getByLabelText('contract-q-customer_appearance_days')).toHaveValue('3');
    expect(screen.getByLabelText('contract-q-partial_acceptance')).toHaveValue('yes');
    for (const key of ['advance_percent', 'warranty_months', 'downtime_rate_per_day', 'contract_place', 'reinspection_limit']) {
      expect(screen.getByLabelText(`contract-q-${key}`)).toHaveValue('');
    }
  });

  it('lets only persons with the authority to accept be chosen and says what to do when there are none', async () => {
    renderCard();
    await compose();
    expect(screen.getByLabelText('contract-q-who_accepts-rep1')).toBeInTheDocument();
    expect(screen.queryByLabelText('contract-q-who_accepts-rep2')).toBeNull();
    cleanup();
    vi.mocked(peopleApi.fetchRepresentatives).mockResolvedValue({ items: [person({ may_accept_and_sign: false })], total: 1 });
    renderCard();
    await compose();
    expect(screen.getByText(/Brak osób z uprawnieniem do odbioru prac/)).toBeInTheDocument();
  });

  it('sends only what changed, with typed values, and shows the completeness the server returns', async () => {
    vi.mocked(api.saveContractAnswers).mockResolvedValue(contract({
      answers: { contract_place: 'Kraków' }, missing_required: ['who_accepts', 'contract_date'],
    }));
    renderCard();
    await compose();
    fireEvent.change(screen.getByLabelText('contract-q-contract_place'), { target: { value: '  Kraków ' } });
    fireEvent.change(screen.getByLabelText('contract-q-advance_percent'), { target: { value: '30' } });
    fireEvent.change(screen.getByLabelText('contract-q-downtime_rate_per_day'), { target: { value: '150,5' } });
    fireEvent.change(screen.getByLabelText('contract-q-payment_mode'), { target: { value: 'BY_STAGES' } });
    fireEvent.change(screen.getByLabelText('contract-q-contract_date'), { target: { value: '2026-10-12' } });
    fireEvent.click(screen.getByLabelText('contract-q-who_accepts-rep1'));
    fireEvent.change(screen.getByLabelText('contract-q-partial_acceptance'), { target: { value: 'no' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('save-contract-answers')); });
    expect(api.saveContractAnswers).toHaveBeenCalledWith('p1', 'c1', {
      contract_place: 'Kraków', advance_percent: 30, downtime_rate_per_day: '150,5', payment_mode: 'BY_STAGES', contract_date: '2026-10-12',
      who_accepts: ['rep1'], partial_acceptance: false,
    });
    expect(await screen.findByLabelText('contract-note')).toHaveTextContent('Zapisano.');
    expect(screen.getByLabelText('contract-progress')).toHaveTextContent('Wymagane odpowiedzi: 2 z 4');
  });

  it('sends nothing and says so when nothing changed', async () => {
    renderCard();
    await compose();
    await act(async () => { fireEvent.click(screen.getByLabelText('save-contract-answers')); });
    expect(api.saveContractAnswers).not.toHaveBeenCalled();
    expect(screen.getByLabelText('contract-note')).toHaveTextContent('Brak zmian do zapisania.');
  });

  it('clears a stored answer with null when the field is emptied', async () => {
    vi.mocked(api.openContractDraft).mockResolvedValue(contract({ answers: { contract_place: 'Kraków' }, effective_answers: { customer_appearance_days: 3, partial_acceptance: true, contract_place: 'Kraków' } }));
    vi.mocked(api.saveContractAnswers).mockResolvedValue(contract());
    renderCard();
    await compose();
    expect(screen.getByLabelText('contract-q-contract_place')).toHaveValue('Kraków');
    fireEvent.change(screen.getByLabelText('contract-q-contract_place'), { target: { value: '' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('save-contract-answers')); });
    expect(api.saveContractAnswers).toHaveBeenCalledWith('p1', 'c1', { contract_place: null });
  });

  it('sends the values of the premises requirements by their kind: yes/no, a number and a range', async () => {
    vi.mocked(api.saveContractAnswers).mockResolvedValue(contract());
    renderCard();
    await compose();
    fireEvent.change(screen.getByLabelText('contract-r-lighting_permanent'), { target: { value: 'yes' } });
    fireEvent.change(screen.getByLabelText('contract-r-lighting_level'), { target: { value: '300' } });
    fireEvent.change(screen.getByLabelText('contract-r-temperature_range-min'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('contract-r-temperature_range-max'), { target: { value: '25,5' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('save-contract-answers')); });
    expect(api.saveContractAnswers).toHaveBeenCalledWith('p1', 'c1', {
      premises_requirement_values: { lighting_permanent: true, lighting_level: 300, temperature_range: { min: 5, max: 25.5 } },
    });
  });

  it('names the question the server refused, in the language of the interface', async () => {
    vi.mocked(api.saveContractAnswers).mockRejectedValue(new ApiError('English', 422, 'CONTRACT_ANSWER_INVALID', {
      code: 'CONTRACT_ANSWER_INVALID', details: { key: 'advance_percent', reason: 'OUT_OF_RANGE' },
    }));
    renderCard();
    await compose();
    fireEvent.change(screen.getByLabelText('contract-q-advance_percent'), { target: { value: '500' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('save-contract-answers')); });
    expect(await screen.findByLabelText('contract-error')).toHaveTextContent('Zaliczka (% ceny): wartość poza dozwolonym zakresem');
    localStorage.setItem('locale', 'ru');
    cleanup();
    renderCard();
    await compose();
    fireEvent.change(screen.getByLabelText('contract-q-advance_percent'), { target: { value: '500' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('save-contract-answers')); });
    expect(await screen.findByLabelText('contract-error')).toHaveTextContent('значение вне допустимого диапазона');
  });

  it('continues an existing draft instead of starting a new one and shows what was already answered', async () => {
    const existing = contract({ version: 2, answers: { contract_place: 'Łódź' }, effective_answers: { customer_appearance_days: 3, partial_acceptance: true, contract_place: 'Łódź' }, missing_required: ['who_accepts', 'contract_date'] });
    vi.mocked(api.fetchContracts).mockResolvedValue({ items: [existing], total: 1 });
    vi.mocked(api.openContractDraft).mockResolvedValue(existing);
    renderCard();
    expect(await screen.findByText('Szkic, wersja 2. Do uzupełnienia wymaganych odpowiedzi: 2.')).toBeInTheDocument();
    expect(screen.getByLabelText('compose-contract')).toHaveTextContent('Kontynuuj szkic umowy');
    await compose();
    expect(screen.getByLabelText('contract-q-contract_place')).toHaveValue('Łódź');
  });

  it('abandons the draft only after a second tap', async () => {
    vi.mocked(api.abandonContractDraft).mockResolvedValue(contract({ status: 'ARCHIVED' }));
    renderCard();
    await compose();
    const button = screen.getByLabelText('abandon-contract-draft');
    await act(async () => { fireEvent.click(button); });
    expect(api.abandonContractDraft).not.toHaveBeenCalled();
    expect(button).toHaveTextContent('Naciśnij ponownie');
    await act(async () => { fireEvent.click(button); });
    expect(api.abandonContractDraft).toHaveBeenCalledWith('p1', 'c1');
    await waitFor(() => expect(screen.queryByLabelText('contract-form')).toBeNull());
    expect(screen.getByLabelText('contract-note')).toHaveTextContent('Szkic odrzucony.');
  });

  it('mentions the latest issued contract and offers a retry when the load fails', async () => {
    vi.mocked(api.fetchContracts).mockRejectedValueOnce(new Error('net')).mockResolvedValue({ items: [contract({ id: 'c0', version: 3, status: 'SIGNED' })], total: 1 });
    renderCard();
    expect(await screen.findByText('Nie udało się wczytać umowy.')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' })); });
    expect(await screen.findByText('Ostatnia umowa: wersja 3 — podpisana')).toBeInTheDocument();
  });

  it('is localised in Russian and keeps every control touch-sized', async () => {
    localStorage.setItem('locale', 'ru');
    renderCard();
    const form = await compose();
    expect(screen.getByText('Договор')).toBeInTheDocument();
    for (const question of CATALOG.questionnaire.items) {
      expect(form.textContent).toContain(ru.contractCatalog.questions[question.key as keyof typeof ru.contractCatalog.questions]);
    }
    expect(screen.getByLabelText('contract-progress')).toHaveTextContent('Обязательные ответы: 1 из 4');
    for (const control of form.querySelectorAll('input:not([type=checkbox]), select, button')) {
      expect((control as HTMLElement).className).toMatch(/min-h-11/);
    }
  });
});
