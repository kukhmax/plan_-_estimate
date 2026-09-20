import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as workRecommendationsApi from '../api/workRecommendations';
import * as workPlansApi from '../api/workPlans';
import * as estimatesApi from '../api/estimates';
import { I18nProvider } from '../hooks/useI18n';
import { WorkRecommendationRead } from '../types/workRecommendation';
import { SurfacePriceItemSummaryRead } from '../types/workPlan';
import { RecommendationPanel } from './RecommendationPanel';

vi.mock('../api/workRecommendations', () => ({
  fetchWorkRecommendations: vi.fn(),
  evaluateWorkRecommendations: vi.fn(),
  dismissWorkRecommendation: vi.fn(),
  reconsiderWorkRecommendation: vi.fn(),
}));

function priceItem(overrides: Partial<SurfacePriceItemSummaryRead> = {}): SurfacePriceItemSummaryRead {
  return {
    id: 'price-1',
    code: 'SKIM_M2',
    name_key: null,
    display_name: 'Gładź gipsowa',
    category: 'SKIM_COAT',
    unit: 'M2',
    price_scope: 'LABOR',
    price: '25.00',
    currency: 'PLN',
    is_archived: false,
    quality_level: null,
    ...overrides,
  };
}

function recommendation(overrides: Partial<WorkRecommendationRead> = {}): WorkRecommendationRead {
  return {
    id: 'rec-1',
    trigger_type: 'FINDING',
    trigger_code: 'old_paint_present',
    source_signature: 'sig',
    inspection_id: 'ins-1',
    room_id: 'room-1',
    surface_id: 'surface-1',
    target_kind: 'WALL',
    recommended_work_code: 'SKIM_M2',
    status: 'PENDING',
    is_active: true,
    resolved_at: null,
    accepted_at: null,
    dismissed_at: null,
    resolved_price_item_id: null,
    created_at: '2026-09-20T08:00:00Z',
    updated_at: '2026-09-20T08:00:00Z',
    current_price_item: priceItem(),
    ...overrides,
  };
}

function renderPanel(props: { inspectionId?: string } = {}) {
  return render(
    <I18nProvider>
      <RecommendationPanel
        projectId="proj-1"
        roomId="room-1"
        inspectionId={props.inspectionId ?? 'ins-1'}
      />
    </I18nProvider>,
  );
}

describe('RecommendationPanel (Stage 11D.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [],
      total: 0,
    });
    vi.mocked(workRecommendationsApi.evaluateWorkRecommendations).mockResolvedValue({
      created: 0,
      reactivated: 0,
      unchanged: 0,
      resolved: 0,
      items: [],
      total: 0,
    });
    vi.mocked(workRecommendationsApi.dismissWorkRecommendation).mockResolvedValue(
      recommendation({ status: 'DISMISSED', dismissed_at: '2026-09-20T09:00:00Z' }),
    );
    vi.mocked(workRecommendationsApi.reconsiderWorkRecommendation).mockResolvedValue(
      recommendation({ status: 'PENDING', dismissed_at: null }),
    );
  });

  it('performs a plain GET on initial render and never evaluates automatically (A, B)', async () => {
    renderPanel();
    await waitFor(() =>
      expect(workRecommendationsApi.fetchWorkRecommendations).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        { activity: 'active' },
      ),
    );
    expect(workRecommendationsApi.evaluateWorkRecommendations).not.toHaveBeenCalled();
  });

  it('explicit evaluate calls the evaluate endpoint and refreshes the list (C, D)', async () => {
    vi.mocked(workRecommendationsApi.evaluateWorkRecommendations).mockResolvedValue({
      created: 1,
      reactivated: 0,
      unchanged: 0,
      resolved: 0,
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText('Oceń zalecenia'));
    await waitFor(() =>
      expect(workRecommendationsApi.evaluateWorkRecommendations).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
      ),
    );
    expect(await screen.findByText('Gładź gipsowa')).toBeInTheDocument();
  });

  it('renders a PENDING recommendation with a reachable dismiss action (E)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText('Oczekujące')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Gładź gipsowa — Opcje/));
    expect(screen.getByLabelText(/Gładź gipsowa — Odrzuć/)).toBeInTheDocument();
  });

  it('renders an ACCEPTED recommendation with no lifecycle reversal action (F, S)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ status: 'ACCEPTED', accepted_at: '2026-09-20T09:00:00Z' })],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText('Zaakceptowane')).toBeInTheDocument();
    expect(screen.queryByLabelText(/Opcje/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Odrzuć/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Rozważ ponownie/)).not.toBeInTheDocument();
  });

  it('renders a DISMISSED recommendation with only reconsider available (G)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ status: 'DISMISSED', dismissed_at: '2026-09-20T09:00:00Z' })],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText('Odrzucone')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Gładź gipsowa — Opcje/));
    expect(screen.getByLabelText(/Rozważ ponownie/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Gładź gipsowa — Odrzuć/)).not.toBeInTheDocument();
  });

  it('shows inactive/resolved independently of an ACCEPTED lifecycle status (H)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [
        recommendation({
          status: 'ACCEPTED',
          accepted_at: '2026-09-19T09:00:00Z',
          is_active: false,
          resolved_at: '2026-09-20T10:00:00Z',
        }),
      ],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText('Zaakceptowane')).toBeInTheDocument();
    expect(screen.getByText('Nieaktualne')).toBeInTheDocument();
    expect(screen.getByText('Nieaktualne od 2026-09-20')).toBeInTheDocument();
  });

  it('shows inactive/resolved independently of a PENDING lifecycle status (H)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [
        recommendation({
          is_active: false,
          resolved_at: '2026-09-20T10:00:00Z',
        }),
      ],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText('Oczekujące')).toBeInTheDocument();
    expect(screen.getByText('Nieaktualne')).toBeInTheDocument();
    expect(screen.getByText('Nieaktualne od 2026-09-20')).toBeInTheDocument();
  });

  it('maps the already-accepted conflict to a specific localized message (409)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    vi.mocked(workRecommendationsApi.dismissWorkRecommendation).mockRejectedValue(
      new Error('Cannot dismiss an already-accepted recommendation'),
    );
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Opcje/));
    fireEvent.click(screen.getByLabelText(/Odrzuć/));
    expect(
      await screen.findByText('Tej operacji nie można wykonać dla zaakceptowanego zalecenia.'),
    ).toBeInTheDocument();
  });

  it('sends activity=active/resolved/all explicitly on each tab (I, J, K)', async () => {
    renderPanel();
    await waitFor(() =>
      expect(workRecommendationsApi.fetchWorkRecommendations).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        { activity: 'active' },
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Rozwiązane' }));
    await waitFor(() =>
      expect(workRecommendationsApi.fetchWorkRecommendations).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        { activity: 'resolved' },
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Wszystkie' }));
    await waitFor(() =>
      expect(workRecommendationsApi.fetchWorkRecommendations).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        { activity: 'all' },
      ),
    );
    expect(workRecommendationsApi.evaluateWorkRecommendations).not.toHaveBeenCalled();
  });

  it('shows "Do ustalenia" for a NULL price (L)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: priceItem({ price: null }) })],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText(/Do ustalenia/)).toBeInTheDocument();
  });

  it('renders an explicit zero price distinctly from NULL (M)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: priceItem({ price: '0.00' }) })],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText(/0,00 zł/)).toBeInTheDocument();
  });

  it('shows a compact informational state when no PriceItem currently resolves (N)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: null })],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText('Brak pozycji cennika dla tej pracy.')).toBeInTheDocument();
  });

  it('shows the archived badge when the current PriceItem is archived (O)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: priceItem({ is_archived: true }) })],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText('Zarchiwizowana')).toBeInTheDocument();
  });

  it('dismisses a PENDING recommendation (P)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Opcje/));
    fireEvent.click(screen.getByLabelText(/Odrzuć/));
    await waitFor(() =>
      expect(workRecommendationsApi.dismissWorkRecommendation).toHaveBeenCalledWith(
        'proj-1',
        'rec-1',
      ),
    );
    expect(await screen.findByText('Odrzucone')).toBeInTheDocument();
  });

  it('reconsiders a DISMISSED recommendation (Q)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ status: 'DISMISSED', dismissed_at: '2026-09-20T09:00:00Z' })],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Opcje/));
    fireEvent.click(screen.getByLabelText(/Rozważ ponownie/));
    await waitFor(() =>
      expect(workRecommendationsApi.reconsiderWorkRecommendation).toHaveBeenCalledWith(
        'proj-1',
        'rec-1',
      ),
    );
    expect(await screen.findByText('Oczekujące')).toBeInTheDocument();
  });

  it('never falsely shows active after reconsider when the response remains inactive (R)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [
        recommendation({
          status: 'DISMISSED',
          dismissed_at: '2026-09-20T09:00:00Z',
          is_active: false,
          resolved_at: '2026-09-19T09:00:00Z',
        }),
      ],
      total: 1,
    });
    vi.mocked(workRecommendationsApi.reconsiderWorkRecommendation).mockResolvedValue(
      recommendation({
        status: 'PENDING',
        dismissed_at: null,
        is_active: false,
        resolved_at: '2026-09-19T09:00:00Z',
      }),
    );
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Opcje/));
    fireEvent.click(screen.getByLabelText(/Rozważ ponownie/));
    expect(await screen.findByText('Oczekujące')).toBeInTheDocument();
    expect(screen.getByText('Nieaktualne')).toBeInTheDocument();
  });

  it('disables the acting control while a dismiss request is pending (T)', async () => {
    let resolveDismiss: (value: WorkRecommendationRead) => void = () => undefined;
    vi.mocked(workRecommendationsApi.dismissWorkRecommendation).mockReturnValue(
      new Promise((resolve) => {
        resolveDismiss = resolve;
      }),
    );
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Opcje/));
    const dismissButton = screen.getByLabelText(/Odrzuć/);
    fireEvent.click(dismissButton);
    expect(dismissButton).toBeDisabled();
    fireEvent.click(dismissButton);
    expect(workRecommendationsApi.dismissWorkRecommendation).toHaveBeenCalledTimes(1);
    resolveDismiss(recommendation({ status: 'DISMISSED' }));
    await waitFor(() => expect(dismissButton).not.toBeInTheDocument());
  });

  it('renders API errors using the existing alert convention (U)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockRejectedValue(
      new Error('boom'),
    );
    renderPanel();
    expect(await screen.findByText('Nie udało się wczytać zaleceń. Spróbuj ponownie.')).toBeInTheDocument();
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0);
  });

  it('renders a ROOM advisory recommendation with no target Surface guessed (V)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [
        recommendation({
          id: 'rec-room',
          target_kind: 'ROOM',
          surface_id: null,
        }),
      ],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText('Informacja ogólna (pomieszczenie)')).toBeInTheDocument();
    expect(
      screen.getByText('To zalecenie dotyczy całego pomieszczenia i ma charakter informacyjny.'),
    ).toBeInTheDocument();
  });

  it('never offers an accept action anywhere in the 11D.1 panel (W)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [
        recommendation(),
        recommendation({
          id: 'rec-2',
          status: 'ACCEPTED',
          current_price_item: priceItem({ id: 'price-2', display_name: 'Malowanie ścian' }),
        }),
      ],
      total: 2,
    });
    renderPanel();
    await screen.findByText('Gładź gipsowa');
    await screen.findByText('Malowanie ścian');
    expect(screen.queryByText(/Dodaj do prac/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/accept/i)).not.toBeInTheDocument();
  });

  it('never mutates the SurfaceWorkPlan through this panel (X)', async () => {
    const putSpy = vi.spyOn(workPlansApi, 'putSurfaceWorkPlan');
    const applySpy = vi.spyOn(workPlansApi, 'applyWorkPlanToRoomWalls');
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Opcje/));
    fireEvent.click(screen.getByLabelText(/Odrzuć/));
    await waitFor(() =>
      expect(workRecommendationsApi.dismissWorkRecommendation).toHaveBeenCalled(),
    );
    expect(putSpy).not.toHaveBeenCalled();
    expect(applySpy).not.toHaveBeenCalled();
  });

  it('never mutates or regenerates the Estimate through this panel (Y)', async () => {
    const regenSpy = vi.spyOn(estimatesApi, 'regenerateEstimate');
    const previewSpy = vi.spyOn(estimatesApi, 'previewEstimateRegeneration');
    const generateSpy = vi.spyOn(estimatesApi, 'generateEstimate');
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText('Oceń zalecenia'));
    await waitFor(() =>
      expect(workRecommendationsApi.evaluateWorkRecommendations).toHaveBeenCalled(),
    );
    expect(regenSpy).not.toHaveBeenCalled();
    expect(previewSpy).not.toHaveBeenCalled();
    expect(generateSpy).not.toHaveBeenCalled();
  });

  it('uses ~44px touch targets and a single-column card list (Z, MOBILE)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    const evaluate = await screen.findByLabelText('Oceń zalecenia');
    expect(evaluate).toHaveClass('min-h-11');
    const list = screen.getByText('Gładź gipsowa').closest('ul');
    expect(list).not.toBeNull();
    expect(list).toHaveClass('flex-col');
  });
});
