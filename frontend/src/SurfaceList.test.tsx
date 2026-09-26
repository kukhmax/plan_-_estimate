import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as openingsApi from './api/openings';
import * as surfacesApi from './api/surfaces';
import * as workPlansApi from './api/workPlans';
import { SurfaceList } from './components/SurfaceList';
import { I18nProvider } from './hooks/useI18n';
import { OpeningType } from './types/opening';
import { SurfaceType } from './types/surface';
import { surfaceCardTint } from './utils/surfaceColorTint';

vi.mock('./api/surfaces', () => ({
  fetchSurfaces: vi.fn(),
  createSurface: vi.fn(),
  updateSurface: vi.fn(),
  archiveSurface: vi.fn(),
  restoreSurface: vi.fn(),
  generateWalls: vi.fn(),
}));
vi.mock('./api/openings', () => ({
  fetchOpenings: vi.fn(),
  createOpening: vi.fn(),
  updateOpening: vi.fn(),
  archiveOpening: vi.fn(),
  restoreOpening: vi.fn(),
}));
vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return {
    ...actual,
    fetchSurfaceWorkPlan: vi.fn(),
    putSurfaceWorkPlan: vi.fn(),
    applyWorkPlanToRoomWalls: vi.fn(),
  };
});

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const surface: SurfaceType = {
  id: '33333333-3333-3333-3333-333333333333',
  room_id: roomId,
  name: 'Ściana północna',
  surface_type: 'WALL',
  description: 'Przy oknie',
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

function renderSurfaces(
  props: {
    roomHeight?: string | number | null;
    hasRoomDimensions?: boolean;
    wallMode?: 'RECTANGLE' | 'CUSTOM';
    onInspectSurface?: (surfaceId: string, surfaceName: string) => void;
  } = {},
) {
  return render(
    <I18nProvider>
      <SurfaceList
        projectId={projectId}
        roomId={roomId}
        roomHeight={props.roomHeight}
        hasRoomDimensions={props.hasRoomDimensions}
        wallMode={props.wallMode}
        onInspectSurface={props.onInspectSurface}
      />
    </I18nProvider>,
  );
}

/** Stage 10C.1: action grids live behind the per-card Opcje progressive disclosure. */
function expandOptions(surfaceId: string) {
  fireEvent.click(screen.getByLabelText(`options-toggle-${surfaceId}`));
}

beforeEach(() => {
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockImplementation(async (_project, _room, id) => ({
    id: `plan-${id}`,
    surface_id: id,
    substrate: 'CONCRETE',
    quality_target: 'S2',
    planned_works: [],
  }));
});

describe('SurfaceList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [surface], total: 1 });
  });

  it('renders surfaces with their semantic type', async () => {
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByText('Ściana')).toBeInTheDocument();
    expect(screen.getByText('Przy oknie')).toBeInTheDocument();
  });

  it('renders the section title with the theme-aware text color, not a hardcoded dark slate class (Stage 10H.1)', async () => {
    // Regression: a hardcoded `text-slate-900` on page-level (non-card) text
    // never adapts to Telegram's dark theme, where the page background is
    // itself dark — the heading became invisible dark-on-dark.
    renderSurfaces();
    const heading = await screen.findByText('Powierzchnie');
    expect(heading.className).toContain('text-[var(--tg-theme-text-color)]');
    expect(heading.className).not.toContain('text-slate-900');
  });

  it('does not show a redundant generic add-surface control or shape-mode selector in rectangle mode', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    expect(screen.queryByLabelText('add-surface')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('mode-custom')).not.toBeInTheDocument();
  });

  it('edits a surface through the surface form and calls updateSurface', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [surface], total: 1 });
    vi.mocked(surfacesApi.updateSurface).mockResolvedValue({ ...surface, name: 'Ściana nowa' });
    renderSurfaces();

    await waitFor(() =>
      expect(screen.getByLabelText(`options-toggle-${surface.id}`)).toBeInTheDocument(),
    );
    expandOptions(surface.id);
    fireEvent.click(screen.getByLabelText(`edit-surface-${surface.id}`));
    fireEvent.change(screen.getByLabelText('surface-name'), { target: { value: 'Ściana nowa' } });
    fireEvent.submit(screen.getByLabelText('surface-form'));

    await waitFor(() => {
      expect(surfacesApi.updateSurface).toHaveBeenCalledWith(
        projectId,
        roomId,
        surface.id,
        expect.objectContaining({ name: 'Ściana nowa', surface_type: 'WALL' }),
      );
    });
    expect(await screen.findByText('Powierzchnia została zaktualizowana')).toBeInTheDocument();
  });

  it('renders mobile wall action buttons with 44px touch targets in a compact grid', async () => {
    const wallWithDims: SurfaceType = {
      ...surface,
      width: 5,
      height: 2.7,
      gross_area: '13.500',
      deduction_area: '0.000',
      net_area: '13.500',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallWithDims], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(surface.id);
    expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`archive-surface-${surface.id}`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`add-opening-${surface.id}-DOOR`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`add-opening-${surface.id}-WINDOW`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`add-opening-${surface.id}-OTHER`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`toggle-openings-${surface.id}`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`options-toggle-${surface.id}`)).toHaveClass('min-h-11');
  });

  it('renders wall dimensions, gross area, deduction area, and net area', async () => {
    const wallWithDeduction: SurfaceType = {
      ...surface,
      width: 5,
      height: 2.7,
      gross_area: '13.500',
      deduction_area: '1.800',
      net_area: '11.700',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallWithDeduction], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByText(/5\.00 × 2\.70 m/)).toBeInTheDocument();
    expect(screen.getByText(/13\.50 m²/)).toBeInTheDocument();
    expect(screen.getByText(/1\.80 m²/)).toBeInTheDocument();
    expect(screen.getByText(/11\.70 m²/)).toBeInTheDocument();
    expandOptions(surface.id);
    expect(screen.getByLabelText(`toggle-openings-${surface.id}`)).toBeInTheDocument();
  });

  it('rounds a backend wall gross area of 13.515 m² to 13.52 m² on display (two-decimal policy)', async () => {
    const roundingWall: SurfaceType = {
      ...surface,
      width: 5.1,
      height: 2.65,
      gross_area: '13.515',
      deduction_area: '0.000',
      net_area: '13.515',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [roundingWall], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByText(/5\.10 × 2\.65 m/)).toBeInTheDocument();
    expect(screen.getAllByText(/13\.52 m²/)).toHaveLength(2); // gross & net
  });

  it('shows requires_dimensions notice when wall lacks dimensions', async () => {
    const wallNoDims: SurfaceType = {
      ...surface,
      width: null,
      height: null,
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallNoDims], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByText(/Wprowadź wymiary ściany, aby zarządzać otworami/)).toBeInTheDocument();
    expect(screen.queryByLabelText(`toggle-openings-${surface.id}`)).not.toBeInTheDocument();
  });

  it('restores an archived surface and reloads the list', async () => {
    const archived = { ...surface, is_archived: true };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [archived], total: 1 });
    vi.mocked(surfacesApi.restoreSurface).mockResolvedValue(surface);
    renderSurfaces();

    await waitFor(() => expect(screen.getByLabelText(`options-toggle-${surface.id}`)).toBeInTheDocument());
    expandOptions(surface.id);
    fireEvent.click(screen.getByLabelText(`restore-surface-${surface.id}`));

    await waitFor(() => {
      expect(surfacesApi.restoreSurface).toHaveBeenCalledWith(projectId, roomId, surface.id);
    });
    expect(await screen.findByText('Powierzchnia została przywrócona')).toBeInTheDocument();
    expect(surfacesApi.fetchSurfaces).toHaveBeenCalledTimes(2);
  });

  it('renders wall arithmetic hierarchy (gross - deduction = net) and inputMode="decimal"', async () => {
    const wallWithDeduction: SurfaceType = {
      ...surface,
      width: 5,
      height: 2.7,
      gross_area: '13.500',
      deduction_area: '1.800',
      net_area: '11.700',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallWithDeduction], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByText('−')).toBeInTheDocument();
    expect(screen.getByText('=')).toBeInTheDocument();

    // Verify form inputMode="decimal"
    expandOptions(surface.id);
    fireEvent.click(screen.getByLabelText(`edit-surface-${surface.id}`));
    expect(screen.getByLabelText('surface-width')).toHaveAttribute('inputMode', 'decimal');
    expect(screen.getByLabelText('surface-height')).toHaveAttribute('inputMode', 'decimal');
  });
});

describe('SurfaceList wall generation (Stage 5D.1A)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('generates exactly 4 canonical walls from room dimensions and reloads without duplication', async () => {
    const generated: SurfaceType[] = [0, 1, 2, 3].map((position, index) => ({
      ...surface,
      id: `44444444-4444-4444-4444-44444444444${index + 1}`,
      name: `Wall ${position + 1}`,
      position,
      width: position % 2 === 0 ? 5 : 4,
      height: 2.7,
      gross_area: position % 2 === 0 ? '13.500' : '10.800',
      deduction_area: '0.000',
      net_area: position % 2 === 0 ? '13.500' : '10.800',
    }));
    vi.mocked(surfacesApi.fetchSurfaces)
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({ items: generated, total: 4 });
    vi.mocked(surfacesApi.generateWalls).mockResolvedValue({ items: generated, total: 4 });
    renderSurfaces({ hasRoomDimensions: true });

    await waitFor(() => expect(screen.getByLabelText('generate-walls')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('generate-walls'));

    await waitFor(() => {
      expect(surfacesApi.generateWalls).toHaveBeenCalledWith(projectId, roomId);
    });
    expect(await screen.findByText('Ściana 4')).toBeInTheDocument();
    expect(screen.getByLabelText('surfaces-list').querySelectorAll('li')).toHaveLength(4);
    expect(screen.getByText('Wygenerowano 4 ściany')).toBeInTheDocument();
  });

  it('surfaces a 409 conflict message and leaves the list unchanged', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [surface], total: 1 });
    vi.mocked(surfacesApi.generateWalls).mockRejectedValue(
      new Error('Room already contains walls that do not match the 4-wall rectangle; no walls were changed'),
    );
    renderSurfaces({ hasRoomDimensions: true });

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('generate-walls'));

    await waitFor(() => {
      expect(screen.getByText(/Room already contains walls that do not match/)).toBeInTheDocument();
    });
    expect(screen.getByLabelText('surfaces-list').querySelectorAll('li')).toHaveLength(1);
  });

  it('adds a custom wall sequentially with localized name, next position, width, and room height', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.createSurface).mockResolvedValue({
      ...surface,
      name: 'Ściana 1',
      position: 0,
      width: 2.5,
      height: 2.7,
    });
    renderSurfaces({ roomHeight: 2.7, wallMode: 'CUSTOM' });

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    expect(screen.getByLabelText('custom-wall-entry')).toBeInTheDocument();
    expect(screen.getByText('Ściana 1')).toBeInTheDocument();
    expect(screen.queryByLabelText('mode-custom')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('custom-wall-width'), { target: { value: '2.5' } });
    fireEvent.submit(screen.getByLabelText('custom-wall-form'));

    await waitFor(() => {
      expect(surfacesApi.createSurface).toHaveBeenCalledWith(projectId, roomId, {
        name: 'Ściana 1',
        surface_type: 'WALL',
        position: 0,
        width: 2.5,
        height: 2.7,
        description: null,
      });
    });
  });

  it('does not persist the next empty wall row (no phantom request)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    renderSurfaces({ roomHeight: 2.7, wallMode: 'CUSTOM' });

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    expect(screen.getByLabelText('custom-wall-entry')).toBeInTheDocument();
    expect(screen.getByLabelText('add-custom-wall')).toBeInTheDocument();
    expect(surfacesApi.createSurface).not.toHaveBeenCalled();
  });

  it('defaults the custom wall height to the room height', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    renderSurfaces({ roomHeight: 2.7, wallMode: 'CUSTOM' });

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());

    expect(screen.getByLabelText('custom-wall-height')).toHaveValue('2.70 m');

    fireEvent.change(screen.getByLabelText('custom-wall-width'), { target: { value: '1.8' } });
    fireEvent.submit(screen.getByLabelText('custom-wall-form'));

    await waitFor(() => {
      expect(surfacesApi.createSurface).toHaveBeenCalledWith(
        projectId,
        roomId,
        expect.objectContaining({ width: 1.8, height: 2.7 }),
      );
    });
  });

  it('uses the overridden height when "different height" is enabled', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    renderSurfaces({ roomHeight: 2.7, wallMode: 'CUSTOM' });

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('custom-wall-different-height'));
    fireEvent.change(screen.getByLabelText('custom-wall-width'), { target: { value: '1.8' } });
    fireEvent.change(screen.getByLabelText('custom-wall-height'), { target: { value: '3.1' } });
    fireEvent.submit(screen.getByLabelText('custom-wall-form'));

    await waitFor(() => {
      expect(surfacesApi.createSurface).toHaveBeenCalledWith(
        projectId,
        roomId,
        expect.objectContaining({ width: 1.8, height: 3.1 }),
      );
    });
  });

  it('opens the opening form preselected with the quick action type on a measured wall', async () => {
    const wallWithDims: SurfaceType = {
      ...surface,
      width: 5,
      height: 2.7,
      gross_area: '13.500',
      deduction_area: '0.000',
      net_area: '13.500',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallWithDims], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(surface.id);
    fireEvent.click(screen.getByLabelText(`add-opening-${surface.id}-DOOR`));

    expect(await screen.findByLabelText(`opening-form-${surface.id}`)).toBeInTheDocument();
    expect(screen.getByLabelText('opening-type')).toHaveValue('DOOR');
  });

  it('does not duplicate walls in the UI when generate is repeated idempotently', async () => {
    const generated: SurfaceType[] = [0, 1, 2, 3].map((position, index) => ({
      ...surface,
      id: `44444444-4444-4444-4444-44444444444${index + 1}`,
      name: `Wall ${position + 1}`,
      position,
      width: position % 2 === 0 ? 5 : 4,
      height: 2.7,
      gross_area: position % 2 === 0 ? '13.500' : '10.800',
      deduction_area: '0.000',
      net_area: position % 2 === 0 ? '13.500' : '10.800',
    }));
    const listResponse = { items: generated, total: 4 };
    vi.mocked(surfacesApi.fetchSurfaces)
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValue(listResponse);
    vi.mocked(surfacesApi.generateWalls).mockResolvedValue(listResponse);
    renderSurfaces({ hasRoomDimensions: true });

    await waitFor(() => expect(screen.getByLabelText('generate-walls')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('generate-walls'));
    await waitFor(() => expect(screen.getByText('Ściana 4')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('generate-walls'));
    await waitFor(() => expect(surfacesApi.generateWalls).toHaveBeenCalledTimes(2));

    expect(screen.getByLabelText('surfaces-list').querySelectorAll('li')).toHaveLength(4);
    expect(screen.getAllByText('Ściana 1')).toHaveLength(1);
  });

  it('switches quick action type between Door and Window without duplicate forms', async () => {
    const wallWithDims: SurfaceType = {
      ...surface,
      width: 5,
      height: 2.7,
      gross_area: '13.500',
      deduction_area: '0.000',
      net_area: '13.500',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallWithDims], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(surface.id);

    fireEvent.click(screen.getByLabelText(`add-opening-${surface.id}-DOOR`));
    await screen.findByLabelText(`opening-form-${surface.id}`);
    expect(screen.getByLabelText('opening-type')).toHaveValue('DOOR');
    expect(screen.getAllByLabelText(`opening-form-${surface.id}`)).toHaveLength(1);

    fireEvent.click(screen.getByLabelText(`add-opening-${surface.id}-WINDOW`));
    const form = await screen.findByLabelText(`opening-form-${surface.id}`);
    expect(form).toBeInTheDocument();
    expect(screen.getByLabelText('opening-type')).toHaveValue('WINDOW');
    expect(screen.getAllByLabelText(`opening-form-${surface.id}`)).toHaveLength(1);
  });
});

describe('SurfaceList Stage 10C.1 compact card + Opcje progressive disclosure', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  const measuredWall = (): SurfaceType => ({
    ...surface,
    width: 5,
    height: 2.7,
    gross_area: '13.500',
    deduction_area: '1.800',
    net_area: '11.700',
  });

  it('collapses the wall action grid by default, showing only identity, area, Opcje, and Work Plan entry', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByLabelText(`options-toggle-${surface.id}`)).toBeInTheDocument();
    expect(screen.getByLabelText(`work-plan-${surface.id}`)).toBeInTheDocument();
    expect(screen.getByText('Otwory i opcje')).toBeInTheDocument();
    expect(screen.queryByLabelText(`edit-surface-${surface.id}`)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`add-opening-${surface.id}-DOOR`)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`toggle-openings-${surface.id}`)).not.toBeInTheDocument();
  });

  it('expands the wall action grid when tapping Opcje and relabels it Ukryj opcje', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(surface.id);

    // The top toggle and the bottom collapse action (Stage 10H.1) both show
    // the "Ukryj opcje" label while expanded.
    expect(screen.getAllByText('Ukryj otwory i opcje')).toHaveLength(2);
    expect(screen.getByLabelText(`options-toggle-${surface.id}`)).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toBeInTheDocument();
    expect(screen.getByLabelText(`archive-surface-${surface.id}`)).toBeInTheDocument();
    expect(screen.getByLabelText(`add-opening-${surface.id}-DOOR`)).toBeInTheDocument();
    expect(screen.getByLabelText(`add-opening-${surface.id}-WINDOW`)).toBeInTheDocument();
    expect(screen.getByLabelText(`add-opening-${surface.id}-OTHER`)).toBeInTheDocument();
    expect(screen.getByLabelText(`toggle-openings-${surface.id}`)).toBeInTheDocument();
  });

  it('renders a bottom "Ukryj opcje" collapse action so a long expanded openings panel never needs a scroll back to the top (Stage 10H.1)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());

    // Not present while collapsed.
    expect(screen.queryByLabelText(`options-toggle-bottom-${surface.id}`)).not.toBeInTheDocument();

    expandOptions(surface.id);

    const bottomToggle = screen.getByLabelText(`options-toggle-bottom-${surface.id}`);
    expect(bottomToggle).toBeInTheDocument();
    expect(bottomToggle).toHaveTextContent('Ukryj otwory i opcje');
    expect(bottomToggle.className).toContain('min-h-11');
    expect(bottomToggle.className).toContain('w-full');

    // Reuses the exact same toggle handler/state as the top action — no
    // separate collapse state is introduced.
    fireEvent.click(bottomToggle);
    expect(screen.getByLabelText(`options-toggle-${surface.id}`)).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText(`options-toggle-bottom-${surface.id}`)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`edit-surface-${surface.id}`)).not.toBeInTheDocument();
  });

  it('collapses the action grid again when tapping Ukryj opcje', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(surface.id);
    expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(`options-toggle-${surface.id}`));

    expect(screen.getByText('Otwory i opcje')).toBeInTheDocument();
    expect(screen.getByLabelText(`options-toggle-${surface.id}`)).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText(`edit-surface-${surface.id}`)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`add-opening-${surface.id}-DOOR`)).not.toBeInTheDocument();
  });

  it('keeps option expansion independent per card', async () => {
    const wall1 = measuredWall();
    const wall2: SurfaceType = {
      ...measuredWall(),
      id: '44444444-4444-4444-4444-444444444444',
      name: 'Ściana wschodnia',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wall1, wall2], total: 2 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(wall1.id);

    expect(screen.getByLabelText(`edit-surface-${wall1.id}`)).toBeInTheDocument();
    expect(screen.queryByLabelText(`edit-surface-${wall2.id}`)).not.toBeInTheDocument();
    expect(screen.getByLabelText(`options-toggle-${wall2.id}`)).toBeInTheDocument();
  });

  it('runs the wall inspection action from the expanded options', async () => {
    const onInspectSurface = vi.fn();
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    renderSurfaces({ onInspectSurface });

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(surface.id);
    fireEvent.click(screen.getByLabelText(`inspect-surface-${surface.id}`));

    expect(onInspectSurface).toHaveBeenCalledWith(surface.id, 'Ściana północna');
  });

  it('opens the pre-set door form from the expanded options (add door works)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(surface.id);
    fireEvent.click(screen.getByLabelText(`add-opening-${surface.id}-DOOR`));

    const form = await screen.findByLabelText(`opening-form-${surface.id}`);
    expect(form).toBeInTheDocument();
    expect(screen.getByLabelText('opening-type')).toHaveValue('DOOR');
  });

  it('manages openings from the expanded options and fetches the list', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(surface.id);
    fireEvent.click(screen.getByLabelText(`toggle-openings-${surface.id}`));

    await waitFor(() => {
      expect(openingsApi.fetchOpenings).toHaveBeenCalledWith(projectId, roomId, surface.id, false);
    });
    expect(await screen.findByLabelText(`no-openings-${surface.id}`)).toBeInTheDocument();
  });

  it('archives an active wall from the expanded options', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    vi.mocked(surfacesApi.archiveSurface).mockResolvedValue({ ...measuredWall(), is_archived: true });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expandOptions(surface.id);
    fireEvent.click(screen.getByLabelText(`archive-surface-${surface.id}`));

    await waitFor(() => {
      expect(surfacesApi.archiveSurface).toHaveBeenCalledWith(projectId, roomId, surface.id);
    });
    expect(await screen.findByText('Powierzchnia została zarchiwizowana')).toBeInTheDocument();
  });

  it('does not render a canonical FLOOR card in the generic surface list (10C.1C)', async () => {
    const floor: SurfaceType = {
      ...surface,
      name: 'Podłoga w łazience',
      surface_type: 'FLOOR',
      width: 4,
      height: 5,
      gross_area: '20.000',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [floor], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    expect(screen.queryByText('Podłoga w łazience')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('surfaces-list')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`options-toggle-${floor.id}`)).not.toBeInTheDocument();
  });

  it('does not render a canonical CEILING card in the generic surface list (10C.1C)', async () => {
    const ceiling: SurfaceType = {
      ...surface,
      name: 'Sufit w salonie',
      surface_type: 'CEILING',
      width: 4,
      height: 5,
      gross_area: '20.000',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [ceiling], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    expect(screen.queryByText('Sufit w salonie')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('surfaces-list')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`options-toggle-${ceiling.id}`)).not.toBeInTheDocument();
  });

  it('shows the Work Plan entry button (Rodzaje prac i jakość) on the collapsed card', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByLabelText(`work-plan-${surface.id}`)).toBeInTheDocument();
    expect(screen.getByText('Rodzaje prac i jakość')).toBeInTheDocument();
    expect(screen.getByLabelText(`work-plan-${surface.id}`)).toHaveClass('min-h-11');
  });

  it('opens and closes the exact wall WorkPlan independently from Opcje', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    renderSurfaces();

    const workPlan = await screen.findByLabelText(`work-plan-${surface.id}`);
    const options = screen.getByLabelText(`options-toggle-${surface.id}`);
    expect(workPlan).toHaveAttribute('aria-expanded', 'false');
    expect(options).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(workPlan);
    expect(await screen.findByLabelText(`work-plan-editor-${surface.id}`)).toBeInTheDocument();
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledWith(projectId, roomId, surface.id);
    expect(options).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText(`edit-surface-${surface.id}`)).not.toBeInTheDocument();

    fireEvent.click(workPlan);
    expect(screen.queryByLabelText(`work-plan-editor-${surface.id}`)).not.toBeInTheDocument();

    fireEvent.click(workPlan);
    await screen.findByLabelText(`work-plan-form-${surface.id}`);
    expandOptions(surface.id);
    expect(screen.getByLabelText(`work-plan-editor-${surface.id}`)).toBeInTheDocument();
    expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(`close-work-plan-${surface.id}`));
    expect(screen.queryByLabelText(`work-plan-editor-${surface.id}`)).not.toBeInTheDocument();
    expect(options).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toBeInTheDocument();
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
  });

  it('localizes the disclosure controls in Russian (O)', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByLabelText(`options-toggle-${surface.id}`)).toBeInTheDocument());
    expect(screen.getByText('Проёмы и опции')).toBeInTheDocument();
    expect(screen.getByText('Виды работ и качество')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(`options-toggle-${surface.id}`));
    expect(screen.getAllByText('Скрыть проёмы и опции')).toHaveLength(2);
    expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toBeInTheDocument();
  });

  it('shows generated wall names in Polish while keeping the stored name in the edit form', async () => {
    const generatedWall = { ...measuredWall(), name: 'Wall 1' };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [generatedWall], total: 1 });
    renderSurfaces();

    expect(await screen.findByText('Ściana 1')).toBeInTheDocument();
    expect(screen.queryByText('Wall 1')).not.toBeInTheDocument();

    expandOptions(generatedWall.id);
    fireEvent.click(screen.getByLabelText(`edit-surface-${generatedWall.id}`));
    expect(screen.getByLabelText('surface-name')).toHaveValue('Wall 1');
    expect(surfacesApi.updateSurface).not.toHaveBeenCalled();
  });

  it('uses localized Russian generated names in cards and the exact wall WorkPlan', async () => {
    localStorage.setItem('locale', 'ru');
    const wall1 = { ...measuredWall(), name: 'Wall 1' };
    const wall2 = {
      ...measuredWall(),
      id: '44444444-4444-4444-4444-444444444444',
      name: 'Wall 2',
      position: 1,
    };
    const custom = {
      ...measuredWall(),
      id: '55555555-5555-5555-5555-555555555555',
      name: 'Ściana łukowa',
      position: 2,
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({
      items: [wall1, wall2, custom],
      total: 3,
    });
    renderSurfaces();

    expect(await screen.findByText('Стена 1')).toBeInTheDocument();
    expect(screen.getByText('Стена 2')).toBeInTheDocument();
    expect(screen.getByText('Ściana łukowa')).toBeInTheDocument();
    expect(screen.queryByText('Wall 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Wall 2')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(`work-plan-${wall1.id}`));
    const editor = await screen.findByLabelText(`work-plan-editor-${wall1.id}`);
    expect(editor).toHaveTextContent('Виды работ и качество');
    expect(editor).toHaveTextContent('Стена 1');
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledWith(projectId, roomId, wall1.id);
  });
});

describe('SurfaceList canonical plane filtering (10C.1C finding 3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  /** Canonical FLOOR/CEILING Surface rows — provisioned once per room by 10C.1A. */
  const canonicalFloor = (): SurfaceType => ({
    ...surface,
    id: 'f1111111-1111-1111-1111-111111111111',
    name: 'Floor',
    surface_type: 'FLOOR',
    position: 100,
  });
  const canonicalCeiling = (): SurfaceType => ({
    ...surface,
    id: 'c1111111-1111-1111-1111-111111111111',
    name: 'Ceiling',
    surface_type: 'CEILING',
    position: 101,
  });
  const measuredWall = (): SurfaceType => ({
    ...surface,
    width: 5,
    height: 2.7,
    gross_area: '13.500',
    deduction_area: '1.800',
    net_area: '11.700',
  });

  it('A: canonical FLOOR/CEILING rows stay in the fetched data but appear nowhere as generic cards (no duplicates)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({
      items: [canonicalFloor(), canonicalCeiling(), measuredWall()],
      total: 3,
    });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    // Exactly one generic card: the wall. Canonical planes are rendered solely by AreaSegmentList.
    expect(screen.getByLabelText('surfaces-list').querySelectorAll('li')).toHaveLength(1);
    expect(screen.queryByText('Floor')).not.toBeInTheDocument();
    expect(screen.queryByText('Ceiling')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`options-toggle-${canonicalFloor().id}`)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`options-toggle-${canonicalCeiling().id}`)).not.toBeInTheDocument();
  });

  it('B: room with only canonical planes shows the wall empty state, not orphan cards', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({
      items: [canonicalFloor(), canonicalCeiling()],
      total: 2,
    });
    renderSurfaces();

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    expect(screen.queryByLabelText('surfaces-list')).not.toBeInTheDocument();
    expect(screen.queryByText('Floor')).not.toBeInTheDocument();
    expect(screen.queryByText('Ceiling')).not.toBeInTheDocument();
  });

  it('C: wall cards are unchanged when canonical planes coexist with walls', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({
      items: [canonicalFloor(), canonicalCeiling(), measuredWall()],
      total: 3,
    });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByText(/5\.00 × 2\.70 m/)).toBeInTheDocument();
    expect(screen.getByText(/11\.70 m²/)).toBeInTheDocument();
    expandOptions(surface.id);
    expect(screen.getByLabelText(`add-opening-${surface.id}-DOOR`)).toBeInTheDocument();
    expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toBeInTheDocument();
    expect(screen.getByLabelText(`archive-surface-${surface.id}`)).toBeInTheDocument();
  });

  it('D: surface count derivation still sees canonical rows under the hood when position numbering', async () => {
    // nextWallPosition derives from ALL surfaces (incl. canonical FLOOR/CEILING
    // position 100/101); a new wall must simply not break — regression guard only.
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({
      items: [canonicalFloor(), canonicalCeiling()],
      total: 2,
    });
    renderSurfaces({ roomHeight: 2.7, wallMode: 'CUSTOM' });

    await waitFor(() => expect(screen.getByLabelText('custom-wall-entry')).toBeInTheDocument());
    expect(screen.getByText('Ściana 1')).toBeInTheDocument();
    expect(screen.queryAllByLabelText(/^surface-item-/)).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Stage 10G.4 — deterministic surface-type card tints (mobile navigation)
// ---------------------------------------------------------------------------

describe('SurfaceList — surface type card tints (Stage 10G.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders each WALL card with the tint the shared deterministic per-id helper computes', async () => {
    const wallA: SurfaceType = { ...surface, id: 'wall-a', name: 'Ściana A' };
    const wallB: SurfaceType = { ...surface, id: 'wall-b', name: 'Ściana B' };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallA, wallB], total: 2 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana A')).toBeInTheDocument());
    const cardA = screen.getByLabelText('surface-item-wall-a');
    const cardB = screen.getByLabelText('surface-item-wall-b');
    const tintA = surfaceCardTint('wall-a');
    const tintB = surfaceCardTint('wall-b');
    expect(cardA.className).toContain(tintA.bg);
    expect(cardA.className).toContain(tintA.border);
    expect(cardB.className).toContain(tintB.bg);
    expect(cardB.className).toContain(tintB.border);
  });

  it('two different surface IDs can receive different palette tints, independent of array order', async () => {
    const idOne = 'wall-a';
    const idTwo = 'wall-b';
    const tintOne = surfaceCardTint(idOne);
    const tintTwo = surfaceCardTint(idTwo);
    // Self-check: these two fixture ids must actually hash to different tints,
    // otherwise this test would pass for the wrong reason.
    expect(tintOne.bg).not.toBe(tintTwo.bg);

    // Reversed array order vs. the id order itself — tint must depend only on id.
    const wallReversedFirst: SurfaceType = { ...surface, id: idTwo, name: 'Ściana Two' };
    const wallReversedSecond: SurfaceType = { ...surface, id: idOne, name: 'Ściana One' };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({
      items: [wallReversedFirst, wallReversedSecond],
      total: 2,
    });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana Two')).toBeInTheDocument());
    expect(screen.getByLabelText(`surface-item-${idOne}`).className).toContain(tintOne.bg);
    expect(screen.getByLabelText(`surface-item-${idTwo}`).className).toContain(tintTwo.bg);
  });

  it('the same surface_id always maps to the same tint result', () => {
    const first = surfaceCardTint(surface.id);
    const second = surfaceCardTint(surface.id);
    expect(second).toEqual(first);
  });

  it('preserves existing card actions (Opcje, Rodzaje prac i jakość, archive) alongside the tint', async () => {
    const wall: SurfaceType = { ...surface, width: 5, height: 2.7, gross_area: '13.500' };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wall], total: 1 });
    renderSurfaces();

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    const tint = surfaceCardTint(wall.id);
    const card = screen.getByLabelText(`surface-item-${wall.id}`);
    expect(card.className).toContain(tint.bg);
    expect(screen.getByLabelText(`options-toggle-${wall.id}`)).toBeInTheDocument();
    expect(screen.getByLabelText(`work-plan-${wall.id}`)).toBeInTheDocument();
    expect(screen.getByText('Rodzaje prac i jakość')).toBeInTheDocument();
  });

  it('remains readable and horizontally unconstrained at 320px (no fixed width forcing overflow)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [surface], total: 1 });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    const card = screen.getByLabelText(`surface-item-${surface.id}`);
    expect(card.className).not.toMatch(/\bw-\[\d/);
  });
});

// ---------------------------------------------------------------------------
// Stage 10G.4 follow-up — Opcje placement, deduction context, reveal row, units
// ---------------------------------------------------------------------------

function makeOpening(overrides: Partial<OpeningType> = {}): OpeningType {
  return {
    id: 'opening-1',
    surface_id: surface.id,
    opening_type: 'WINDOW',
    name: null,
    width: '1.200',
    height: '1.400',
    quantity: 1,
    single_area: '1.680',
    total_area: '1.680',
    description: null,
    reveal_enabled: false,
    reveal_depth: null,
    reveal_left: true,
    reveal_right: true,
    reveal_top: true,
    reveal_bottom: false,
    reveal_single_length: null,
    reveal_single_area: null,
    reveal_total_length: null,
    reveal_total_area: null,
    is_archived: false,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

const measuredWallWithDeduction = (): SurfaceType => ({
  ...surface,
  width: 5,
  height: 2.7,
  gross_area: '13.500',
  deduction_area: '1.680',
  net_area: '11.820',
});

describe('SurfaceList — compact upper-right Opcje (Stage 10G.4 follow-up)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
  });

  it('renders Opcje in the surface header, and it still opens/closes the existing options grid', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());

    const header = screen.getByText('Ściana północna').closest('div')!;
    const opcjeButton = screen.getByLabelText(`options-toggle-${surface.id}`);
    expect(header.parentElement).toContainElement(opcjeButton);
    expect(opcjeButton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText(`edit-surface-${surface.id}`)).not.toBeInTheDocument();

    fireEvent.click(opcjeButton);
    expect(opcjeButton).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toBeInTheDocument();

    fireEvent.click(opcjeButton);
    expect(opcjeButton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText(`edit-surface-${surface.id}`)).not.toBeInTheDocument();
  });

  it('meets the ~44px touch target as a compact button', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByLabelText(`options-toggle-${surface.id}`).className).toContain('min-h-11');
  });

  it('no duplicate full-width Opcje button remains on the card', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getAllByLabelText(`options-toggle-${surface.id}`)).toHaveLength(1);
  });

  it('a long surface name wraps instead of colliding with the Opcje button', async () => {
    const longNamed: SurfaceType = {
      ...measuredWallWithDeduction(),
      name: 'Bardzo długa nazwa ściany opisująca cały zakres pomieszczenia od podłogi do sufitu',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [longNamed], total: 1 });
    renderSurfaces();
    const nameEl = await screen.findByText(/Bardzo długa nazwa ściany/);
    expect(nameEl.className).toContain('break-words');
    expect(screen.getByLabelText(`options-toggle-${longNamed.id}`)).toBeInTheDocument();
  });
});

describe('SurfaceList — deduction context row (Stage 10G.4 follow-up)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('describes a single WINDOW deduction with its dimensions, localized', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [makeOpening({ opening_type: 'WINDOW', width: '1.200', height: '1.400' })],
      total: 1,
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    const row = await screen.findByText(/okno 1[,.]20/);
    expect(row.textContent).toContain('okno');
    expect(row.textContent).toContain('1.40');
    // The authoritative numeric deduction value is untouched by the context text.
    expect(screen.getByText('1.68 m²')).toBeInTheDocument();
  });

  it('describes a single DOOR deduction with its dimensions, localized', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [makeOpening({ opening_type: 'DOOR', width: '0.900', height: '2.000' })],
      total: 1,
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    const row = await screen.findByText(/drzwi 0[,.]90/);
    expect(row.textContent).toContain('drzwi');
  });

  it('uses a compact "N × type" summary for multiple openings of the same type', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [
        makeOpening({ id: 'o1', opening_type: 'WINDOW' }),
        makeOpening({ id: 'o2', opening_type: 'WINDOW' }),
      ],
      total: 2,
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(await screen.findByText(/2 × okno/)).toBeInTheDocument();
  });

  it('uses a compact "type + type" summary for a mix of opening types', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [
        makeOpening({ id: 'o1', opening_type: 'WINDOW' }),
        makeOpening({ id: 'o2', opening_type: 'DOOR' }),
      ],
      total: 2,
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(await screen.findByText(/okno \+ drzwi/)).toBeInTheDocument();
  });

  it('the numeric deduction amount always remains the authoritative backend value, unaffected by context', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [makeOpening({ opening_type: 'WINDOW' })],
      total: 1,
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    await screen.findByText(/okno/);
    expect(screen.getByText('1.68 m²')).toBeInTheDocument();
  });

  it('shows the plain deduction label with no invented context before openings have loaded / when there are none', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    await waitFor(() => expect(openingsApi.fetchOpenings).toHaveBeenCalled());
    expect(screen.getByText('Odliczenia')).toBeInTheDocument();
  });
});

describe('SurfaceList — Ościeża reveal row (Stage 10G.4 follow-up)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders the existing backend-authoritative reveal total length + area, localized as "mb"', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [
        makeOpening({
          id: 'o1', opening_type: 'WINDOW', reveal_enabled: true,
          reveal_total_length: '4.300', reveal_total_area: '0.860',
        }),
        makeOpening({
          id: 'o2', opening_type: 'DOOR', reveal_enabled: true,
          reveal_total_length: '3.100', reveal_total_area: '0.620',
        }),
      ],
      total: 2,
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());

    const row = await screen.findByText('Ościeża');
    const rowContent = row.closest('div')!.parentElement!.textContent ?? '';
    // 4.300 + 3.100 = 7.400 mb ; 0.860 + 0.620 = 1.480 m² — exact decimal-string sums, no float math.
    expect(rowContent).toContain('7.40');
    expect(rowContent).toContain('mb');
    expect(rowContent).toContain('1.48');
    expect(rowContent).toContain('m²');
    expect(rowContent).not.toMatch(/\bLM\b/);
  });

  it('hides the Ościeża row entirely when no opening has reveal enabled (least-noisy presentation)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [makeOpening({ opening_type: 'WINDOW', reveal_enabled: false })],
      total: 1,
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    await waitFor(() => expect(openingsApi.fetchOpenings).toHaveBeenCalled());
    expect(screen.queryByText('Ościeża')).not.toBeInTheDocument();
  });

  it('never recalculates reveal geometry — uses the opening totals verbatim, not width/height/depth', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [makeOpening({
        opening_type: 'WINDOW', width: '1.200', height: '1.400', reveal_depth: '0.250',
        reveal_enabled: true, reveal_total_length: '4.300', reveal_total_area: '1.290',
      })],
      total: 1,
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    const row = await screen.findByText('Ościeża');
    const rowContent = row.closest('div')!.parentElement!.textContent ?? '';
    // Exactly the backend reveal_total_length/area — never re-derived from width/height/depth.
    expect(rowContent).toContain('4.30');
    expect(rowContent).toContain('1.29');
  });
});

describe('SurfaceList — regression: existing behavior remains untouched', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
  });

  it('Surface Work Plan toggle still works', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue({
      id: 'plan-1', surface_id: surface.id, substrate: 'CONCRETE', quality_target: 'S2', planned_works: [],
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`work-plan-${surface.id}`));
    expect(screen.getByLabelText(`work-plan-${surface.id}`)).toHaveAttribute('aria-expanded', 'true');
    await waitFor(() => expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalled());
  });

  it('Opening UI (toggle-openings) still works after Opcje is expanded', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`options-toggle-${surface.id}`));
    fireEvent.click(screen.getByLabelText(`toggle-openings-${surface.id}`));
    await waitFor(() => {
      expect(openingsApi.fetchOpenings).toHaveBeenCalledWith(projectId, roomId, surface.id, false);
    });
  });
});

// ---------------------------------------------------------------------------
// Stage 13E.5B walkthrough — compact opening summary + "Otwory i opcje" label
// ---------------------------------------------------------------------------

describe('SurfaceList — opening summary on the wall card (13E.5B)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  const mixed = () => [
    makeOpening({ id: 'd', opening_type: 'DOOR', width: '0.900', height: '2.070', quantity: 2 }),
    makeOpening({ id: 'w1', opening_type: 'WINDOW', width: '0.600', height: '1.400' }),
    makeOpening({ id: 'w2', opening_type: 'WINDOW', width: '2.100', height: '1.400' }),
    makeOpening({ id: 'x', opening_type: 'WINDOW', width: '9.990', height: '9.990', is_archived: true }),
  ];

  it('groups active openings by type and size, sums quantity and omits archived ones (PL)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: mixed(), total: 4 });
    renderSurfaces();
    const summary = await screen.findByLabelText(`openings-summary-${surface.id}`);
    const rows = within(summary).getAllByRole('listitem').map((li) => li.textContent);
    expect(summary).toHaveTextContent('Otwory:');
    expect(rows).toEqual(['Drzwi 0,90 × 2,07 m (2)', 'Okno 0,60 × 1,40 m (1)', 'Okno 2,10 × 1,40 m (1)']);
    expect(summary).not.toHaveTextContent('9,99');
    // Existing area figures are untouched by the summary.
    expect(screen.getByText('1.68 m²')).toBeInTheDocument();
  });

  it('localizes the summary in Russian, including OTHER', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [...mixed(), makeOpening({ id: 'o', opening_type: 'OTHER', width: '0.300', height: '0.300' })], total: 5,
    });
    renderSurfaces();
    const summary = await screen.findByLabelText(`openings-summary-${surface.id}`);
    expect(summary).toHaveTextContent('Проёмы:');
    const rows = within(summary).getAllByRole('listitem').map((li) => li.textContent);
    expect(rows).toEqual([
      'Дверь 0,90 × 2,07 м (2)', 'Окно 0,60 × 1,40 м (1)', 'Окно 2,10 × 1,40 м (1)', 'Другой проем 0,30 × 0,30 м (1)',
    ]);
  });

  it('is absent without active openings', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWallWithDeduction()], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [makeOpening({ opening_type: 'WINDOW', is_archived: true })], total: 1,
    });
    renderSurfaces();
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    await waitFor(() => expect(openingsApi.fetchOpenings).toHaveBeenCalled());
    expect(screen.queryByLabelText(`openings-summary-${surface.id}`)).not.toBeInTheDocument();
  });
});
