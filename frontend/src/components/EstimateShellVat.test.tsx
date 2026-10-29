/** V2-6 — net / VAT / gross in the estimate header and the VAT selector of a DRAFT estimate. */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as estimatesApi from '../api/estimates';
import { I18nProvider } from '../hooks/useI18n';
import type { EstimateRead, EstimateSummaryRead } from '../types/estimate';
import { EstimateShell } from './EstimateShell';

vi.mock('../api/estimates', () => ({
  getEstimate: vi.fn(),
  setEstimateVat: vi.fn(),
  patchEstimateLine: vi.fn(),
  previewEstimateRegeneration: vi.fn(),
  regenerateEstimate: vi.fn(),
  addManualEstimateLine: vi.fn(),
  deleteEstimateLine: vi.fn(),
  finalizeEstimate: vi.fn(),
}));

const PROJECT_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

function summary(overrides: Partial<EstimateSummaryRead> = {}): EstimateSummaryRead {
  return {
    id: 'est-1', project_id: PROJECT_ID, version: 1, status: 'DRAFT', name: null, total: '2837.12', currency: 'PLN',
    vat_mode: null, vat_rate_percent: null, vat_amount: null, gross_total: null,
    created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-20T10:00:00Z',
    ...overrides,
  };
}

function show(estimate: EstimateSummaryRead, lang: 'pl' | 'ru' = 'pl') {
  localStorage.setItem('locale', lang);
  const detail: EstimateRead = { ...estimate, lines: [] };
  vi.mocked(estimatesApi.getEstimate).mockResolvedValue(detail);
  render(
    <I18nProvider>
      <EstimateShell estimate={estimate} onBack={vi.fn()} selectedGroupKey={null} onGroupKeyChange={vi.fn()} />
    </I18nProvider>,
  );
}

describe('EstimateShell VAT (V2-6)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('shows no VAT rows while the VAT is not set', async () => {
    show(summary());
    await screen.findByLabelText('estimate-vat-select');
    expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('2837,12 PLN');
    expect(screen.queryByLabelText('estimate-shell-vat')).toBeNull();
    expect(screen.queryByLabelText('estimate-shell-gross')).toBeNull();
    expect(screen.getByLabelText('estimate-vat-select')).toHaveValue('');
  });

  it('shows net, VAT and gross for a rate', async () => {
    show(summary({ vat_mode: 'RATE', vat_rate_percent: 23, vat_amount: '652.54', gross_total: '3489.66' }));
    await screen.findByLabelText('estimate-vat-select');
    expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('2837,12 PLN');
    expect(screen.getByLabelText('estimate-shell-vat').textContent).toBe('652,54 PLN');
    expect(screen.getByLabelText('estimate-shell-gross').textContent).toBe('3489,66 PLN');
    expect(screen.getByLabelText('estimate-vat-select')).toHaveValue('23');
  });

  it('says zw. for an exempt estimate, in Russian too', async () => {
    show(summary({ vat_mode: 'EXEMPT' }), 'ru');
    expect(await screen.findByLabelText('estimate-shell-vat-exempt')).toHaveTextContent('НДС: zw. (освобождён)');
    expect(screen.getByLabelText('estimate-vat-select')).toHaveValue('EXEMPT');
  });

  it('sends the chosen rate and shows the answer without reloading the lines', async () => {
    show(summary());
    const select = await screen.findByLabelText('estimate-vat-select');
    vi.mocked(estimatesApi.setEstimateVat).mockResolvedValue(
      summary({ vat_mode: 'RATE', vat_rate_percent: 8, vat_amount: '226.97', gross_total: '3064.09' }),
    );
    fireEvent.change(select, { target: { value: '8' } });
    await waitFor(() => expect(screen.getByLabelText('estimate-shell-gross').textContent).toBe('3064,09 PLN'));
    expect(estimatesApi.setEstimateVat).toHaveBeenCalledWith(PROJECT_ID, 'est-1', { vat_mode: 'RATE', vat_rate_percent: 8, vat_included: false });
    expect(estimatesApi.getEstimate).toHaveBeenCalledTimes(1);
  });

  it('sends null/null when the VAT is cleared and reports a failure', async () => {
    show(summary({ vat_mode: 'EXEMPT' }));
    const select = await screen.findByLabelText('estimate-vat-select');
    vi.mocked(estimatesApi.setEstimateVat).mockRejectedValue(new Error('net'));
    fireEvent.change(select, { target: { value: '' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zmienić stawki VAT.');
    expect(estimatesApi.setEstimateVat).toHaveBeenCalledWith(PROJECT_ID, 'est-1', { vat_mode: null, vat_rate_percent: null });
  });

  it('has no VAT selector on a FINAL estimate and keeps touch-sized control on a draft', async () => {
    show(summary({ status: 'FINAL', vat_mode: 'RATE', vat_rate_percent: 23, vat_amount: '652.54', gross_total: '3489.66' }));
    await screen.findByLabelText('estimate-shell-gross');
    expect(screen.queryByLabelText('estimate-vat-select')).toBeNull();
  });

  describe('prices that already include the VAT (owner 2026-10-27)', () => {
    it('offers the checkbox only with a rate', async () => {
      show(summary({ vat_mode: 'EXEMPT' }));
      await screen.findByLabelText('estimate-vat-select');
      expect(screen.queryByLabelText('estimate-vat-included')).toBeNull();
    });

    it('takes the VAT out of the sum when ticked: net, VAT and gross from the server', async () => {
      show(summary({ vat_mode: 'RATE', vat_rate_percent: 8, vat_amount: '226.97', gross_total: '3064.09', net_total: '2837.12', vat_included: false }));
      const box = await screen.findByLabelText('estimate-vat-included');
      expect(box).not.toBeChecked();
      expect(screen.getByText('VAT jest doliczany do sumy: suma pozycji to netto.')).toBeInTheDocument();
      vi.mocked(estimatesApi.setEstimateVat).mockResolvedValue(
        summary({ vat_mode: 'RATE', vat_rate_percent: 8, vat_included: true, net_total: '2626.96', vat_amount: '210.16', gross_total: '2837.12' }),
      );
      fireEvent.click(box);
      await waitFor(() => expect(screen.getByLabelText('estimate-shell-gross').textContent).toBe('2837,12 PLN'));
      expect(estimatesApi.setEstimateVat).toHaveBeenCalledWith(PROJECT_ID, 'est-1', { vat_mode: 'RATE', vat_rate_percent: 8, vat_included: true });
      expect(screen.getByLabelText('estimate-shell-total').textContent).toBe('2626,96 PLN');
      expect(screen.getByLabelText('estimate-shell-vat').textContent).toBe('210,16 PLN');
      expect(screen.getByLabelText('estimate-vat-included')).toBeChecked();
      expect(screen.getByText('Ceny zawierają VAT')).toBeInTheDocument();
    });

    it('keeps "included" when the rate is changed, and speaks Russian', async () => {
      show(summary({ vat_mode: 'RATE', vat_rate_percent: 8, vat_included: true, net_total: '2626.96', vat_amount: '210.16', gross_total: '2837.12' }), 'ru');
      const select = await screen.findByLabelText('estimate-vat-select');
      expect(screen.getByText('Цены уже с НДС')).toBeInTheDocument();
      vi.mocked(estimatesApi.setEstimateVat).mockResolvedValue(summary({ vat_mode: 'RATE', vat_rate_percent: 23, vat_included: true, net_total: '2306.60', vat_amount: '530.52', gross_total: '2837.12' }));
      fireEvent.change(select, { target: { value: '23' } });
      await waitFor(() => expect(estimatesApi.setEstimateVat).toHaveBeenCalledWith(PROJECT_ID, 'est-1', { vat_mode: 'RATE', vat_rate_percent: 23, vat_included: true }));
      expect(screen.getByLabelText('estimate-vat-included').closest('label')?.className).toContain('min-h-11');
    });
  });
});
