/**
 * Stage 12F — minimal coefficient catalog management (Price Book "Współczynniki" tab).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as coefficientsApi from '../api/coefficients';
import { I18nProvider } from '../hooks/useI18n';
import { CoefficientGroupRead } from '../types/coefficient';
import { CoefficientCatalogManager } from './CoefficientCatalogManager';

vi.mock('../api/coefficients', () => ({
  fetchCoefficientGroups: vi.fn(),
  createCoefficientGroup: vi.fn(),
  updateCoefficientGroup: vi.fn(),
  archiveCoefficientGroup: vi.fn(),
  restoreCoefficientGroup: vi.fn(),
  createCoefficientOption: vi.fn(),
  updateCoefficientOption: vi.fn(),
  archiveCoefficientOption: vi.fn(),
  restoreCoefficientOption: vi.fn(),
}));

const group: CoefficientGroupRead = {
  id: 'grp-height',
  code: 'HEIGHT',
  name_key: null,
  display_name: 'Wysokość',
  selection_mode: 'SINGLE_SELECT',
  position: 0,
  is_archived: false,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  options: [
    {
      id: 'opt-high', group_id: 'grp-height', code: 'HIGH', name_key: null, display_name: 'wysoka',
      percentage: '20.00', is_base: false, position: 0, is_archived: false,
      created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
    },
  ],
};

function renderManager() {
  return render(
    <I18nProvider>
      <CoefficientCatalogManager />
    </I18nProvider>,
  );
}

describe('CoefficientCatalogManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [group], total: 1 });
  });

  it('lists active groups with their options and signed percentages', async () => {
    renderManager();
    expect(await screen.findByText('Wysokość')).toBeInTheDocument();
    expect(screen.getByText('wysoka')).toBeInTheDocument();
    expect(screen.getByText('+20%')).toBeInTheDocument();
    expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledWith({
      archived: 'active',
      include_archived_options: true,
    });
  });

  it('creates an option, normalizing a Polish decimal comma', async () => {
    vi.mocked(coefficientsApi.createCoefficientOption).mockResolvedValue(group.options[0]);
    renderManager();
    await screen.findByText('Wysokość');
    fireEvent.click(screen.getByRole('button', { name: '+ Dodaj opcję' }));
    fireEvent.change(screen.getByPlaceholderText('np. Prace na wysokości > 3m'), {
      target: { value: 'bardzo wysoka' },
    });
    const percentage = document.querySelector('input[inputmode="decimal"]') as HTMLInputElement;
    fireEvent.change(percentage, { target: { value: '12,5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));

    await waitFor(() => {
      expect(coefficientsApi.createCoefficientOption).toHaveBeenCalledWith('grp-height', {
        display_name: 'bardzo wysoka',
        percentage: '12.5',
        is_base: false,
      });
    });
  });

  it('keeps every action button at least 44px tall', async () => {
    renderManager();
    await screen.findByText('Wysokość');
    screen.getAllByRole('button').forEach((button) => {
      expect(button.className).toContain('min-h-[44px]');
    });
  });
});
