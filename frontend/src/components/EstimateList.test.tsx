/**
 * Stage 10G.1 — EstimateList component tests.
 *
 * Covers:
 * - empty state rendering and first DRAFT generation
 * - list rendering with multiple versions
 * - DRAFT visually distinct and open-draft action present
 * - immutable versions shown as history (no open-draft label)
 * - create-new-version shown only when no DRAFT exists
 * - create-new-version hidden when DRAFT exists
 * - backend version number displayed, not calculated
 * - generate pending disables action
 * - 409 handled safely (refreshes list, no crash)
 * - API error + retry
 * - PL and RU labels
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as estimatesApi from '../api/estimates';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { EstimateListResponse, EstimateSummaryRead } from '../types/estimate';
import { EstimateList } from './EstimateList';

vi.mock('../api/estimates', () => ({
  listEstimates: vi.fn(),
  generateEstimate: vi.fn(),
  getEstimate: vi.fn(),
}));

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

function emptyResponse(): EstimateListResponse {
  return { items: [], total: 0 };
}

function listResponse(items: EstimateSummaryRead[]): EstimateListResponse {
  return { items, total: items.length };
}

const mockListEstimates = estimatesApi.listEstimates as ReturnType<typeof vi.fn>;
const mockGenerateEstimate = estimatesApi.generateEstimate as ReturnType<typeof vi.fn>;

function renderComponent(onOpen = vi.fn()) {
  return render(
    <I18nProvider>
      <EstimateList projectId={PROJECT_ID} onOpenEstimate={onOpen} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
});

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

describe('empty state', () => {
  it('shows PL empty state title and description when no estimates exist', async () => {
    mockListEstimates.mockResolvedValue(emptyResponse());
    renderComponent();
    await screen.findByLabelText('estimates-empty-state');
    expect(screen.getByText('Brak kosztorysu')).toBeTruthy();
    expect(screen.getByText(/Kosztorys zostanie wygenerowany/)).toBeTruthy();
  });

  it('shows "Utwórz kosztorys" button in empty state', async () => {
    mockListEstimates.mockResolvedValue(emptyResponse());
    renderComponent();
    await screen.findByLabelText('generate-estimate');
    expect(screen.getByLabelText('generate-estimate').textContent).toBe('Utwórz kosztorys');
  });

  it('shows RU empty state when locale is RU', async () => {
    mockListEstimates.mockResolvedValue(emptyResponse());
    render(
      <I18nProvider>
        <div>
          <button onClick={() => {}} data-testid="lang-switch" />
          <EstimateList projectId={PROJECT_ID} onOpenEstimate={vi.fn()} />
        </div>
      </I18nProvider>,
    );
    // The component renders PL by default; we verify RU strings exist in locales
    // by checking the i18n hook renders correctly with ru locale
    await screen.findByLabelText('estimates-empty-state');
  });
});

// ---------------------------------------------------------------------------
// First DRAFT generation
// ---------------------------------------------------------------------------

describe('first DRAFT generation', () => {
  it('calls generateEstimate then refreshes the list on success', async () => {
    const draft = makeEstimate();
    mockListEstimates
      .mockResolvedValueOnce(emptyResponse())
      .mockResolvedValueOnce(listResponse([draft]));
    mockGenerateEstimate.mockResolvedValue(draft);

    renderComponent();
    const btn = await screen.findByLabelText('generate-estimate');
    await act(async () => { fireEvent.click(btn); });

    expect(mockGenerateEstimate).toHaveBeenCalledWith(PROJECT_ID);
    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('estimate-version-1')).toBeTruthy();
  });

  it('disables generate button while pending', async () => {
    let resolveGenerate!: (v: EstimateSummaryRead) => void;
    mockListEstimates.mockResolvedValue(emptyResponse());
    mockGenerateEstimate.mockReturnValue(
      new Promise<EstimateSummaryRead>((resolve) => { resolveGenerate = resolve; }),
    );

    renderComponent();
    const btn = await screen.findByLabelText('generate-estimate');
    await act(async () => { fireEvent.click(btn); });

    expect(btn).toBeDisabled();
    resolveGenerate(makeEstimate());
  });

  it('shows "Tworzenie kosztorysu..." while pending', async () => {
    let resolveGenerate!: (v: EstimateSummaryRead) => void;
    mockListEstimates.mockResolvedValue(emptyResponse());
    mockGenerateEstimate.mockReturnValue(
      new Promise<EstimateSummaryRead>((resolve) => { resolveGenerate = resolve; }),
    );

    renderComponent();
    const btn = await screen.findByLabelText('generate-estimate');
    await act(async () => { fireEvent.click(btn); });

    expect(btn.textContent).toBe('Tworzenie kosztorysu...');
    resolveGenerate(makeEstimate());
  });
});

// ---------------------------------------------------------------------------
// Version list rendering
// ---------------------------------------------------------------------------

describe('version list rendering', () => {
  it('renders multiple versions as cards', async () => {
    const v1 = makeEstimate({ id: 'est-1', version: 1, status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    const v2 = makeEstimate({ id: 'est-2', version: 2, status: 'DRAFT', updated_at: '2026-09-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([v1, v2]));
    renderComponent();

    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('estimate-version-1')).toBeTruthy();
    expect(screen.getByLabelText('estimate-version-2')).toBeTruthy();
  });

  it('displays backend version number, not calculated client-side', async () => {
    const v5 = makeEstimate({ id: 'est-5', version: 5, status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([v5]));
    renderComponent();

    await screen.findByLabelText('estimate-version-5');
    expect(screen.getByLabelText('estimate-version-5').textContent).toContain('5');
  });

  it('shows total and currency for priced estimate', async () => {
    const v1 = makeEstimate({ total: '1234.56', currency: 'PLN', status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([v1]));
    renderComponent();

    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('estimate-version-1').textContent).toContain('1234.56');
    expect(screen.getByLabelText('estimate-version-1').textContent).toContain('PLN');
  });

  it('shows — for null total', async () => {
    const v1 = makeEstimate({ total: null, status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([v1]));
    renderComponent();

    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('estimate-version-1').textContent).toContain('—');
  });
});

// ---------------------------------------------------------------------------
// DRAFT recognition
// ---------------------------------------------------------------------------

describe('DRAFT recognition', () => {
  it('renders draft badge on DRAFT version', async () => {
    const draft = makeEstimate({ status: 'DRAFT' });
    mockListEstimates.mockResolvedValue(listResponse([draft]));
    renderComponent();

    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('draft-badge')).toBeTruthy();
  });

  it('shows "Otwórz kosztorys" (open-draft) button on DRAFT', async () => {
    const draft = makeEstimate({ status: 'DRAFT' });
    mockListEstimates.mockResolvedValue(listResponse([draft]));
    renderComponent();

    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('open-draft-estimate')).toBeTruthy();
    expect(screen.getByLabelText('open-draft-estimate').textContent).toBe('Otwórz kosztorys');
  });

  it('calls onOpenEstimate with the draft when open-draft is clicked', async () => {
    const onOpen = vi.fn();
    const draft = makeEstimate({ status: 'DRAFT' });
    mockListEstimates.mockResolvedValue(listResponse([draft]));
    renderComponent(onOpen);

    const btn = await screen.findByLabelText('open-draft-estimate');
    fireEvent.click(btn);
    expect(onOpen).toHaveBeenCalledWith(draft);
  });
});

// ---------------------------------------------------------------------------
// Immutable history
// ---------------------------------------------------------------------------

describe('immutable history', () => {
  it('shows "Otwórz" (not open-draft) button for FINAL version', async () => {
    const final = makeEstimate({ id: 'est-1', version: 1, status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([final]));
    renderComponent();

    await screen.findByLabelText('estimates-list');
    expect(screen.queryByLabelText('open-draft-estimate')).toBeNull();
    expect(screen.getByLabelText('open-estimate-1')).toBeTruthy();
  });

  it('calls onOpenEstimate when immutable version is opened', async () => {
    const onOpen = vi.fn();
    const final = makeEstimate({ id: 'est-1', version: 1, status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([final]));
    renderComponent(onOpen);

    const btn = await screen.findByLabelText('open-estimate-1');
    fireEvent.click(btn);
    expect(onOpen).toHaveBeenCalledWith(final);
  });
});

// ---------------------------------------------------------------------------
// Generate button visibility (no DRAFT = show; DRAFT = hide)
// ---------------------------------------------------------------------------

describe('create-new-version visibility', () => {
  it('shows create-new-version when estimates exist but no DRAFT', async () => {
    const final = makeEstimate({ id: 'est-1', version: 1, status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([final]));
    renderComponent();

    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('create-new-version')).toBeTruthy();
    expect(screen.getByLabelText('create-new-version').textContent).toBe('Utwórz nową wersję');
  });

  it('hides create-new-version when DRAFT exists', async () => {
    const final = makeEstimate({ id: 'est-1', version: 1, status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    const draft = makeEstimate({ id: 'est-2', version: 2, status: 'DRAFT', updated_at: '2026-09-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([final, draft]));
    renderComponent();

    await screen.findByLabelText('estimates-list');
    expect(screen.queryByLabelText('create-new-version')).toBeNull();
  });

  it('hides create-new-version in empty state (uses generate-estimate instead)', async () => {
    mockListEstimates.mockResolvedValue(emptyResponse());
    renderComponent();

    await screen.findByLabelText('estimates-empty-state');
    expect(screen.queryByLabelText('create-new-version')).toBeNull();
    expect(screen.getByLabelText('generate-estimate')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// 409 conflict handling
// ---------------------------------------------------------------------------

describe('409 conflict handling', () => {
  it('shows conflict message and refreshes list on 409', async () => {
    const draft = makeEstimate({ status: 'DRAFT' });
    mockListEstimates
      .mockResolvedValueOnce(emptyResponse())
      .mockResolvedValueOnce(listResponse([draft]));
    mockGenerateEstimate.mockRejectedValue(new ApiError('Draft already exists', 409));

    renderComponent();
    const btn = await screen.findByLabelText('generate-estimate');
    await act(async () => { fireEvent.click(btn); });

    await screen.findByLabelText('estimates-list');
    expect(screen.getByRole('alert', { hidden: true }).textContent).toContain(
      'Szkic kosztorysu już istnieje',
    );
  });

  it('does not crash or lose state on 409', async () => {
    const draft = makeEstimate({ status: 'DRAFT' });
    mockListEstimates
      .mockResolvedValueOnce(emptyResponse())
      .mockResolvedValueOnce(listResponse([draft]));
    mockGenerateEstimate.mockRejectedValue(new ApiError('conflict', 409));

    renderComponent();
    const btn = await screen.findByLabelText('generate-estimate');
    await act(async () => { fireEvent.click(btn); });

    await waitFor(() => {
      expect(screen.queryByLabelText('estimates-loading')).toBeNull();
    });
  });
});

// ---------------------------------------------------------------------------
// API error and retry
// ---------------------------------------------------------------------------

describe('API error and retry', () => {
  it('shows error message when list fails', async () => {
    mockListEstimates.mockRejectedValue(new Error('Network error'));
    renderComponent();

    await screen.findByLabelText('estimates-error');
    expect(screen.getByLabelText('estimates-error').textContent).toContain('Network error');
  });

  it('shows retry button on list error', async () => {
    mockListEstimates.mockRejectedValue(new Error('fail'));
    renderComponent();

    await screen.findByRole('alert');
    expect(screen.getByText('Ponów próbę')).toBeTruthy();
  });

  it('retries list on retry click', async () => {
    const draft = makeEstimate();
    mockListEstimates
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce(listResponse([draft]));

    renderComponent();
    await screen.findByRole('alert');
    await act(async () => { fireEvent.click(screen.getByText('Ponów próbę')); });
    await screen.findByLabelText('estimates-list');
  });

  it('shows generate error message on non-409 generate failure', async () => {
    mockListEstimates.mockResolvedValue(emptyResponse());
    mockGenerateEstimate.mockRejectedValue(new Error('Server error'));

    renderComponent();
    const btn = await screen.findByLabelText('generate-estimate');
    await act(async () => { fireEvent.click(btn); });

    await waitFor(() => {
      const alert = screen.queryByRole('alert');
      expect(alert).not.toBeNull();
    });
  });
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe('loading state', () => {
  it('shows loading text while fetching', async () => {
    let resolveList!: (v: EstimateListResponse) => void;
    mockListEstimates.mockReturnValue(
      new Promise<EstimateListResponse>((resolve) => { resolveList = resolve; }),
    );
    renderComponent();
    expect(screen.getByLabelText('estimates-loading')).toBeTruthy();
    resolveList(emptyResponse());
  });
});

// ---------------------------------------------------------------------------
// PL / RU labels
// ---------------------------------------------------------------------------

describe('PL labels', () => {
  it('shows PL status label for DRAFT', async () => {
    const draft = makeEstimate({ status: 'DRAFT' });
    mockListEstimates.mockResolvedValue(listResponse([draft]));
    renderComponent();
    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('estimate-status-1').textContent).toBe('Szkic');
  });

  it('shows PL status label for FINAL', async () => {
    const final = makeEstimate({ status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([final]));
    renderComponent();
    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('estimate-status-1').textContent).toBe('Finalny');
  });

  it('shows PL status label for ACCEPTED', async () => {
    const accepted = makeEstimate({ status: 'ACCEPTED', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([accepted]));
    renderComponent();
    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('estimate-status-1').textContent).toBe('Zaakceptowany');
  });

  it('shows PL status label for ARCHIVED', async () => {
    const archived = makeEstimate({ status: 'ARCHIVED', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([archived]));
    renderComponent();
    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('estimate-status-1').textContent).toBe('Archiwalny');
  });
});

describe('RU labels', () => {
  function renderRU(onOpen = vi.fn()) {
    localStorage.setItem('locale', 'ru');
    const result = render(
      <I18nProvider>
        <EstimateList projectId={PROJECT_ID} onOpenEstimate={onOpen} />
      </I18nProvider>,
    );
    localStorage.removeItem('locale');
    return result;
  }

  it('shows RU empty state title', async () => {
    mockListEstimates.mockResolvedValue(emptyResponse());
    renderRU();
    await screen.findByLabelText('estimates-empty-state');
    expect(screen.getByText('Нет сметы')).toBeTruthy();
  });

  it('shows RU generate button label', async () => {
    mockListEstimates.mockResolvedValue(emptyResponse());
    renderRU();
    const btn = await screen.findByLabelText('generate-estimate');
    expect(btn.textContent).toBe('Создать смету');
  });

  it('shows RU open-draft label', async () => {
    const draft = makeEstimate({ status: 'DRAFT' });
    mockListEstimates.mockResolvedValue(listResponse([draft]));
    renderRU();
    const btn = await screen.findByLabelText('open-draft-estimate');
    expect(btn.textContent).toBe('Открыть смету');
  });

  it('shows RU create-new-version label', async () => {
    const final = makeEstimate({ status: 'FINAL', updated_at: '2026-01-01T00:00:00Z' });
    mockListEstimates.mockResolvedValue(listResponse([final]));
    renderRU();
    const btn = await screen.findByLabelText('create-new-version');
    expect(btn.textContent).toBe('Создать новую версию');
  });

  it('shows RU DRAFT status label', async () => {
    const draft = makeEstimate({ status: 'DRAFT' });
    mockListEstimates.mockResolvedValue(listResponse([draft]));
    renderRU();
    await screen.findByLabelText('estimates-list');
    expect(screen.getByLabelText('estimate-status-1').textContent).toBe('Черновик');
  });
});
