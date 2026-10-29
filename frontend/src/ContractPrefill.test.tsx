import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as catalogApi from './api/contractCatalog';
import * as api from './api/contracts';
import * as peopleApi from './api/representatives';
import { I18nProvider } from './hooks/useI18n';
import type { Contract } from './types/contract';
import type { ContractCatalog } from './types/contractCatalog';
import type { ProjectRepresentative } from './types/representative';
import { ProjectContract } from './components/ProjectContract';

vi.mock('./api/contracts', () => ({
  fetchContracts: vi.fn(),
  openContractDraft: vi.fn(),
  saveContractAnswers: vi.fn(),
  abandonContractDraft: vi.fn(),
  fetchContractGate: vi.fn(),
  issueContract: vi.fn(),
  signContract: vi.fn(),
  closeContract: vi.fn(),
  prefillContract: vi.fn(),
}));
vi.mock('./api/documents', () => ({ previewContractPdf: vi.fn() }));
vi.mock('./api/contractCatalog', () => ({ fetchContractCatalog: vi.fn() }));
vi.mock('./api/representatives', () => ({ fetchRepresentatives: vi.fn() }));

// the real catalogues of the server: the screen must draw every question and requirement they hold
const files = import.meta.glob('../../backend/app/domain/contracts/catalog/*.json', { eager: true, import: 'default' }) as Record<string, unknown>;
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

function person(over: Partial<ProjectRepresentative> = {}): ProjectRepresentative {
  return {
    id: 'rep1', project_id: 'p1', side: 'CUSTOMER', name: 'Anna Nowak', role_title: 'Właścicielka', phone: null, email: null,
    may_accept_and_sign: true, is_archived: false, created_at: 'x', updated_at: 'x', ...over,
  };
}

function contract(over: Partial<Contract> = {}): Contract {
  return {
    id: 'c1', project_id: 'p1', version: 1, status: 'DRAFT', answers: {}, effective_answers: { customer_appearance_days: 3, partial_acceptance: true },
    missing_required: ['client_status', 'conclusion_mode', 'who_accepts', 'contract_date', 'contract_place'], questionnaire_version: 2, created_at: 'x', updated_at: 'x', ...over,
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

describe('UX walk B2: the empty answers are filled from what is known', () => {
  const FILLED = ['contract_date', 'contract_place', 'vat_rate_percent', 'client_status', 'who_accepts', 'warranty_months'];
  const prefilled = contract({
    answers: { contract_date: '2026-10-29', contract_place: 'Kraków', vat_rate_percent: 8, client_status: 'CONSUMER', who_accepts: ['rep3'], warranty_months: 24 },
    effective_answers: {
      customer_appearance_days: 3, partial_acceptance: true, contract_date: '2026-10-29', contract_place: 'Kraków', vat_rate_percent: 8,
      client_status: 'CONSUMER', who_accepts: ['rep3'], warranty_months: 24,
    },
    missing_required: ['conclusion_mode'],
  });

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchContracts).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.openContractDraft).mockResolvedValue(contract());
    vi.mocked(api.fetchContractGate).mockResolvedValue({ ready: false, blockers: [] });
    vi.mocked(api.prefillContract).mockResolvedValue({ contract: prefilled, filled: FILLED, terms_from: 'Długa 15/4' });
    vi.mocked(catalogApi.fetchContractCatalog).mockResolvedValue(CATALOG);
    vi.mocked(peopleApi.fetchRepresentatives)
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValue({ items: [person({ id: 'rep3', name: 'Jan Kowalski', role_title: null })], total: 1 });
  });
  afterEach(cleanup);

  it('fills a draft nobody has answered at once, names how many and where the terms came from, and marks the fields', async () => {
    renderCard();
    const form = await compose();
    await waitFor(() => expect(api.prefillContract).toHaveBeenCalledWith('p1', 'c1'));
    expect(await within(form).findByLabelText('contract-prefill-note')).toHaveTextContent(
      'Uzupełniono automatycznie pól: 6. Stałe warunki wzięto z umowy obiektu „Długa 15/4”. Sprawdź je przed wystawieniem.');
    expect(within(form).getByLabelText('contract-q-contract_place')).toHaveValue('Kraków');
    expect(within(form).getByLabelText('contract-q-vat_rate_percent')).toHaveValue('8');
    expect(within(form).getByLabelText('contract-q-who_accepts-rep3')).toBeChecked(); // the client, made the person who accepts
    expect(within(form).getByLabelText('contract-prefilled-contract_place')).toHaveTextContent('uzupełnione');
    fireEvent.change(within(form).getByLabelText('contract-q-contract_place'), { target: { value: 'Wieliczka' } });
    expect(within(form).queryByLabelText('contract-prefilled-contract_place')).toBeNull(); // changed by the owner
    expect(within(form).getByLabelText('contract-prefilled-warranty_months')).toBeInTheDocument();
  });

  it('does not fill a draft that already has answers by itself; the button saves what is typed first, then fills', async () => {
    const answered = contract({ answers: { contract_place: 'Kraków' }, effective_answers: { customer_appearance_days: 3, partial_acceptance: true, contract_place: 'Kraków' } });
    vi.mocked(api.openContractDraft).mockResolvedValue(answered);
    vi.mocked(api.saveContractAnswers).mockResolvedValue(answered);
    vi.mocked(api.prefillContract).mockResolvedValue({ contract: answered, filled: [], terms_from: null });
    renderCard();
    const form = await compose();
    expect(api.prefillContract).not.toHaveBeenCalled();
    fireEvent.change(within(form).getByLabelText('contract-q-warranty_months'), { target: { value: '36' } });
    const button = within(form).getByLabelText('contract-prefill');
    expect(button.className).toContain('min-h-11');
    await act(async () => { fireEvent.click(button); });
    await waitFor(() => expect(api.prefillContract).toHaveBeenCalledWith('p1', 'c1'));
    expect(api.saveContractAnswers).toHaveBeenCalledWith('p1', 'c1', { warranty_months: 36 });
    expect(vi.mocked(api.saveContractAnswers).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.prefillContract).mock.invocationCallOrder[0]);
    expect(await within(form).findByLabelText('contract-prefill-note')).toHaveTextContent('Nie ma czego uzupełnić');
  });

  it('keeps the questionnaire as it was when the automatic fill fails', async () => {
    vi.mocked(api.prefillContract).mockRejectedValue(new Error('offline'));
    renderCard();
    const form = await compose();
    await waitFor(() => expect(api.prefillContract).toHaveBeenCalled());
    expect(within(form).getByLabelText('contract-q-contract_place')).toHaveValue('');
    expect(within(form).queryByLabelText('contract-prefill-note')).toBeNull();
    expect(within(form).getByLabelText('contract-prefill')).not.toBeDisabled();
  });
});
