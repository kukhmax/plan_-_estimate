/**
 * Stage 12F — minimal coefficient catalog management (Price Book "Współczynniki" tab).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as coefficientsApi from '../api/coefficients';
import { I18nProvider } from '../hooks/useI18n';
import pl from '../locales/pl.json';
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
  description: null,
  selection_mode: 'SINGLE_SELECT',
  position: 0,
  is_archived: false,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  options: [
    {
      id: 'opt-high', group_id: 'grp-height', code: 'HIGH', name_key: null, display_name: 'wysoka', description: null,
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
        description: null,
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

  describe('descriptions (Stage 12G)', () => {
    const described: CoefficientGroupRead = {
      ...group,
      description: 'Opis grupy',
      options: [{ ...group.options[0], description: 'Opis opcji' }],
    };

    it('shows existing group and option descriptions', async () => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [described], total: 1 });
      renderManager();
      expect(await screen.findByText('Opis grupy')).toBeInTheDocument();
      expect(screen.getByText('Opis opcji')).toBeInTheDocument();
    });

    it('creates a group with a description', async () => {
      vi.mocked(coefficientsApi.createCoefficientGroup).mockResolvedValue(described);
      renderManager();
      await screen.findByText('Wysokość');
      fireEvent.click(screen.getByRole('button', { name: '+ Dodaj grupę' }));
      fireEvent.change(screen.getByPlaceholderText('np. Wysokość pracy, Dostęp do powierzchni'), {
        target: { value: 'Nowa grupa' },
      });
      fireEvent.change(screen.getByLabelText('coefficient-group-description-input'), {
        target: { value: '  Kiedy stosować  ' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
      await waitFor(() => {
        expect(coefficientsApi.createCoefficientGroup).toHaveBeenCalledWith({
          display_name: 'Nowa grupa',
          description: 'Kiedy stosować',
        });
      });
    });

    it('edits a group description, prefilled with the current text', async () => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [described], total: 1 });
      vi.mocked(coefficientsApi.updateCoefficientGroup).mockResolvedValue(described);
      renderManager();
      await screen.findByText('Opis grupy');
      fireEvent.click(screen.getAllByRole('button', { name: 'Edytuj' })[0]);
      const textarea = screen.getByLabelText('coefficient-group-description-edit');
      expect(textarea).toHaveValue('Opis grupy');
      fireEvent.change(textarea, { target: { value: '' } });
      fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
      await waitFor(() => {
        expect(coefficientsApi.updateCoefficientGroup).toHaveBeenCalledWith('grp-height', {
          display_name: 'Wysokość',
          description: null,
        });
      });
    });

    it('creates an option with a description', async () => {
      vi.mocked(coefficientsApi.createCoefficientOption).mockResolvedValue(group.options[0]);
      renderManager();
      await screen.findByText('Wysokość');
      fireEvent.click(screen.getByRole('button', { name: '+ Dodaj opcję' }));
      fireEvent.change(screen.getByPlaceholderText('np. Prace na wysokości > 3m'), {
        target: { value: 'Opcja' },
      });
      fireEvent.change(document.querySelector('input[inputmode="decimal"]') as HTMLInputElement, {
        target: { value: '5' },
      });
      fireEvent.change(screen.getByLabelText('coefficient-option-description-input'), {
        target: { value: 'Opis nowej opcji' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
      await waitFor(() => {
        expect(coefficientsApi.createCoefficientOption).toHaveBeenCalledWith('grp-height', {
          display_name: 'Opcja',
          percentage: '5',
          is_base: false,
          description: 'Opis nowej opcji',
        });
      });
    });

    it('edits an option description, prefilled with the current text', async () => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [described], total: 1 });
      vi.mocked(coefficientsApi.updateCoefficientOption).mockResolvedValue(described.options[0]);
      renderManager();
      await screen.findByText('Opis opcji');
      fireEvent.click(screen.getAllByRole('button', { name: 'Edytuj' })[1]);
      const textarea = screen.getByLabelText('coefficient-option-description-edit');
      expect(textarea).toHaveValue('Opis opcji');
      fireEvent.change(textarea, { target: { value: 'Zmieniony opis' } });
      fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
      await waitFor(() => {
        expect(coefficientsApi.updateCoefficientOption).toHaveBeenCalledWith('opt-high', {
          display_name: 'wysoka',
          percentage: '20.00',
          is_base: false,
          description: 'Zmieniony opis',
        });
      });
    });

    it('labels the description field in Russian', async () => {
      localStorage.setItem('locale', 'ru');
      renderManager();
      await screen.findByText('Wysokość');
      fireEvent.click(screen.getByRole('button', { name: '+ Добавить группу' }));
      expect(screen.getByText('Описание (необязательно)')).toBeInTheDocument();
      expect(screen.getByLabelText('coefficient-group-description-input')).toHaveAttribute(
        'placeholder',
        'Когда применять, примеры, когда не применять',
      );
    });
  });

  describe('built-in localization and loading state (Stage 12G)', () => {
    const builtinPl = pl.coefficients.builtin.WYSOKOSC_PRACY;
    const builtin: CoefficientGroupRead = {
      ...group,
      id: 'grp-builtin',
      code: 'WYSOKOSC_PRACY',
      display_name: builtinPl.name,
      description: builtinPl.description,
      options: [
        {
          ...group.options[0],
          id: 'opt-builtin',
          group_id: 'grp-builtin',
          code: 'WYSOKA',
          display_name: builtinPl.options.WYSOKA.name,
          description: builtinPl.options.WYSOKA.description,
          percentage: '25.000',
        },
      ],
    };

    it('shows untouched built-ins in Polish and Russian', async () => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [builtin], total: 1 });
      const { unmount } = renderManager();
      expect(await screen.findByText('Wysokość pracy')).toBeInTheDocument();
      expect(screen.getByText('Wysoka')).toBeInTheDocument();
      unmount();

      localStorage.setItem('locale', 'ru');
      renderManager();
      expect(await screen.findByText('Высота работ')).toBeInTheDocument();
      expect(screen.getByText('Высокая')).toBeInTheDocument();
      expect(screen.queryByText('Wysokość pracy')).not.toBeInTheDocument();
    });

    it('shows owner-customized built-in names and descriptions as stored, even in Russian', async () => {
      const customized: CoefficientGroupRead = {
        ...builtin,
        display_name: 'Moja wysokość',
        description: 'Mój opis grupy',
        options: [{ ...builtin.options[0], display_name: 'Rusztowanie', description: 'Mój opis opcji' }],
      };
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [customized], total: 1 });
      localStorage.setItem('locale', 'ru');
      renderManager();
      expect(await screen.findByText('Moja wysokość')).toBeInTheDocument();
      expect(screen.getByText('Mój opis grupy')).toBeInTheDocument();
      expect(screen.getByText('Rusztowanie')).toBeInTheDocument();
      expect(screen.getByText('Mój opis opcji')).toBeInTheDocument();
    });

    it('prefills the edit form with the stored (canonical) value, not the translation', async () => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [builtin], total: 1 });
      localStorage.setItem('locale', 'ru');
      renderManager();
      await screen.findByText('Высота работ');
      fireEvent.click(screen.getAllByRole('button', { name: 'Редактировать' })[0]);
      expect(screen.getByLabelText('coefficient-group-description-edit')).toHaveValue(builtinPl.description);
    });

    it('shows loading, not the empty state, until the first response arrives', async () => {
      let resolve!: (value: { items: CoefficientGroupRead[]; total: number }) => void;
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockReturnValue(
        new Promise((r) => {
          resolve = r;
        }),
      );
      renderManager();
      expect(screen.getByText('Ładowanie współczynników...')).toBeInTheDocument();
      expect(screen.queryByText('Brak zdefiniowanych grup współczynników.')).not.toBeInTheDocument();

      resolve({ items: [], total: 0 });
      expect(await screen.findByText('Brak zdefiniowanych grup współczynników.')).toBeInTheDocument();
      expect(screen.queryByText('Ładowanie współczynników...')).not.toBeInTheDocument();
    });

    it('uses the localized percentage placeholder', async () => {
      localStorage.setItem('locale', 'ru');
      renderManager();
      await screen.findByText('Wysokość');
      fireEvent.click(screen.getByRole('button', { name: '+ Добавить опцию' }));
      expect(document.querySelector('input[inputmode="decimal"]')).toHaveAttribute(
        'placeholder',
        'напр. 20 или -10',
      );
    });
  });
});
