import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as workRecommendationsApi from '../api/workRecommendations';
import * as workPlansApi from '../api/workPlans';
import * as estimatesApi from '../api/estimates';
import * as priceItemsApi from '../api/priceItems';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { WorkRecommendationRead } from '../types/workRecommendation';
import { SurfacePriceItemSummaryRead } from '../types/workPlan';
import { PriceItem } from '../types/priceItem';
import { RecommendationPanel } from './RecommendationPanel';

vi.mock('../api/workRecommendations', () => ({
  fetchWorkRecommendations: vi.fn(),
  evaluateWorkRecommendations: vi.fn(),
  dismissWorkRecommendation: vi.fn(),
  reconsiderWorkRecommendation: vi.fn(),
  acceptWorkRecommendation: vi.fn(),
}));

vi.mock('../api/priceItems', () => ({
  fetchPriceItems: vi.fn(),
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

function fullPriceItem(overrides: Partial<PriceItem> = {}): PriceItem {
  return {
    id: 'manual-1',
    code: 'PAINT_M2',
    name_key: null,
    display_name: 'Malowanie ścian',
    category: 'PAINTING',
    unit: 'M2',
    price: '18.00',
    currency: 'PLN',
    price_scope: 'LABOR',
    quality_level: null,
    is_archived: false,
    created_at: '2026-09-20T08:00:00Z',
    updated_at: '2026-09-20T08:00:00Z',
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
    vi.mocked(workRecommendationsApi.acceptWorkRecommendation).mockResolvedValue(
      recommendation({
        status: 'ACCEPTED',
        accepted_at: '2026-09-20T09:00:00Z',
        resolved_price_item_id: 'price-1',
      }),
    );
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [fullPriceItem()],
      total: 1,
    });
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
      await screen.findByText('Ta operacja nie jest teraz możliwa. Odśwież listę zaleceń.'),
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

  it('shows the accept action on a PENDING card but never on an ACCEPTED one, side by side (superseded by 11D.2)', async () => {
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
    expect(screen.getByLabelText(/Gładź gipsowa — Dodaj do prac/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Malowanie ścian — Dodaj do prac/)).not.toBeInTheDocument();
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

describe('RecommendationPanel zero-result UX (Stage 11B.1.1)', () => {
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
  });

  it('shows the untouched "Brak zaleceń" text before any evaluation', async () => {
    renderPanel();
    expect(await screen.findByText('Brak zaleceń.')).toBeInTheDocument();
    expect(workRecommendationsApi.evaluateWorkRecommendations).not.toHaveBeenCalled();
  });

  it('shows a distinct "no recommendations found" text after an explicit evaluate returns zero', async () => {
    renderPanel();
    await screen.findByText('Brak zaleceń.');
    fireEvent.click(screen.getByLabelText('Oceń zalecenia'));
    await waitFor(() =>
      expect(workRecommendationsApi.evaluateWorkRecommendations).toHaveBeenCalled(),
    );
    expect(
      await screen.findByText('Nie znaleziono zaleceń dla zakończonych badań.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Brak zaleceń.')).not.toBeInTheDocument();
  });

  it('shows the error state, not the successful-zero state, when evaluate fails', async () => {
    vi.mocked(workRecommendationsApi.evaluateWorkRecommendations).mockRejectedValue(
      new Error('network down'),
    );
    renderPanel();
    await screen.findByText('Brak zaleceń.');
    fireEvent.click(screen.getByLabelText('Oceń zalecenia'));
    await screen.findByRole('alert');
    expect(
      screen.queryByText('Nie znaleziono zaleceń dla zakończonych badań.'),
    ).not.toBeInTheDocument();
    // The untouched-state text is still shown underneath the error banner,
    // never the "evaluated successfully" zero-result text.
    expect(screen.getByText('Brak zaleceń.')).toBeInTheDocument();
  });

  it('replaces the zero-result message with cards once a later evaluate finds recommendations', async () => {
    renderPanel();
    fireEvent.click(await screen.findByLabelText('Oceń zalecenia'));
    await screen.findByText('Nie znaleziono zaleceń dla zakończonych badań.');

    vi.mocked(workRecommendationsApi.evaluateWorkRecommendations).mockResolvedValue({
      created: 1,
      reactivated: 0,
      unchanged: 0,
      resolved: 0,
      items: [recommendation()],
      total: 1,
    });
    fireEvent.click(screen.getByLabelText('Oceń zalecenia'));
    expect(await screen.findByText('Gładź gipsowa')).toBeInTheDocument();
    expect(
      screen.queryByText('Nie znaleziono zaleceń dla zakończonych badań.'),
    ).not.toBeInTheDocument();
  });
});

describe('RecommendationPanel acceptance (Stage 11D.2)', () => {
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
    vi.mocked(workRecommendationsApi.acceptWorkRecommendation).mockResolvedValue(
      recommendation({
        status: 'ACCEPTED',
        accepted_at: '2026-09-20T09:00:00Z',
        resolved_price_item_id: 'price-1',
      }),
    );
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [fullPriceItem()],
      total: 1,
    });
  });

  it('shows "Dodaj do prac" for an actionable PENDING recommendation with a normal PriceItem (A)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByLabelText(/Dodaj do prac/)).toBeInTheDocument();
  });

  it('accepts semantically, shows ACCEPTED, removes the accept action, and shows success feedback (B)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Dodaj do prac/));
    await waitFor(() =>
      expect(workRecommendationsApi.acceptWorkRecommendation).toHaveBeenCalledWith(
        'proj-1',
        'rec-1',
        {},
      ),
    );
    expect(await screen.findByText('Zaakceptowane')).toBeInTheDocument();
    expect(screen.queryByLabelText(/Dodaj do prac/)).not.toBeInTheDocument();
    expect(
      screen.getByText('Praca dodana do planu. Kosztorys nie został jeszcze zaktualizowany.'),
    ).toBeInTheDocument();
  });

  it('never mutates WorkPlan or Estimate as part of acceptance (C)', async () => {
    const putSpy = vi.spyOn(workPlansApi, 'putSurfaceWorkPlan');
    const applySpy = vi.spyOn(workPlansApi, 'applyWorkPlanToRoomWalls');
    const regenSpy = vi.spyOn(estimatesApi, 'regenerateEstimate');
    const previewSpy = vi.spyOn(estimatesApi, 'previewEstimateRegeneration');
    const generateSpy = vi.spyOn(estimatesApi, 'generateEstimate');
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Dodaj do prac/));
    await waitFor(() =>
      expect(workRecommendationsApi.acceptWorkRecommendation).toHaveBeenCalled(),
    );
    expect(putSpy).not.toHaveBeenCalled();
    expect(applySpy).not.toHaveBeenCalled();
    expect(regenSpy).not.toHaveBeenCalled();
    expect(previewSpy).not.toHaveBeenCalled();
    expect(generateSpy).not.toHaveBeenCalled();
  });

  it('keeps acceptance enabled for a NULL price (D)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: priceItem({ price: null }) })],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText(/Do ustalenia/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Dodaj do prac/)).not.toBeDisabled();
  });

  it('keeps acceptance enabled for an explicit zero price (E)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: priceItem({ price: '0.00' }) })],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText(/0,00 zł/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Dodaj do prac/)).not.toBeDisabled();
  });

  it('never shows accept or the fallback picker for a ROOM advisory recommendation (F)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ target_kind: 'ROOM', surface_id: null })],
      total: 1,
    });
    renderPanel();
    await screen.findByText('Informacja ogólna (pomieszczenie)');
    expect(screen.queryByLabelText(/Dodaj do prac/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Wybierz pozycję ręcznie/)).not.toBeInTheDocument();
  });

  it('hides normal accept and offers the fallback picker when no PriceItem currently resolves (G)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: null })],
      total: 1,
    });
    renderPanel();
    await screen.findByText('Brak pozycji cennika dla tej pracy.');
    expect(screen.queryByLabelText(/Dodaj do prac/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Wybierz pozycję ręcznie/)).toBeInTheDocument();
  });

  it('hides normal accept and offers the fallback picker for an archived PriceItem (H)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: priceItem({ is_archived: true }) })],
      total: 1,
    });
    renderPanel();
    await screen.findByText('Zarchiwizowana');
    expect(screen.queryByLabelText(/Dodaj do prac/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Wybierz pozycję ręcznie/)).toBeInTheDocument();
  });

  it('hides normal accept and offers the fallback picker for a REVEAL PriceItem (I)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: priceItem({ category: 'REVEAL' }) })],
      total: 1,
    });
    renderPanel();
    await screen.findByText('Gładź gipsowa');
    expect(screen.queryByLabelText(/Dodaj do prac/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Wybierz pozycję ręcznie/)).toBeInTheDocument();
  });

  it('excludes REVEAL items from the fallback picker (J)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [
        fullPriceItem({ id: 'reveal-1', display_name: 'Ościeże', category: 'REVEAL' }),
        fullPriceItem({ id: 'paint-1', display_name: 'Malowanie ścian', category: 'PAINTING' }),
      ],
      total: 2,
    });
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: null })],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Wybierz pozycję ręcznie/));
    await screen.findByText('Malowanie ścian');
    expect(screen.queryByText('Ościeże')).not.toBeInTheDocument();
  });

  it('permits a NULL-price item in the fallback picker (K)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [fullPriceItem({ price: null })],
      total: 1,
    });
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: null })],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Wybierz pozycję ręcznie/));
    expect(await screen.findByText(/Do ustalenia/)).toBeInTheDocument();
  });

  it('permits a zero-price item in the fallback picker (L)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
      items: [fullPriceItem({ price: '0.00' })],
      total: 1,
    });
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: null })],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Wybierz pozycję ręcznie/));
    expect(await screen.findByText(/0,00 zł/)).toBeInTheDocument();
  });

  it('submits the manually selected price_item_id through /accept and never calls WorkPlan PUT (M, N)', async () => {
    const putSpy = vi.spyOn(workPlansApi, 'putSurfaceWorkPlan');
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation({ current_price_item: null })],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Wybierz pozycję ręcznie/));
    fireEvent.click(await screen.findByLabelText(/Wybierz pozycję Malowanie ścian/));
    fireEvent.click(screen.getByLabelText('Potwierdź wybór'));
    await waitFor(() =>
      expect(workRecommendationsApi.acceptWorkRecommendation).toHaveBeenCalledWith(
        'proj-1',
        'rec-1',
        { price_item_id: 'manual-1' },
      ),
    );
    expect(putSpy).not.toHaveBeenCalled();
  });

  it('prevents a duplicate accept submit while a request is pending (O)', async () => {
    let resolveAccept: (value: WorkRecommendationRead) => void = () => undefined;
    vi.mocked(workRecommendationsApi.acceptWorkRecommendation).mockReturnValue(
      new Promise((resolve) => {
        resolveAccept = resolve;
      }),
    );
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    const acceptButton = await screen.findByLabelText(/Dodaj do prac/);
    fireEvent.click(acceptButton);
    expect(acceptButton).toBeDisabled();
    fireEvent.click(acceptButton);
    expect(workRecommendationsApi.acceptWorkRecommendation).toHaveBeenCalledTimes(1);
    resolveAccept(recommendation({ status: 'ACCEPTED' }));
    await waitFor(() => expect(acceptButton).not.toBeInTheDocument());
  });

  it('renders a localized message on a generic accept 404 (P)', async () => {
    vi.mocked(workRecommendationsApi.acceptWorkRecommendation).mockRejectedValue(
      new ApiError('Work recommendation not found', 404),
    );
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Dodaj do prac/));
    expect(
      await screen.findByText('Nie znaleziono badania do oceny zaleceń.'),
    ).toBeInTheDocument();
  });

  it('renders distinguishable setup guidance when the target Surface has no WorkPlan (Q)', async () => {
    vi.mocked(workRecommendationsApi.acceptWorkRecommendation).mockRejectedValue(
      new ApiError('Target surface has no work plan yet', 404),
    );
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Dodaj do prac/));
    expect(
      await screen.findByText('Najpierw skonfiguruj „Rodzaje prac i jakość” dla tej powierzchni.'),
    ).toBeInTheDocument();
  });

  it('renders a localized conflict on accept 409 without retrying automatically (R)', async () => {
    vi.mocked(workRecommendationsApi.acceptWorkRecommendation).mockRejectedValue(
      new ApiError('Cannot accept a dismissed recommendation; reconsider it first', 409),
    );
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Dodaj do prac/));
    expect(
      await screen.findByText('Ta operacja nie jest teraz możliwa. Odśwież listę zaleceń.'),
    ).toBeInTheDocument();
    expect(workRecommendationsApi.acceptWorkRecommendation).toHaveBeenCalledTimes(1);
    // Prior lifecycle state is untouched by a failed accept -- no optimistic
    // update exists to roll back, and the recommendation is never patched on
    // error, so it must still read PENDING with the accept action available.
    expect(screen.getByText('Oczekujące')).toBeInTheDocument();
    expect(screen.getByLabelText(/Dodaj do prac/)).not.toBeDisabled();
  });

  it('renders a generic localized failure for a non-ApiError network failure, leaving the UI usable', async () => {
    vi.mocked(workRecommendationsApi.acceptWorkRecommendation).mockRejectedValue(
      new TypeError('Failed to fetch'),
    );
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    const acceptButton = await screen.findByLabelText(/Dodaj do prac/);
    fireEvent.click(acceptButton);
    expect(
      await screen.findByText('Nie udało się dodać pracy do planu. Spróbuj ponownie.'),
    ).toBeInTheDocument();
    expect(acceptButton).not.toBeDisabled();
    expect(screen.getByText('Oczekujące')).toBeInTheDocument();
  });

  it('renders localized validation feedback on accept 422 (S)', async () => {
    vi.mocked(workRecommendationsApi.acceptWorkRecommendation).mockRejectedValue(
      new ApiError('Price item is a REVEAL-category item', 422),
    );
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [recommendation()],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Dodaj do prac/));
    expect(
      await screen.findByText('Wybrana pozycja nie jest obsługiwana dla tego zalecenia.'),
    ).toBeInTheDocument();
  });

  it('never falsely labels a reloaded current_price_item as the historical accepted snapshot (T)', async () => {
    vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({
      items: [
        recommendation({
          status: 'ACCEPTED',
          accepted_at: '2026-09-19T09:00:00Z',
          resolved_price_item_id: 'manual-1',
          current_price_item: priceItem({ display_name: 'Aktualna pozycja z cennika' }),
        }),
      ],
      total: 1,
    });
    renderPanel();
    expect(await screen.findByText('Zaakceptowane')).toBeInTheDocument();
    expect(await screen.findByText('Aktualna pozycja z cennika')).toBeInTheDocument();
    // The success/staleness message is transient session feedback from this
    // panel's own accept action -- it must never appear merely from a reload.
    expect(
      screen.queryByText('Praca dodana do planu. Kosztorys nie został jeszcze zaktualizowany.'),
    ).not.toBeInTheDocument();
  });

  it('mount still does not evaluate and filter switching still does not evaluate (V, W)', async () => {
    renderPanel();
    await waitFor(() =>
      expect(workRecommendationsApi.fetchWorkRecommendations).toHaveBeenCalled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Rozwiązane' }));
    await waitFor(() =>
      expect(workRecommendationsApi.fetchWorkRecommendations).toHaveBeenCalledTimes(2),
    );
    expect(workRecommendationsApi.evaluateWorkRecommendations).not.toHaveBeenCalled();
  });
});
