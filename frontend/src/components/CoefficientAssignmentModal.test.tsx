/**
 * Stage 12F — CoefficientAssignmentModal: modal-local selection, SINGLE_SELECT
 * per group, additive multi-group total, "Brak" vs explicit is_base option,
 * and Apply/Cancel semantics (the modal itself never persists).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as coefficientsApi from '../api/coefficients';
import { I18nProvider } from '../hooks/useI18n';
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

describe('CoefficientAssignmentModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: groups, total: groups.length });
  });

  it('defaults every group to "Brak" and hides archived options', async () => {
    renderModal();
    await screen.findByRole('radio', { name: /wysoka/ });
    const none = screen.getAllByRole('radio', { name: /Brak/ });
    expect(none).toHaveLength(2);
    none.forEach((radio) => expect(radio).toBeChecked());
    expect(screen.queryByText('stara opcja')).not.toBeInTheDocument();
    expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledWith({ archived: 'active' });
  });

  it('combines options from different groups additively and previews the effective price', async () => {
    const { props } = renderModal();
    fireEvent.click(await screen.findByRole('radio', { name: /wysoka/ }));
    fireEvent.click(screen.getByRole('radio', { name: /umeblowane/ }));

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
    fireEvent.click(await screen.findByRole('radio', { name: /wysoka/ }));
    fireEvent.click(screen.getByRole('radio', { name: /normalna/ }));
    fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
    const applied = vi.mocked(props.onApply).mock.calls[0][0];
    expect(applied.map((o) => o.id)).toEqual(['opt-normal']);
  });

  it('preserves an explicit is_base 0% option as a real option id, distinct from "Brak"', async () => {
    const { props } = renderModal();
    fireEvent.click(await screen.findByRole('radio', { name: /normalna/ }));
    fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
    const applied = vi.mocked(props.onApply).mock.calls[0][0];
    expect(applied).toEqual([
      expect.objectContaining({ id: 'opt-normal', group_id: 'grp-height', percentage: '0.00', is_base: true }),
    ]);
  });

  it('applies an empty list when every group is "Brak"', async () => {
    const { props } = renderModal({ initialOptionIds: ['opt-high'] });
    const high = await screen.findByRole('radio', { name: /wysoka/ });
    expect(high).toBeChecked();
    fireEvent.click(screen.getAllByRole('radio', { name: /Brak/ })[0]);
    fireEvent.click(screen.getByLabelText('coefficient-modal-apply'));
    expect(props.onApply).toHaveBeenCalledWith([]);
  });

  it('Cancel discards local changes without applying', async () => {
    const { props } = renderModal();
    fireEvent.click(await screen.findByRole('radio', { name: /wysoka/ }));
    fireEvent.click(screen.getByLabelText('coefficient-modal-cancel'));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(props.onApply).not.toHaveBeenCalled();
  });

  it('keeps NULL base price unresolved instead of treating it as zero', async () => {
    renderModal({ basePrice: null });
    fireEvent.click(await screen.findByRole('radio', { name: /wysoka/ }));
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
    fireEvent.click(await screen.findByRole('radio', { name: /wysoka/ }));
    rerender(
      <I18nProvider>
        <CoefficientAssignmentModal {...props} initialOptionIds={[]} />
      </I18nProvider>,
    );
    await waitFor(() => expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('radio', { name: /wysoka/ })).toBeChecked();
  });
});
