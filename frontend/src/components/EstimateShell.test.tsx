/**
 * Stage 10G.1 — EstimateShell component tests.
 *
 * The shell renders the estimate header for 10G.1: version, status, total.
 * Line editor is deferred to 10G.2.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import type { EstimateSummaryRead } from '../types/estimate';
import { EstimateShell } from './EstimateShell';

const PROJECT_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

function makeEstimate(overrides: Partial<EstimateSummaryRead> = {}): EstimateSummaryRead {
  return {
    id: 'est-1',
    project_id: PROJECT_ID,
    version: 1,
    status: 'DRAFT',
    name: null,
    total: null,
    currency: 'PLN',
    created_at: '2026-09-17T10:00:00Z',
    updated_at: '2026-09-17T10:00:00Z',
    ...overrides,
  };
}

function renderShell(estimate: EstimateSummaryRead) {
  return render(
    <I18nProvider>
      <EstimateShell estimate={estimate} onBack={vi.fn()} />
    </I18nProvider>,
  );
}

describe('EstimateShell', () => {
  it('renders estimate shell container', () => {
    renderShell(makeEstimate());
    expect(screen.getByLabelText('estimate-shell')).toBeTruthy();
  });

  it('shows version number', () => {
    renderShell(makeEstimate({ version: 3 }));
    expect(screen.getByLabelText('estimate-shell').textContent).toContain('3');
  });

  it('shows DRAFT status label (PL)', () => {
    renderShell(makeEstimate({ status: 'DRAFT' }));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Szkic');
  });

  it('shows FINAL status label (PL)', () => {
    renderShell(makeEstimate({ status: 'FINAL' }));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Finalny');
  });

  it('shows ACCEPTED status label (PL)', () => {
    renderShell(makeEstimate({ status: 'ACCEPTED' }));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Zaakceptowany');
  });

  it('shows ARCHIVED status label (PL)', () => {
    renderShell(makeEstimate({ status: 'ARCHIVED' }));
    expect(screen.getByLabelText('estimate-shell-status').textContent).toBe('Archiwalny');
  });

  it('shows total when present', () => {
    renderShell(makeEstimate({ total: '5678.00', currency: 'PLN' }));
    expect(screen.getByLabelText('estimate-shell').textContent).toContain('5678.00');
    expect(screen.getByLabelText('estimate-shell').textContent).toContain('PLN');
  });

  it('shows — for null total', () => {
    renderShell(makeEstimate({ total: null }));
    expect(screen.getByLabelText('estimate-shell').textContent).toContain('—');
  });

  it('shows estimate name when present', () => {
    renderShell(makeEstimate({ name: 'Kosztorys bazowy' }));
    expect(screen.getByText('Kosztorys bazowy')).toBeTruthy();
  });

});
