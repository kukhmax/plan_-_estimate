/**
 * Stage 12F — CoefficientAssignmentModal: modal-local selection, SINGLE_SELECT
 * per group, additive multi-group total, "Brak" vs explicit is_base option,
 * and Apply/Cancel semantics (the modal itself never persists).
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as coefficientsApi from '../api/coefficients';
import { I18nProvider } from '../hooks/useI18n';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import { CoefficientGroupRead, CoefficientOptionRead } from '../types/coefficient';
import { CoefficientAssignmentModal, CoefficientAssignmentModalProps } from './CoefficientAssignmentModal';

vi.mock('../api/coefficients', () => ({
  fetchCoefficientGroups: vi.fn(),
}));

function makeOption(overrides: Partial<CoefficientOptionRead>): CoefficientOptionRead {
  return {
    id: 'opt',
    group_id: 'grp-height',
    code: 'OPT',
    name_key: null,
    display_name: 'Opcja',
    description: null,
    percentage: '0.00',
    is_base: false,
    position: 0,
    is_archived: false,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

const groups: CoefficientGroupRead[] = [
  {
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
      makeOption({ id: 'opt-normal', code: 'NORMAL', display_name: 'normalna', percentage: '0.00', is_base: true }),
      makeOption({ id: 'opt-high', code: 'HIGH', display_name: 'wysoka', percentage: '20.00', position: 1 }),
    ],
  },
  {
    id: 'grp-furniture',
    code: 'FURNITURE',
    name_key: null,
    display_name: 'Umeblowanie',
    description: null,
    selection_mode: 'SINGLE_SELECT',
    position: 1,
    is_archived: false,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    options: [
      makeOption({ id: 'opt-furnished', group_id: 'grp-furniture', code: 'FURNISHED', display_name: 'umeblowane', percentage: '10.00' }),
      makeOption({ id: 'opt-old', group_id: 'grp-furniture', code: 'OLD', display_name: 'stara opcja', percentage: '5.00', is_archived: true }),
    ],
  },
];

function renderModal(overrides: Partial<CoefficientAssignmentModalProps> = {}) {
  const props: CoefficientAssignmentModalProps = {
    isOpen: true,
    occurrenceName: 'Szpachlowanie',
    basePrice: '40.00',
    currency: 'PLN',
    initialOptionIds: [],
    onApply: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  };
  const utils = render(
    <I18nProvider>
      <CoefficientAssignmentModal {...props} />
    </I18nProvider>,
  );
  return { ...utils, props };
}

function toggle(groupId: string) {
  return screen.getByTestId(`coefficient-group-toggle-${groupId}`);
}

function summary(groupId: string) {
  return screen.getByTestId(`coefficient-group-summary-${groupId}`);
}

function percent(groupId: string) {
  return screen.getByTestId(`coefficient-group-percent-${groupId}`);
}

/** Expand the group (if collapsed) and pick the option by its visible name. */
async function choose(groupId: string, name: RegExp) {
  const button = await screen.findByTestId(`coefficient-group-toggle-${groupId}`);
  if (button.getAttribute('aria-expanded') !== 'true') fireEvent.click(button);
  fireEvent.click(screen.getByRole('radio', { name }));
}

describe('CoefficientAssignmentModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: groups, total: groups.length });
  });

  it('defaults every group to "Brak" and hides archived options', async () => {
    renderModal();
    await screen.findByTestId('coefficient-group-toggle-grp-height');
    expect(summary('grp-height')).toHaveTextContent('Brak');
    expect(summary('grp-furniture')).toHaveTextContent('Brak');
    fireEvent.click(toggle('grp-furniture'));
    expect(screen.getByRole('radio', { name: /Brak/ })).toBeChecked();
    expect(screen.queryByText('stara opcja')).not.toBeInTheDocument();
    expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledWith({ archived: 'active' });
  });

  it('combines options from different groups additively and previews the effective price', async () => {
    const { props } = renderModal();
    await choose('grp-height', /wysoka/);
    await choose('grp-furniture', /umeblowane/);

    // 40.00 × (1 + 30/100) = 52.00 — additive, never compounded (40 × 1.2 × 1.1 = 52.80).
    expect(screen.getByText('+30%')).toBeInTheDocument();
    expect(screen.getByText('52.00 PLN')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
    expect(props.onApply).toHaveBeenCalledTimes(1);
    const applied = vi.mocked(props.onApply).mock.calls[0][0];
    expect(applied.map((o) => o.id)).toEqual(['opt-high', 'opt-furnished']);
  });

  it('keeps a single selection per SINGLE_SELECT group', async () => {
    const { props } = renderModal();
    await choose('grp-height', /wysoka/);
    await choose('grp-height', /normalna/);
    fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
    const applied = vi.mocked(props.onApply).mock.calls[0][0];
    expect(applied.map((o) => o.id)).toEqual(['opt-normal']);
  });

  it('preserves an explicit is_base 0% option as a real option id, distinct from "Brak"', async () => {
    const { props } = renderModal();
    await choose('grp-height', /normalna/);
    fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
    const applied = vi.mocked(props.onApply).mock.calls[0][0];
    expect(applied).toEqual([
      expect.objectContaining({ id: 'opt-normal', group_id: 'grp-height', percentage: '0.00', is_base: true }),
    ]);
  });

  it('applies an empty list when every group is "Brak"', async () => {
    const { props } = renderModal({ initialOptionIds: ['opt-high'] });
    await screen.findByTestId('coefficient-group-toggle-grp-height');
    expect(summary('grp-height')).toHaveTextContent('wysoka');
    fireEvent.click(toggle('grp-height'));
    expect(screen.getByRole('radio', { name: /wysoka/ })).toBeChecked();
    fireEvent.click(screen.getByRole('radio', { name: /Brak/ }));
    fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
    expect(props.onApply).toHaveBeenCalledWith([]);
  });

  it('Cancel discards local changes without applying', async () => {
    const { props } = renderModal();
    await choose('grp-height', /wysoka/);
    fireEvent.click(screen.getByLabelText('coefficient-modal-cancel'));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(props.onApply).not.toHaveBeenCalled();
  });

  it('keeps NULL base price unresolved instead of treating it as zero', async () => {
    renderModal({ basePrice: null });
    await choose('grp-height', /wysoka/);
    expect(screen.getAllByText('Do ustalenia')).toHaveLength(2);
    expect(screen.queryByText(/0\.00 PLN/)).not.toBeInTheDocument();
  });

  it('disables Apply when the catalog fails to load so existing selections are not wiped', async () => {
    vi.mocked(coefficientsApi.fetchCoefficientGroups).mockRejectedValue(new Error('boom'));
    const { props } = renderModal({ initialOptionIds: ['opt-high'] });
    await screen.findByText('boom');
    const apply = screen.getByLabelText('coefficient-modal-apply');
    expect(apply).toBeDisabled();
    fireEvent.click(apply);
    expect(props.onApply).not.toHaveBeenCalled();
  });

  it('does not refetch or reset local selection when re-rendered with an equal id list', async () => {
    const { props, rerender } = renderModal({ initialOptionIds: [] });
    await choose('grp-height', /wysoka/);
    rerender(
      <I18nProvider>
        <CoefficientAssignmentModal {...props} initialOptionIds={[]} />
      </I18nProvider>,
    );
    await waitFor(() => expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('radio', { name: /wysoka/ })).toBeChecked();
  });

  describe('accordion (owner walkthrough UX)', () => {
    it('renders every group collapsed initially with a compact summary', async () => {
      renderModal({ initialOptionIds: ['opt-high'] });
      await screen.findByTestId('coefficient-group-toggle-grp-height');
      expect(toggle('grp-height')).toHaveAttribute('aria-expanded', 'false');
      expect(toggle('grp-furniture')).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryAllByRole('radio')).toHaveLength(0);
      expect(toggle('grp-height').className).toContain('min-h-[44px]');
      expect(summary('grp-height')).toHaveTextContent('wysoka');
      expect(percent('grp-height')).toHaveTextContent('+20%');
      expect(summary('grp-furniture')).toHaveTextContent('Brak');
      expect(percent('grp-furniture')).toHaveTextContent('—');
    });

    it('expands one group at a time and collapses it on a second tap', async () => {
      renderModal();
      await screen.findByTestId('coefficient-group-toggle-grp-height');
      fireEvent.click(toggle('grp-height'));
      expect(toggle('grp-height')).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('radio', { name: /wysoka/ })).toBeInTheDocument();

      fireEvent.click(toggle('grp-furniture'));
      expect(toggle('grp-height')).toHaveAttribute('aria-expanded', 'false');
      expect(toggle('grp-furniture')).toHaveAttribute('aria-expanded', 'true');
      expect(screen.queryByRole('radio', { name: /wysoka/ })).not.toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /umeblowane/ })).toBeInTheDocument();

      fireEvent.click(toggle('grp-furniture'));
      expect(toggle('grp-furniture')).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryAllByRole('radio')).toHaveLength(0);
    });

    it('updates the collapsed summary on selection and never changes the draft by toggling', async () => {
      const { props } = renderModal();
      await choose('grp-height', /wysoka/);
      expect(summary('grp-height')).toHaveTextContent('wysoka');
      expect(percent('grp-height')).toHaveTextContent('+20%');

      for (let i = 0; i < 3; i += 1) {
        fireEvent.click(toggle('grp-furniture'));
        fireEvent.click(toggle('grp-height'));
      }
      expect(summary('grp-height')).toHaveTextContent('wysoka');
      expect(summary('grp-furniture')).toHaveTextContent('Brak');
      expect(props.onApply).not.toHaveBeenCalled();

      fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
      expect(vi.mocked(props.onApply).mock.calls[0][0].map((o) => o.id)).toEqual(['opt-high']);
    });

    it('shows Brak distinctly from an explicit 0% base (0% · BAZA)', async () => {
      renderModal();
      await screen.findByTestId('coefficient-group-toggle-grp-height');
      expect(summary('grp-height')).toHaveTextContent('Brak');
      expect(summary('grp-height')).not.toHaveTextContent('Baza');
      expect(percent('grp-height')).toHaveTextContent('—');

      await choose('grp-height', /normalna/);
      expect(summary('grp-height')).toHaveTextContent('normalna');
      expect(summary('grp-height')).toHaveTextContent('Baza');
      expect(summary('grp-height')).not.toHaveTextContent('Brak');
      expect(percent('grp-height')).toHaveTextContent('0%');
    });
  });

  describe('descriptions (Stage 12G)', () => {
    const described: CoefficientGroupRead[] = [
      {
        ...groups[0],
        description: 'Opis grupy wysokości',
        options: [
          groups[0].options[0],
          { ...groups[0].options[1], description: 'Opis opcji wysoka' },
        ],
      },
      groups[1],
    ];

    beforeEach(() => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({
        items: described,
        total: described.length,
      });
    });

    it('shows info controls only where a description exists', async () => {
      renderModal();
      expect(await screen.findByTestId('coefficient-group-info-grp-height')).toBeInTheDocument();
      expect(screen.queryByTestId('coefficient-group-info-grp-furniture')).not.toBeInTheDocument();
      fireEvent.click(toggle('grp-height'));
      expect(screen.getByTestId('coefficient-option-info-opt-high')).toBeInTheDocument();
      expect(screen.queryByTestId('coefficient-option-info-opt-normal')).not.toBeInTheDocument();
      fireEvent.click(toggle('grp-furniture'));
      expect(screen.queryByTestId('coefficient-option-info-opt-furnished')).not.toBeInTheDocument();
      expect(screen.getByTestId('coefficient-group-info-grp-height')).toHaveAccessibleName(
        'Pokaż opis: Wysokość',
      );
      expect(screen.getByTestId('coefficient-group-info-grp-height').className).toContain('min-h-[44px]');
    });

    it('group info does not toggle the accordion', async () => {
      renderModal();
      fireEvent.click(await screen.findByTestId('coefficient-group-info-grp-height'));
      expect(screen.getByTestId('coefficient-description-sheet')).toHaveTextContent('Opis grupy wysokości');
      expect(toggle('grp-height')).toHaveAttribute('aria-expanded', 'false');
      fireEvent.click(
        within(screen.getByTestId('coefficient-description-sheet')).getAllByRole('button', { name: 'Zamknij' })[0],
      );
      expect(toggle('grp-height')).toHaveAttribute('aria-expanded', 'false');
    });

    it('opens and closes the description sheet without touching the draft or accordion state', async () => {
      const { props } = renderModal();
      await choose('grp-furniture', /umeblowane/);
      fireEvent.click(toggle('grp-height'));

      fireEvent.click(screen.getByTestId('coefficient-option-info-opt-high'));
      const sheet = screen.getByTestId('coefficient-description-sheet');
      expect(sheet).toHaveTextContent('Opis opcji wysoka');
      fireEvent.click(
        within(screen.getByTestId('coefficient-description-sheet')).getAllByRole('button', { name: 'Zamknij' })[0],
      );
      expect(screen.queryByTestId('coefficient-description-sheet')).not.toBeInTheDocument();
      // Same group still expanded, "wysoka" not selected by opening its info.
      expect(toggle('grp-height')).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('radio', { name: /wysoka/ })).not.toBeChecked();

      fireEvent.click(screen.getByTestId('coefficient-group-info-grp-height'));
      expect(screen.getByTestId('coefficient-description-sheet')).toHaveTextContent('Opis grupy wysokości');
      fireEvent.click(screen.getByTestId('coefficient-description-sheet'));
      expect(screen.queryByTestId('coefficient-description-sheet')).not.toBeInTheDocument();
      expect(toggle('grp-height')).toHaveAttribute('aria-expanded', 'true');

      expect(summary('grp-furniture')).toHaveTextContent('umeblowane');
      expect(summary('grp-height')).toHaveTextContent('Brak');
      expect(props.onApply).not.toHaveBeenCalled();
      expect(props.onCancel).not.toHaveBeenCalled();
      expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledTimes(1);

      fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
      expect(vi.mocked(props.onApply).mock.calls[0][0].map((o) => o.id)).toEqual(['opt-furnished']);
    });
  });

  describe('high total correction warning (Stage 12G)', () => {
    const warningGroups: CoefficientGroupRead[] = [
      {
        ...groups[0],
        id: 'g-a',
        display_name: 'A',
        options: [
          makeOption({ id: 'a-base', group_id: 'g-a', display_name: 'a-base', percentage: '0.000', is_base: true }),
          makeOption({ id: 'a-30', group_id: 'g-a', display_name: 'a-30', percentage: '30.000' }),
        ],
      },
      {
        ...groups[0],
        id: 'g-b',
        display_name: 'B',
        options: [
          makeOption({ id: 'b-20', group_id: 'g-b', display_name: 'b-20', percentage: '20.000' }),
          makeOption({ id: 'b-205', group_id: 'g-b', display_name: 'b-205', percentage: '20.500' }),
        ],
      },
      {
        ...groups[0],
        id: 'g-c',
        display_name: 'C',
        options: [makeOption({ id: 'c-neg', group_id: 'g-c', display_name: 'c-neg', percentage: '-10.000' })],
      },
    ];

    beforeEach(() => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({
        items: warningGroups,
        total: warningGroups.length,
      });
    });

    it('is absent at exactly +50% and present above it, without blocking Zastosuj', async () => {
      const { props } = renderModal();
      await choose('g-a', /a-30/);
      await choose('g-b', /b-20\b/);
      expect(screen.getByText('+50%')).toBeInTheDocument();
      expect(screen.queryByLabelText('coefficient-high-total-warning')).not.toBeInTheDocument();

      await choose('g-b', /b-205/);
      const warning = screen.getByLabelText('coefficient-high-total-warning');
      expect(warning).toHaveTextContent('Wysoka łączna korekta ceny (+50.5%).');
      expect(warning).toHaveTextContent('czy ich wpływ nie został już uwzględniony w cenie bazowej');

      const apply = screen.getByLabelText('coefficient-modal-apply');
      expect(apply).toBeEnabled();
      fireEvent.click(apply);
      expect(vi.mocked(props.onApply).mock.calls[0][0].map((o) => o.id)).toEqual(['a-30', 'b-205']);
    });

    it('counts negative coefficients and the explicit 0% base additively', async () => {
      renderModal();
      await choose('g-a', /a-30/);
      await choose('g-b', /b-205/);
      expect(screen.getByLabelText('coefficient-high-total-warning')).toBeInTheDocument();

      await choose('g-c', /c-neg/);
      expect(screen.getByText('+40.5%')).toBeInTheDocument();
      expect(percent('g-c')).toHaveTextContent('-10%');
      expect(screen.queryByLabelText('coefficient-high-total-warning')).not.toBeInTheDocument();

      // Explicit base (0%) replaces +30% in group A: 0 + 20.5 - 10 = +10.5%.
      await choose('g-a', /a-base/);
      expect(screen.getByText('+10.5%')).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /a-base/ })).toBeChecked();
      expect(screen.getByRole('radio', { name: /Brak/ })).not.toBeChecked();
    });

    it('shows the Russian warning text', async () => {
      localStorage.setItem('locale', 'ru');
      renderModal();
      await choose('g-a', /a-30/);
      await choose('g-b', /b-205/);
      expect(screen.getByLabelText('coefficient-high-total-warning')).toHaveTextContent(
        'Высокая суммарная корректировка цены (+50.5%).',
      );
    });
  });

  describe('built-in localization (Stage 12G)', () => {
    const builtinPl = pl.coefficients.builtin.DOSTEP_DO_POWIERZCHNI;
    const builtin: CoefficientGroupRead = {
      ...groups[0],
      id: 'grp-access',
      code: 'DOSTEP_DO_POWIERZCHNI',
      display_name: builtinPl.name,
      description: builtinPl.description,
      options: [
        makeOption({
          id: 'opt-hard',
          group_id: 'grp-access',
          code: 'UTRUDNIONY',
          display_name: builtinPl.options.UTRUDNIONY.name,
          description: builtinPl.options.UTRUDNIONY.description,
          percentage: '10.000',
        }),
        makeOption({
          id: 'opt-own',
          group_id: 'grp-access',
          code: 'CUSTOM_OWN',
          display_name: 'Własna opcja',
          percentage: '5.000',
        }),
      ],
    };

    it('shows untouched built-ins in Russian and custom options as stored', async () => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [builtin], total: 1 });
      localStorage.setItem('locale', 'ru');
      const { props } = renderModal();
      expect(await screen.findByText('Доступ к поверхности')).toBeInTheDocument();
      expect(summary('grp-access')).toHaveTextContent('Нет');
      fireEvent.click(toggle('grp-access'));
      expect(screen.getByRole('radio', { name: /Затруднённый/ })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /Własna opcja/ })).toBeInTheDocument();

      fireEvent.click(screen.getByTestId('coefficient-option-info-opt-hard'));
      expect(screen.getByTestId('coefficient-description-sheet')).toHaveTextContent(
        ru.coefficients.builtin.DOSTEP_DO_POWIERZCHNI.options.UTRUDNIONY.description,
      );
      fireEvent.click(
        within(screen.getByTestId('coefficient-description-sheet')).getAllByRole('button', { name: 'Закрыть' })[0],
      );

      // The applied draft keeps the stored (canonical) catalog values.
      fireEvent.click(screen.getByRole('radio', { name: /Затруднённый/ }));
      expect(summary('grp-access')).toHaveTextContent('Затруднённый');
      fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
      expect(vi.mocked(props.onApply).mock.calls[0][0][0]).toEqual(
        expect.objectContaining({ id: 'opt-hard', display_name: builtinPl.options.UTRUDNIONY.name }),
      );
    });

    it('shows an owner-customized built-in group name as stored in Russian', async () => {
      vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({
        items: [{ ...builtin, display_name: 'Mój dostęp' }],
        total: 1,
      });
      localStorage.setItem('locale', 'ru');
      renderModal();
      expect(await screen.findByText('Mój dostęp')).toBeInTheDocument();
      expect(screen.queryByText('Доступ к поверхности')).not.toBeInTheDocument();
    });
  });

  it('drops an archived option on Zastosuj so an occurrence can be repaired (Stage 12H)', async () => {
    const withArchived: CoefficientGroupRead[] = [
      {
        ...groups[0],
        options: [
          groups[0].options[0],
          { ...groups[0].options[1], is_archived: true },
        ],
      },
      groups[1],
    ];
    vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: withArchived, total: 2 });
    const { props } = renderModal({ initialOptionIds: ['opt-high', 'opt-furnished'] });
    // The archived option is not offered; its group falls back to "Brak".
    await screen.findByTestId('coefficient-group-toggle-grp-height');
    expect(summary('grp-height')).toHaveTextContent('Brak');
    expect(summary('grp-furniture')).toHaveTextContent('umeblowane');
    fireEvent.click(toggle('grp-height'));
    expect(screen.queryByRole('radio', { name: /wysoka/ })).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Brak/ })).toBeChecked();

    fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
    expect(vi.mocked(props.onApply).mock.calls[0][0].map((o) => o.id)).toEqual(['opt-furnished']);
  });

  it('shows the warning just above +50% (Stage 12H boundary)', async () => {
    const boundary: CoefficientGroupRead[] = [
      { ...groups[0], id: 'g1', options: [makeOption({ id: 'x', group_id: 'g1', display_name: 'x', percentage: '50.000' })] },
      { ...groups[0], id: 'g2', options: [makeOption({ id: 'y', group_id: 'g2', display_name: 'y', percentage: '0.001' })] },
    ];
    vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: boundary, total: 2 });
    renderModal();
    await choose('g1', /^x/);
    expect(screen.queryByLabelText('coefficient-high-total-warning')).not.toBeInTheDocument();
    await choose('g2', /^y/);
    expect(screen.getByLabelText('coefficient-high-total-warning')).toHaveTextContent('+50.001%');
    expect(screen.getByLabelText('coefficient-modal-apply')).toBeEnabled();
  });
});
