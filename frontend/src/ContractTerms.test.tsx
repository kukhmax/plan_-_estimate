import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as catalogApi from './api/contractCatalog';
import * as termsApi from './api/contractTerms';
import { ApiError } from './api/http';
import { ContractTermsModal } from './components/ContractTermsModal';
import { I18nProvider } from './hooks/useI18n';
import type { ContractCatalog } from './types/contractCatalog';

vi.mock('./api/contractCatalog', () => ({ fetchContractCatalog: vi.fn() }));
vi.mock('./api/contractTerms', () => ({ fetchContractTerms: vi.fn(), saveContractTerms: vi.fn() }));

// the real catalogues of the server
const files = import.meta.glob('../../backend/app/domain/contracts/catalog/*.json', { eager: true, import: 'default' }) as Record<string, unknown>;
const read = (name: string) => Object.entries(files).find(([path]) => path.endsWith(`/${name}`))![1];
const CATALOG = {
  requirements: read('premises_requirements.json'),
  instruments: read('assessment_instruments.json'),
  evaluation: read('evaluation_conditions.json'),
  defects: read('defect_classes.json'),
  tolerances: read('tolerances.json'),
  questionnaire: read('questionnaire.json'),
} as ContractCatalog;
const KEYS = ['conclusion_mode', 'work_hours', 'price_validity_days', 'advance_percent', 'payment_mode', 'payment_due_days', 'payment_account',
  'materials_supplier', 'contractor_representative', 'insurance_sum', 'insurance_policy', 'warranty_months', 'penalty_mode', 'penalty_rate_per_day',
  'penalty_cap_percent', 'downtime_rate_per_day', 'downtime_cap_percent', 'downtime_days_limit', 'customer_appearance_days', 'partial_acceptance',
  'reinspection_limit', 'premises_acceptance_notice_days', 'premises_requirement_values'];

const open = () => render(<I18nProvider><ContractTermsModal onClose={() => undefined} /></I18nProvider>);

describe('UX walk B2: "Moje standardowe warunki umowy"', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(catalogApi.fetchContractCatalog).mockResolvedValue(CATALOG);
    vi.mocked(termsApi.fetchContractTerms).mockResolvedValue({
      answers: {}, keys: KEYS, latest: { answers: { warranty_months: 24, advance_percent: 30, conclusion_mode: 'OFF_PREMISES' }, project_name: 'Długa 15/4' },
    });
    vi.mocked(termsApi.saveContractTerms).mockImplementation(async (answers) => ({ answers, keys: KEYS, latest: null }));
  });
  afterEach(cleanup);

  it('draws only the terms, says they come from the latest contract while empty, and starts from it on demand', async () => {
    open();
    const form = await screen.findByLabelText('contract-terms-form');
    expect(within(form).queryByLabelText('contract-q-contract_place')).toBeNull(); // a fact of one object, not a term
    expect(within(form).queryByLabelText('contract-q-who_accepts')).toBeNull();
    expect(within(form).getByLabelText('contract-q-warranty_months')).toHaveValue('');
    expect(within(form).getByLabelText('contract-terms-empty')).toHaveTextContent('z ostatniej umowy (obiekt „Długa 15/4”)');
    fireEvent.click(within(form).getByLabelText('contract-terms-from-latest'));
    expect(within(form).getByLabelText('contract-q-warranty_months')).toHaveValue('24');
    expect(within(form).getByLabelText('contract-q-conclusion_mode')).toHaveValue('OFF_PREMISES');
    expect(termsApi.saveContractTerms).not.toHaveBeenCalled(); // nothing is saved before "Zapisz warunki"
    fireEvent.change(within(form).getByLabelText('contract-q-advance_percent'), { target: { value: '20' } });
    await act(async () => { fireEvent.click(within(form).getByLabelText('save-contract-terms')); });
    await waitFor(() => expect(termsApi.saveContractTerms).toHaveBeenCalledWith({ warranty_months: 24, advance_percent: 20, conclusion_mode: 'OFF_PREMISES' }));
    expect(await within(form).findByLabelText('contract-terms-note')).toHaveTextContent('Zapisano warunków: 3.');
  });

  it('shows the saved terms and names a refused answer by its question', async () => {
    vi.mocked(termsApi.fetchContractTerms).mockResolvedValue({ answers: { warranty_months: 36, partial_acceptance: false }, keys: KEYS, latest: null });
    vi.mocked(termsApi.saveContractTerms).mockRejectedValue(
      new ApiError('bad', 422, 'CONTRACT_ANSWER_INVALID', { details: { key: 'warranty_months', reason: 'OUT_OF_RANGE' } }),
    );
    open();
    const form = await screen.findByLabelText('contract-terms-form');
    expect(within(form).getByLabelText('contract-q-warranty_months')).toHaveValue('36');
    expect(within(form).getByLabelText('contract-q-partial_acceptance')).toHaveValue('no');
    expect(within(form).queryByLabelText('contract-terms-empty')).toBeNull();
    expect(within(form).queryByLabelText('contract-terms-from-latest')).toBeNull();
    fireEvent.change(within(form).getByLabelText('contract-q-warranty_months'), { target: { value: '500' } });
    await act(async () => { fireEvent.click(within(form).getByLabelText('save-contract-terms')); });
    expect(await within(form).findByLabelText('contract-terms-error')).toHaveTextContent('Okres gwarancji (miesiące)');
  });

  it('says so when it cannot load', async () => {
    vi.mocked(termsApi.fetchContractTerms).mockRejectedValue(new Error('offline'));
    open();
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać warunków.');
  });
});
