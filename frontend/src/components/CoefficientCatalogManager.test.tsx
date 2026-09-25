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

function expand(groupId: string) {
  fireEvent.click(screen.getByTestId(`coefficient-catalog-group-toggle-${groupId}`));
}

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
    expand('grp-height');
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
    expand('grp-height');
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
      await screen.findByText('Wysokość');
      expect(screen.queryByText('Opis grupy')).not.toBeInTheDocument();
      expand('grp-height');
      expect(screen.getByText('Opis grupy')).toBeInTheDocument();
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
      await screen.findByText('Wysokość');
      expand('grp-height');
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
      expand('grp-height');
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
      await screen.findByText('Wysokość');
      expand('grp-height');
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
      expand('grp-builtin');
      expect(screen.getByText('Wysoka')).toBeInTheDocument();
      unmount();

      localStorage.setItem('locale', 'ru');
      renderManager();
      expect(await screen.findByText('Высота работ')).toBeInTheDocument();
      expand('grp-builtin');
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
      expand('grp-builtin');
      expect(screen.getByText('Mój opis grupy')).toBeInTheDocument();
      expect(screen.getByText('Rusztowanie')).toBeInTheDocument();
      expect(screen.getByText('Mój opis opcji')).toBeInTheDocument();
    });

    it('prefills the edit form with the stored (canonical) value, not the translation', async () => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [builtin], total: 1 });
      localStorage.setItem('locale', 'ru');
      renderManager();
      await screen.findByText('Высота работ');
      expand('grp-builtin');
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
      expand('grp-height');
      fireEvent.click(screen.getByRole('button', { name: '+ Добавить опцию' }));
      expect(document.querySelector('input[inputmode="decimal"]')).toHaveAttribute(
        'placeholder',
        'напр. 20 или -10',
      );
    });
  });

  describe('accordion (owner walkthrough UX)', () => {
    const opt = (id: string, groupId: string, name: string, pct: string, isBase = false) => ({
      ...group.options[0],
      id,
      group_id: groupId,
      code: id.toUpperCase(),
      display_name: name,
      percentage: pct,
      is_base: isBase,
    });
    const height: CoefficientGroupRead = {
      ...group,
      id: 'g-height',
      display_name: 'Wysokość pracy',
      options: [
        opt('o-std', 'g-height', 'Standardowa', '0.000', true),
        opt('o-up', 'g-height', 'Podwyższona', '15.000'),
        opt('o-high', 'g-height', 'Wysoka', '25.000'),
      ],
    };
    const access: CoefficientGroupRead = {
      ...group,
      id: 'g-access',
      display_name: 'Dostęp do powierzchni',
      options: [
        opt('o-free', 'g-access', 'Swobodny', '0.000', true),
        opt('o-hard', 'g-access', 'Utrudniony', '10.000'),
      ],
    };
    const toggle = (id: string) => screen.getByTestId(`coefficient-catalog-group-toggle-${id}`);
    const summary = (id: string) => screen.getByTestId(`coefficient-catalog-group-summary-${id}`);

    beforeEach(() => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [height, access], total: 2 });
    });

    it('renders all groups collapsed with name, option count and explicit base', async () => {
      renderManager();
      await screen.findByText('Wysokość pracy');
      expect(toggle('g-height')).toHaveAttribute('aria-expanded', 'false');
      expect(toggle('g-access')).toHaveAttribute('aria-expanded', 'false');
      expect(toggle('g-height').className).toContain('min-h-[44px]');
      expect(summary('g-height')).toHaveTextContent('3 opcje · Baza: Standardowa 0%');
      expect(summary('g-access')).toHaveTextContent('2 opcje · Baza: Swobodny 0%');
      expect(screen.queryByRole('button', { name: 'Edytuj' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '+ Dodaj opcję' })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: '+ Dodaj grupę' })).toBeInTheDocument();
    });

    it('shows a localized no-base summary without inventing a base', async () => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [group], total: 1 });
      renderManager();
      await screen.findByText('Wysokość');
      expect(summary('grp-height')).toHaveTextContent('1 opcja · Brak opcji bazowej');
    });

    it('expands one group at a time, collapses on a second tap, and never calls the API', async () => {
      renderManager();
      await screen.findByText('Wysokość pracy');
      fireEvent.click(toggle('g-height'));
      expect(toggle('g-height')).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByText('Podwyższona')).toBeInTheDocument();

      fireEvent.click(toggle('g-access'));
      expect(toggle('g-height')).toHaveAttribute('aria-expanded', 'false');
      expect(toggle('g-access')).toHaveAttribute('aria-expanded', 'true');
      expect(screen.queryByText('Podwyższona')).not.toBeInTheDocument();
      expect(screen.getByText('Utrudniony')).toBeInTheDocument();

      fireEvent.click(toggle('g-access'));
      expect(toggle('g-access')).toHaveAttribute('aria-expanded', 'false');

      expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledTimes(1);
      expect(coefficientsApi.updateCoefficientGroup).not.toHaveBeenCalled();
      expect(coefficientsApi.archiveCoefficientGroup).not.toHaveBeenCalled();
      expect(coefficientsApi.archiveCoefficientOption).not.toHaveBeenCalled();
      expect(coefficientsApi.createCoefficientOption).not.toHaveBeenCalled();
    });

    it('group edit keeps the group expanded and stays usable through save and reload', async () => {
      vi.mocked(coefficientsApi.updateCoefficientGroup).mockResolvedValue(height);
      renderManager();
      await screen.findByText('Wysokość pracy');
      fireEvent.click(toggle('g-height'));
      fireEvent.click(screen.getAllByRole('button', { name: 'Edytuj' })[0]);
      expect(toggle('g-height')).toHaveAttribute('aria-expanded', 'true');
      const input = screen.getByDisplayValue('Wysokość pracy');
      fireEvent.change(input, { target: { value: 'Wysokość robót' } });
      fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
      await waitFor(() =>
        expect(coefficientsApi.updateCoefficientGroup).toHaveBeenCalledWith('g-height', {
          display_name: 'Wysokość robót',
          description: null,
        }),
      );
      await waitFor(() => expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledTimes(2));
      expect(toggle('g-height')).toHaveAttribute('aria-expanded', 'true');
    });

    it('option edit and add-option open their forms without toggling the group', async () => {
      renderManager();
      await screen.findByText('Wysokość pracy');
      fireEvent.click(toggle('g-height'));
      fireEvent.click(screen.getAllByRole('button', { name: 'Edytuj' })[2]);
      expect(screen.getByDisplayValue('Podwyższona')).toBeInTheDocument();
      expect(screen.getByDisplayValue('15.000')).toBeInTheDocument();
      expect(toggle('g-height')).toHaveAttribute('aria-expanded', 'true');
      fireEvent.click(screen.getByRole('button', { name: 'Anuluj' }));

      fireEvent.click(screen.getByRole('button', { name: '+ Dodaj opcję' }));
      expect(screen.getByPlaceholderText('np. Prace na wysokości > 3m')).toBeInTheDocument();
      expect(toggle('g-height')).toHaveAttribute('aria-expanded', 'true');
    });

    it('archiving an option keeps the group expanded after reload', async () => {
      vi.mocked(coefficientsApi.archiveCoefficientOption).mockResolvedValue(height.options[2]);
      renderManager();
      await screen.findByText('Wysokość pracy');
      fireEvent.click(toggle('g-height'));
      fireEvent.click(screen.getAllByRole('button', { name: 'Archiwizuj' })[3]);
      await waitFor(() => expect(coefficientsApi.archiveCoefficientOption).toHaveBeenCalledWith('o-high'));
      await waitFor(() => expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledTimes(2));
      expect(toggle('g-height')).toHaveAttribute('aria-expanded', 'true');
    });

    it('archiving the expanded group leaves a coherent collapsed list', async () => {
      vi.mocked(coefficientsApi.archiveCoefficientGroup).mockResolvedValue(height);
      renderManager();
      await screen.findByText('Wysokość pracy');
      fireEvent.click(toggle('g-height'));
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [access], total: 1 });
      fireEvent.click(screen.getAllByRole('button', { name: 'Archiwizuj' })[0]);
      await waitFor(() => expect(coefficientsApi.archiveCoefficientGroup).toHaveBeenCalledWith('g-height'));
      await waitFor(() => expect(screen.queryByText('Wysokość pracy')).not.toBeInTheDocument());
      expect(toggle('g-access')).toHaveAttribute('aria-expanded', 'false');
    });

    it('switching tabs never carries an expanded group over, and restore stays coherent', async () => {
      const archived: CoefficientGroupRead = { ...access, id: 'g-old', display_name: 'Stara grupa', is_archived: true };
      vi.mocked(coefficientsApi.restoreCoefficientGroup).mockResolvedValue(archived);
      renderManager();
      await screen.findByText('Wysokość pracy');
      fireEvent.click(toggle('g-height'));

      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [archived], total: 1 });
      fireEvent.click(screen.getByRole('button', { name: 'Zarchiwizowane' }));
      await screen.findByText('Stara grupa');
      expect(toggle('g-old')).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByTestId('coefficient-catalog-group-toggle-g-height')).not.toBeInTheDocument();

      fireEvent.click(toggle('g-old'));
      expect(screen.queryByRole('button', { name: '+ Dodaj opcję' })).not.toBeInTheDocument();
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [], total: 0 });
      fireEvent.click(screen.getAllByRole('button', { name: 'Przywróć' })[0]);
      await waitFor(() => expect(coefficientsApi.restoreCoefficientGroup).toHaveBeenCalledWith('g-old'));
      expect(await screen.findByText('Brak zdefiniowanych grup współczynników.')).toBeInTheDocument();

      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [height, access], total: 2 });
      fireEvent.click(screen.getByRole('button', { name: 'Aktywne' }));
      await screen.findByText('Wysokość pracy');
      expect(toggle('g-height')).toHaveAttribute('aria-expanded', 'false');
    });

    it('summarizes untouched built-ins in Russian and owner-edited names as stored', async () => {
      const builtinPl = pl.coefficients.builtin.WYSOKOSC_PRACY;
      const builtin: CoefficientGroupRead = {
        ...group,
        id: 'g-builtin',
        code: 'WYSOKOSC_PRACY',
        display_name: builtinPl.name,
        description: builtinPl.description,
        options: [
          { ...opt('o-b1', 'g-builtin', builtinPl.options.STANDARDOWA.name, '0.000', true), code: 'STANDARDOWA' },
          { ...opt('o-b2', 'g-builtin', builtinPl.options.WYSOKA.name, '25.000'), code: 'WYSOKA' },
        ],
      };
      const edited: CoefficientGroupRead = {
        ...builtin,
        id: 'g-edited',
        display_name: 'Moja wysokość',
        options: [{ ...builtin.options[0], id: 'o-e1', display_name: 'Z podłogi' }, builtin.options[1]],
      };
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [builtin, edited], total: 2 });
      localStorage.setItem('locale', 'ru');
      renderManager();
      await screen.findByText('Высота работ');
      expect(summary('g-builtin')).toHaveTextContent('2 опции · База: Стандартная 0%');
      expect(screen.getByText('Moja wysokość')).toBeInTheDocument();
      expect(summary('g-edited')).toHaveTextContent('2 опции · База: Z podłogi 0%');
    });
  });
});
