import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api/http';
import * as openingsApi from './api/openings';
import * as surfacesApi from './api/surfaces';
import * as workPlansApi from './api/workPlans';
import { SurfaceList } from './components/SurfaceList';
import { I18nProvider } from './hooks/useI18n';
import { ProjectPhotosContext } from './hooks/ProjectPhotosContext';
import { EMPTY_PHOTO_COUNTS } from './hooks/usePhotoCounts';
import { OpeningType } from './types/opening';
import { SurfaceType } from './types/surface';
import { surfaceCardTint } from './utils/surfaceColorTint';
import { installAutoOpenAreaDetails } from './test/autoOpenWalls';

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
    dimensionsKey?: string;
    initiallyOpen?: boolean;
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
        dimensionsKey={props.dimensionsKey}
        initiallyOpen={props.initiallyOpen ?? true}
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

// the calculation of the area is folded behind a tap on the net area (usability U-7); the older tests about its figures see it open
let stopAutoOpenAreas: (() => void) | undefined;
beforeEach(() => {
  stopAutoOpenAreas = installAutoOpenAreaDetails();
});
afterEach(() => {
  stopAutoOpenAreas?.();
});

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
    const heading = await screen.findByText('Ściany'); // 13F-PRE FIX.2: wall-only section
    expect(heading.className).toContain('text-[var(--tg-theme-text-color)]');
    expect(heading.className).not.toContain('text-slate-900');
  });

  it('names the wall-only section "Стены" in Russian and keeps wall cards (13F-PRE FIX.2)', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [surface], total: 1 });
    renderSurfaces();
    expect(await screen.findByText('Стены')).toBeInTheDocument();
    expect(screen.queryByText('Поверхности')).not.toBeInTheDocument();
    expect(await screen.findByText('Ściana północna')).toBeInTheDocument();
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

  it('renders mobile wall action buttons with compact touch targets (40 px, owner request 18G) in a compact grid', async () => {
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

  it('re-reads the walls when the room size is corrected, and not when it is unchanged', async () => {
    const wall = (width: number, gross: string): SurfaceType => ({ ...surface, width, height: 2.68, gross_area: gross, deduction_area: '0.000', net_area: gross });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValueOnce({ items: [wall(4.08, '10.934')], total: 1 });
    const view = renderSurfaces({ dimensionsKey: '3.73|2.32|2.68' });
    await waitFor(() => expect(screen.getByText(/4\.08 × 2\.68 m/)).toBeInTheDocument());

    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wall(2.32, '6.218')], total: 1 });
    const again = (key: string) => (
      <I18nProvider>
        <SurfaceList projectId={projectId} roomId={roomId} dimensionsKey={key} initiallyOpen />
      </I18nProvider>
    );
    view.rerender(again('3.73|2.32|2.68'));
    expect(surfacesApi.fetchSurfaces).toHaveBeenCalledTimes(1);

    view.rerender(again('2.32|2.32|2.68'));
    await waitFor(() => expect(screen.getByText(/2\.32 × 2\.68 m/)).toBeInTheDocument());
    expect(screen.queryByText(/4\.08 × 2\.68 m/)).not.toBeInTheDocument();
    expect(surfacesApi.fetchSurfaces).toHaveBeenCalledTimes(2);
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
      .mockResolvedValueOnce({ items: [], total: 0 }) // active list
      .mockResolvedValueOnce({ items: [], total: 0 }) // archived-walls check: genuinely empty room
      .mockResolvedValue({ items: generated, total: 4 });
    vi.mocked(surfacesApi.generateWalls).mockResolvedValue({ items: generated, total: 4 });
    renderSurfaces({ hasRoomDimensions: true });

    await waitFor(() => expect(screen.getByLabelText('generate-walls')).toBeInTheDocument());
    expect(surfacesApi.fetchSurfaces).toHaveBeenLastCalledWith(projectId, roomId, true);
    fireEvent.click(screen.getByLabelText('generate-walls'));

    await waitFor(() => {
      expect(surfacesApi.generateWalls).toHaveBeenCalledWith(projectId, roomId);
    });
    expect(await screen.findByText('Ściana 4')).toBeInTheDocument();
    expect(screen.getByLabelText('surfaces-list').querySelectorAll('li')).toHaveLength(4);
    expect(screen.getByText('Wygenerowano 4 ściany')).toBeInTheDocument();
    // 13F-PRE: once walls exist the CTA disappears (no disabled button, no hint).
    expect(screen.queryByLabelText('generate-walls')).not.toBeInTheDocument();
    expect(screen.queryByText(/Tworzy 4 ściany na podstawie wymiarów/)).not.toBeInTheDocument();
    expect(surfacesApi.generateWalls).toHaveBeenCalledTimes(1);
  });

  it('hides the CTA when the room already has walls (no conflict invitation)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [surface], total: 1 });
    renderSurfaces({ hasRoomDimensions: true });

    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.queryByLabelText('generate-walls')).not.toBeInTheDocument();
    expect(surfacesApi.fetchSurfaces).toHaveBeenCalledTimes(1); // active walls known: no extra check
  });

  it('hides the CTA when only ARCHIVED walls exist, so no second set is invited', async () => {
    const archivedWall = { ...surface, is_archived: true };
    vi.mocked(surfacesApi.fetchSurfaces).mockImplementation(async (_p, _r, includeArchived) =>
      includeArchived ? { items: [archivedWall], total: 1 } : { items: [], total: 0 },
    );
    renderSurfaces({ hasRoomDimensions: true });

    await waitFor(() => expect(surfacesApi.fetchSurfaces).toHaveBeenCalledWith(projectId, roomId, true));
    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    expect(screen.queryByLabelText('generate-walls')).not.toBeInTheDocument();
    expect(surfacesApi.generateWalls).not.toHaveBeenCalled();
  });

  it('hides the CTA when the archived-walls check fails (fail-safe)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockImplementation(async (_p, _r, includeArchived) => {
      if (includeArchived) throw new Error('network');
      return { items: [], total: 0 };
    });
    renderSurfaces({ hasRoomDimensions: true });

    await waitFor(() => expect(surfacesApi.fetchSurfaces).toHaveBeenCalledWith(projectId, roomId, true));
    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    expect(screen.queryByLabelText('generate-walls')).not.toBeInTheDocument();
  });

  it('shows a 409 conflict message from the server and leaves the list unchanged', async () => {
    // e.g. walls were created in another session after this list was loaded
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.generateWalls).mockRejectedValue(
      new Error('Room already contains walls that do not match the 4-wall rectangle; no walls were changed'),
    );
    renderSurfaces({ hasRoomDimensions: true });

    await waitFor(() => expect(screen.getByLabelText('generate-walls')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('generate-walls'));

    await waitFor(() => {
      expect(screen.getByText(/Room already contains walls that do not match/)).toBeInTheDocument();
    });
    expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument();
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

    fireEvent.change(screen.getByLabelText('custom-wall-width'), { target: { value: '250' } });
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

    fireEvent.change(screen.getByLabelText('custom-wall-width'), { target: { value: '180' } });
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
    fireEvent.change(screen.getByLabelText('custom-wall-width'), { target: { value: '180' } });
    fireEvent.change(screen.getByLabelText('custom-wall-height'), { target: { value: '310' } });
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
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValue(listResponse);
    vi.mocked(surfacesApi.generateWalls).mockResolvedValue(listResponse);
    renderSurfaces({ hasRoomDimensions: true });

    await waitFor(() => expect(screen.getByLabelText('generate-walls')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('generate-walls'));
    await waitFor(() => expect(screen.getByText('Ściana 4')).toBeInTheDocument());

    // 13F-PRE: the CTA is gone after generation, so a second set cannot be requested.
    expect(screen.queryByLabelText('generate-walls')).not.toBeInTheDocument();
    expect(surfacesApi.generateWalls).toHaveBeenCalledTimes(1);

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

  it('is a compact 40 px button (owner request, Stage 18G)', async () => {
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

describe('Realizacja entry (Stage 13H.5)', () => {
  const measuredWall = (): SurfaceType => ({ ...surface, width: 5, height: 2.7, gross_area: '13.500', deduction_area: '0.000', net_area: '13.500' });

  it('opens the execution view separately from the plan editor; only one is open at a time', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue({
      id: 'plan-1', surface_id: surface.id, substrate: 'CONCRETE', quality_target: 'S2', template_applications: [],
      planned_works: [{
        id: 'row-1', work_plan_id: 'plan-1', price_item_id: 'p1', position: 0, occurrence_key: 'key-1', wait_after_hours: null,
        price_item: { id: 'p1', code: 'P1', name_key: null, display_name: 'Gładź', category: 'SKIM_COAT', unit: 'M2',
          price_scope: 'LABOR', price: null, currency: 'PLN', is_archived: false, quality_level: null },
        coefficient_options: [],
        execution: { status: 'IN_PROGRESS', started_at: '2026-09-27T08:00:00Z', completed_at: null, ready_after: null },
      }],
    });
    renderSurfaces();

    const execution = await screen.findByLabelText(`execution-${surface.id}`);
    expect(execution).toHaveTextContent('Realizacja');
    expect(execution).toHaveClass('min-h-11');
    fireEvent.click(execution);
    expect(await screen.findByLabelText(`execution-view-${surface.id}`)).toBeInTheDocument();
    expect(await screen.findByLabelText('execution-status-key-1')).toHaveTextContent('W trakcie');
    // a room with a single wall has no one to carry statuses to
    expect(screen.queryByLabelText(`execution-bulk-open-${surface.id}`)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`work-plan-editor-${surface.id}`)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(`work-plan-${surface.id}`));
    expect(await screen.findByLabelText(`work-plan-editor-${surface.id}`)).toBeInTheDocument();
    expect(screen.queryByLabelText(`execution-view-${surface.id}`)).not.toBeInTheDocument();
    // usability U-5: the plan shows no execution status; it is in the Realizacja segment only
    await screen.findByLabelText(/^draft-occurrence-/);
    expect(screen.queryByLabelText(/^occurrence-execution-/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('execution-complete-key-1')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(`execution-${surface.id}`));
    expect(await screen.findByLabelText(`execution-view-${surface.id}`)).toBeInTheDocument();
    expect(screen.queryByLabelText(`work-plan-editor-${surface.id}`)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(`close-execution-${surface.id}`));
    expect(screen.queryByLabelText(`execution-view-${surface.id}`)).not.toBeInTheDocument();
  });

  it('the empty state leads to the plan editor', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [measuredWall()], total: 1 });
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValue(new ApiError('Surface work plan not found', 404));
    renderSurfaces();
    fireEvent.click(await screen.findByLabelText(`execution-${surface.id}`));
    fireEvent.click(await screen.findByLabelText(`execution-open-plan-${surface.id}`));
    expect(await screen.findByLabelText(`work-plan-editor-${surface.id}`)).toBeInTheDocument();
    expect(screen.queryByLabelText(`execution-view-${surface.id}`)).not.toBeInTheDocument();
  });
});

describe('Realizacja row — execution photo badge (Stage 14H.5)', () => {
  const photosValue = (workSurfaces: Record<string, number>) => ({
    projectId,
    counts: { ...EMPTY_PHOTO_COUNTS, work_surfaces: workSurfaces },
    isExpanded: () => false,
    toggle: () => {},
    adjust: () => {},
    resolveLocation: () => '',
    ensureLocations: () => {},
  });
  const renderWithPhotos = (workSurfaces: Record<string, number>, inspectionSurfaces: Record<string, number> = {}) =>
    render(
      <I18nProvider>
        <ProjectPhotosContext.Provider
          value={{ ...photosValue(workSurfaces), counts: { ...EMPTY_PHOTO_COUNTS, work_surfaces: workSurfaces, inspection_surfaces: inspectionSurfaces } }}
        >
          <SurfaceList projectId={projectId} roomId={roomId} onInspectSurface={() => {}} initiallyOpen />
        </ProjectPhotosContext.Provider>
      </I18nProvider>,
    );

  it('a wall shows the number of its execution photos on the row', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [{ ...surface, width: 5, height: 2.7, gross_area: '13.500', net_area: '13.500' }], total: 1 });
    renderWithPhotos({ [surface.id]: 4 });
    const row = await screen.findByLabelText(`execution-${surface.id}`);
    expect(within(row).getByTestId('execution-photo-badge')).toHaveTextContent('4');
  });

  it('another kind of surface (OTHER) shows it on its row as well', async () => {
    const other: SurfaceType = { ...surface, id: '44444444-4444-4444-4444-444444444444', name: 'Kolumna', surface_type: 'OTHER' };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [other], total: 1 });
    renderWithPhotos({ [other.id]: 6, [surface.id]: 1 });
    const row = await screen.findByLabelText(`execution-${other.id}`);
    expect(within(row).getByTestId('execution-photo-badge')).toHaveTextContent('6');
  });

  it('no execution photos, no badge', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [surface], total: 1 });
    renderWithPhotos({});
    const row = await screen.findByLabelText(`execution-${surface.id}`);
    expect(within(row).queryByTestId('execution-photo-badge')).toBeNull();
  });

  it('the wall inspection button shows the number of its inspection photos, and the Realizacja row its own number', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [{ ...surface, width: 5, height: 2.7, gross_area: '13.500', net_area: '13.500' }], total: 1 });
    renderWithPhotos({ [surface.id]: 4 }, { [surface.id]: 7 });
    await screen.findByLabelText(`execution-${surface.id}`);
    fireEvent.click(screen.getByLabelText(`options-toggle-${surface.id}`));
    const inspect = await screen.findByLabelText(`inspect-surface-${surface.id}`);
    expect(within(inspect).getByTestId('inspection-photo-badge')).toHaveTextContent('7');
    expect(within(inspect).queryByTestId('execution-photo-badge')).toBeNull();
    expect(within(screen.getByLabelText(`execution-${surface.id}`)).getByTestId('execution-photo-badge')).toHaveTextContent('4');
    expect(inspect).toHaveClass('flex', 'flex-wrap', 'items-center', 'justify-center');
    expect(inspect).toHaveTextContent('Badanie ściany');
  });

  it('a wall without inspection photos shows no mark on its inspection button', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [surface], total: 1 });
    renderWithPhotos({}, { 'another-surface': 3 });
    await screen.findByLabelText(`execution-${surface.id}`);
    fireEvent.click(screen.getByLabelText(`options-toggle-${surface.id}`));
    const inspect = await screen.findByLabelText(`inspect-surface-${surface.id}`);
    expect(within(inspect).queryByTestId('inspection-photo-badge')).toBeNull();
  });
});


describe('Wall rows and cards (Stage 18G)', () => {
  const measured = (id: string, name: string, width: number, height: number, net: string): SurfaceType => ({
    ...surface, id, name, width, height, gross_area: net, deduction_area: '0.000', net_area: net,
  });
  const WALL_A = measured('aaaaaaaa-0000-0000-0000-000000000001', 'Ściana 1', 3.42, 2.52, '8.62');
  const WALL_B = measured('bbbbbbbb-0000-0000-0000-000000000002', 'Ściana 2', 2.78, 2.6, '7.23');

  const photosValue = (surfaces: Record<string, number>) => ({
    projectId,
    counts: { ...EMPTY_PHOTO_COUNTS, surfaces },
    isExpanded: () => false,
    toggle: () => {},
    adjust: () => {},
    resolveLocation: () => '',
    ensureLocations: () => {},
  });
  const renderRows = (props: { wallMode?: 'RECTANGLE' | 'CUSTOM'; onInspectSurface?: (id: string, name: string) => void } = {}) =>
    render(
      <I18nProvider>
        <ProjectPhotosContext.Provider value={photosValue({ [WALL_A.id]: 3, [WALL_B.id]: 2 })}>
          <SurfaceList projectId={projectId} roomId={roomId} wallMode={props.wallMode} onInspectSurface={props.onInspectSurface} />
        </ProjectPhotosContext.Provider>
      </I18nProvider>,
    );

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [WALL_A, WALL_B], total: 2 });
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue({ id: 'p', surface_id: WALL_A.id, substrate: 'CONCRETE', quality_target: 'S2', planned_works: [] });
  });

  it('lists the walls as one-line rows: name, type, photos, net area — and nothing else', async () => {
    renderRows();

    const row = await screen.findByLabelText(`surface-row-${WALL_A.id}`);
    expect(row).toHaveTextContent('Ściana 1');
    expect(row).toHaveTextContent('Ściana');
    expect(screen.getByLabelText(`surface-row-photos-${WALL_A.id}`)).toHaveTextContent('3');
    expect(screen.getByLabelText(`surface-row-area-${WALL_A.id}`)).toHaveTextContent('8.62 m²');
    expect(screen.getByLabelText(`surface-row-area-${WALL_B.id}`)).toHaveTextContent('7.23 m²');
    // no card behind the row
    expect(screen.queryByLabelText(`options-toggle-${WALL_A.id}`)).toBeNull();
    expect(screen.queryByText(/Powierzchnia brutto/)).toBeNull();
    expect(screen.queryByLabelText(`work-plan-${WALL_A.id}`)).toBeNull();
    expect(row.className).toContain('min-h-11');
  });

  it('a tap opens the card of that wall only, and a tap on its name folds it back', async () => {
    renderRows();
    fireEvent.click(await screen.findByLabelText(`surface-row-${WALL_A.id}`));

    expect(screen.getByLabelText(`options-toggle-${WALL_A.id}`)).toBeInTheDocument();
    expect(screen.getByText(/3\.42 × 2\.52 m/)).toBeInTheDocument();
    expect(screen.queryByLabelText(`surface-row-${WALL_A.id}`)).toBeNull();
    expect(screen.getByLabelText(`surface-row-${WALL_B.id}`)).toBeInTheDocument();
    expect(screen.queryByLabelText(`options-toggle-${WALL_B.id}`)).toBeNull();

    fireEvent.click(screen.getByLabelText(`card-collapse-${WALL_A.id}`));
    expect(screen.getByLabelText(`surface-row-${WALL_A.id}`)).toBeInTheDocument();
    expect(screen.queryByLabelText(`options-toggle-${WALL_A.id}`)).toBeNull();
  });

  it('a wall without dimensions shows a dash instead of an area', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [{ ...surface, name: 'Ściana bez wymiarów' }], total: 1 });
    renderRows();
    expect(await screen.findByLabelText(`surface-row-area-${surface.id}`)).toHaveTextContent('—');
  });

  it('the inspection is on the opened card, outside Opcje, in a calm green, right under the header', async () => {
    const onInspect = vi.fn();
    renderRows({ onInspectSurface: onInspect });
    fireEvent.click(await screen.findByLabelText(`surface-row-${WALL_A.id}`));

    const inspect = screen.getByLabelText(`inspect-surface-${WALL_A.id}`);
    expect(screen.queryByLabelText(`add-opening-${WALL_A.id}-DOOR`)).toBeNull(); // Opcje is still closed
    expect(inspect.className).toContain('bg-emerald-50');
    expect(inspect.className).toContain('min-h-11');
    expect(inspect.compareDocumentPosition(screen.getByLabelText(`work-plan-${WALL_A.id}`)) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(inspect);
    expect(onInspect).toHaveBeenCalledWith(WALL_A.id, 'Ściana 1');
  });

  it('duplicates a wall of an irregular room: the next number and position, the same width and height', async () => {
    vi.mocked(surfacesApi.createSurface).mockResolvedValue({ ...WALL_A, id: 'cccccccc-0000-0000-0000-000000000003', name: 'Ściana 3' });
    renderRows({ wallMode: 'CUSTOM' });
    fireEvent.click(await screen.findByLabelText(`surface-row-${WALL_A.id}`));
    fireEvent.click(screen.getByLabelText(`options-toggle-${WALL_A.id}`));
    const duplicate = screen.getByLabelText(`duplicate-surface-${WALL_A.id}`);
    expect(duplicate).toHaveTextContent('Duplikuj ścianę');
    fireEvent.click(duplicate);

    await waitFor(() => expect(surfacesApi.createSurface).toHaveBeenCalledTimes(1));
    expect(surfacesApi.createSurface).toHaveBeenCalledWith(projectId, roomId, {
      name: 'Ściana 3', surface_type: 'WALL', position: expect.any(Number), width: 3.42, height: 2.52, description: null,
    });
    expect(await screen.findByText('Ścianę zduplikowano')).toBeInTheDocument();
  });

  it('offers no duplicate button in a rectangular room', async () => {
    renderRows();
    fireEvent.click(await screen.findByLabelText(`surface-row-${WALL_A.id}`));
    fireEvent.click(screen.getByLabelText(`options-toggle-${WALL_A.id}`));
    expect(screen.queryByLabelText(`duplicate-surface-${WALL_A.id}`)).toBeNull();
  });

  it('speaks Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderRows({ wallMode: 'CUSTOM' });
    fireEvent.click(await screen.findByLabelText(`surface-row-${WALL_A.id}`));
    fireEvent.click(screen.getByLabelText(`options-toggle-${WALL_A.id}`));
    expect(screen.getByLabelText(`duplicate-surface-${WALL_A.id}`)).toHaveTextContent('Дублировать стену');
  });
});

describe('SurfaceList: a wall only the phone knows (Stage 19E, Q5 (b))', () => {
  beforeEach(() => localStorage.clear());

  const waiting: SurfaceType = { ...surface, width: 3.73, height: 2.68, _pending: true };

  it('shows the typed width × height as a preview marked "~" in the row, and the mark', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [waiting], total: 1 });
    renderSurfaces({ initiallyOpen: false });
    const row = await screen.findByLabelText(`surface-row-${surface.id}`);
    expect(within(row).getByLabelText(`surface-row-area-${surface.id}`)).toHaveTextContent('~10.00 m²');
    expect(within(row).getByLabelText(`pending-mark-${surface.id}`)).toHaveTextContent('Czeka na wysłanie');
  });

  it('in the card replaces the empty gross / deduction / net rows by the preview and says the server will count it', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [waiting], total: 1 });
    renderSurfaces();
    const preview = await screen.findByLabelText(`surface-preview-${surface.id}`);
    expect(preview).toHaveTextContent('~10.00 m²');
    expect(preview).toHaveTextContent('Powierzchnię policzy serwer po synchronizacji.');
    expect(screen.getByLabelText(`pending-mark-${surface.id}`)).toBeInTheDocument();
    expect(screen.queryByText(/= /)).toBeNull();
  });

  it('once the server has the wall its own numbers are shown, with no mark', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [{ ...surface, width: 3.73, height: 2.68, gross_area: '9.996', net_area: '9.996' }], total: 1 });
    renderSurfaces({ initiallyOpen: false });
    const row = await screen.findByLabelText(`surface-row-${surface.id}`);
    expect(within(row).getByLabelText(`surface-row-area-${surface.id}`)).toHaveTextContent('10.00 m²');
    expect(within(row).getByLabelText(`surface-row-area-${surface.id}`)).not.toHaveTextContent('~');
    expect(screen.queryByLabelText(`pending-mark-${surface.id}`)).toBeNull();
  });

  it('a wall the server has, without an area, is not given a "~" preview (only the phone\'s own walls are)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [{ ...surface, width: 3.73, height: 2.68 }], total: 1 });
    renderSurfaces({ initiallyOpen: false });
    const row = await screen.findByLabelText(`surface-row-${surface.id}`);
    expect(within(row).getByLabelText(`surface-row-area-${surface.id}`)).not.toHaveTextContent('~');
    expect(screen.queryByLabelText(`pending-mark-${surface.id}`)).toBeNull();
  });

  it('a waiting wall without dimensions shows no invented number', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [{ ...surface, _pending: true }], total: 1 });
    renderSurfaces({ initiallyOpen: false });
    const row = await screen.findByLabelText(`surface-row-${surface.id}`);
    expect(within(row).getByLabelText(`surface-row-area-${surface.id}`)).toHaveTextContent('—');
  });
});

describe('SurfaceList: changing the size right on the card (owner request, Stage 19)', () => {
  const sized: SurfaceType = { ...surface, width: 1.95, height: 2.6, gross_area: '5.070', net_area: '5.070', deduction_area: '0.000' };
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('the size has an "Edytuj" next to it, without opening the options', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [sized], total: 1 });
    renderSurfaces();
    const button = await screen.findByLabelText(`edit-dimensions-${surface.id}`);
    expect(button).toHaveTextContent('Edytuj');
    expect(button.className).toMatch(/min-h-11/);
    expect(screen.getByText(/1\.95 × 2\.60 m/)).toBeInTheDocument();
    expect(screen.queryByLabelText(`dimensions-form-${surface.id}`)).toBeNull();
  });

  it('opens the two fields in place (centimetres, with the saved size), and saves just the size', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [sized], total: 1 });
    vi.mocked(surfacesApi.updateSurface).mockResolvedValue({ ...sized, width: 2, height: 2.7 });
    const onChanged = vi.fn();
    render(
      <I18nProvider>
        <SurfaceList projectId={projectId} roomId={roomId} initiallyOpen onMeasurementChanged={onChanged} />
      </I18nProvider>,
    );
    fireEvent.click(await screen.findByLabelText(`edit-dimensions-${surface.id}`));

    const width = screen.getByLabelText(`dimensions-width-${surface.id}`);
    expect(width).toHaveValue('195');
    expect(screen.getByLabelText(`dimensions-height-${surface.id}`)).toHaveValue('260');
    fireEvent.change(width, { target: { value: '200' } });
    fireEvent.change(screen.getByLabelText(`dimensions-height-${surface.id}`), { target: { value: '270' } });
    fireEvent.click(screen.getByLabelText(`dimensions-save-${surface.id}`));

    await waitFor(() => expect(surfacesApi.updateSurface).toHaveBeenCalledWith(projectId, roomId, surface.id, { width: 2, height: 2.7 }));
    expect(await screen.findByText('Wymiary zapisane.')).toBeInTheDocument();
    expect(surfacesApi.fetchSurfaces).toHaveBeenCalledTimes(2); // the list is read again: the area is the server's
    expect(onChanged).toHaveBeenCalled();
    expect(screen.queryByLabelText(`dimensions-form-${surface.id}`)).toBeNull();
  });

  it('"Anuluj" closes it and changes nothing', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [sized], total: 1 });
    renderSurfaces();
    fireEvent.click(await screen.findByLabelText(`edit-dimensions-${surface.id}`));
    fireEvent.change(screen.getByLabelText(`dimensions-width-${surface.id}`), { target: { value: '999' } });
    fireEvent.click(screen.getByLabelText(`dimensions-cancel-${surface.id}`));
    expect(screen.queryByLabelText(`dimensions-form-${surface.id}`)).toBeNull();
    expect(surfacesApi.updateSurface).not.toHaveBeenCalled();
    expect(screen.getByText(/1\.95 × 2\.60 m/)).toBeInTheDocument();
  });

  it('a size that is empty or not a positive number is refused before anything is sent', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [sized], total: 1 });
    renderSurfaces();
    fireEvent.click(await screen.findByLabelText(`edit-dimensions-${surface.id}`));
    fireEvent.change(screen.getByLabelText(`dimensions-height-${surface.id}`), { target: { value: '' } });
    fireEvent.click(screen.getByLabelText(`dimensions-save-${surface.id}`));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(surfacesApi.updateSurface).not.toHaveBeenCalled();
    expect(screen.getByLabelText(`dimensions-form-${surface.id}`)).toBeInTheDocument(); // stays open: nothing typed is lost
  });

  it('when the server refuses, the message is shown and the typed size stays', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [sized], total: 1 });
    vi.mocked(surfacesApi.updateSurface).mockRejectedValue(new Error('Server said no'));
    renderSurfaces();
    fireEvent.click(await screen.findByLabelText(`edit-dimensions-${surface.id}`));
    fireEvent.change(screen.getByLabelText(`dimensions-width-${surface.id}`), { target: { value: '210' } });
    fireEvent.click(screen.getByLabelText(`dimensions-save-${surface.id}`));
    expect(await screen.findByText('Server said no')).toBeInTheDocument();
    expect(screen.getByLabelText(`dimensions-width-${surface.id}`)).toHaveValue('210');
  });

  it('a wall without a size is offered "Dodaj wymiary" in the same place', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [surface], total: 1 });
    renderSurfaces();
    const button = await screen.findByLabelText(`edit-dimensions-${surface.id}`);
    expect(button).toHaveTextContent('Dodaj wymiary');
    fireEvent.click(button);
    expect(screen.getByLabelText(`dimensions-width-${surface.id}`)).toHaveValue('');
  });

  it('an archived wall is not edited from the card', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [{ ...sized, is_archived: true }], total: 1 });
    renderSurfaces();
    await screen.findByText(/1\.95 × 2\.60 m/);
    expect(screen.queryByLabelText(`edit-dimensions-${surface.id}`)).toBeNull();
  });

  it('speaks Russian', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [sized], total: 1 });
    renderSurfaces();
    expect(await screen.findByLabelText(`edit-dimensions-${surface.id}`)).toHaveTextContent('Редактировать');
  });

  it('a wall that only the phone knows can be corrected too (the change waits with it)', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [{ ...sized, gross_area: null, net_area: null, _pending: true }], total: 1 });
    vi.mocked(surfacesApi.updateSurface).mockResolvedValue({ ...sized, width: 2 });
    renderSurfaces();
    fireEvent.click(await screen.findByLabelText(`edit-dimensions-${surface.id}`));
    fireEvent.change(screen.getByLabelText(`dimensions-width-${surface.id}`), { target: { value: '200' } });
    fireEvent.click(screen.getByLabelText(`dimensions-save-${surface.id}`));
    await waitFor(() => expect(surfacesApi.updateSurface).toHaveBeenCalledWith(projectId, roomId, surface.id, { width: 2, height: 2.6 }));
  });
});

describe('Compact wall (usability U-5, U-7)', () => {
  const wall = (over: Partial<SurfaceType> = {}): SurfaceType => ({
    ...surface, id: 'cccccccc-0000-0000-0000-000000000003', name: 'Ściana 3', width: 5, height: 2.7,
    gross_area: '13.500', deduction_area: '1.800', net_area: '11.700', ...over,
  });
  const photos = (surfaces: Record<string, number>) => ({
    projectId,
    counts: { ...EMPTY_PHOTO_COUNTS, surfaces },
    isExpanded: () => false,
    toggle: () => {},
    adjust: () => {},
    resolveLocation: () => '',
    ensureLocations: () => {},
  });
  const renderCompact = (initiallyOpen: boolean, walls: SurfaceType[]) => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: walls, total: walls.length });
    return render(
      <I18nProvider>
        <ProjectPhotosContext.Provider value={photos({})}>
          <SurfaceList projectId={projectId} roomId={roomId} initiallyOpen={initiallyOpen} />
        </ProjectPhotosContext.Provider>
      </I18nProvider>,
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    stopAutoOpenAreas?.(); // these tests are about the folded state
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue({ id: 'p', surface_id: 'x', substrate: 'CONCRETE', quality_target: 'S2', template_applications: [], planned_works: [] } as never);
  });

  it('U-7: the collapsed row tells the number of works of the plan, only when there are some', async () => {
    const other = wall({ id: 'dddddddd-0000-0000-0000-000000000004', name: 'Ściana 4', planned_work_count: 0 });
    renderCompact(false, [wall({ planned_work_count: 3 }), other]);
    const row = await screen.findByLabelText(`surface-row-${wall().id}`);
    expect(screen.getByLabelText(`surface-row-works-${wall().id}`)).toHaveTextContent('3');
    expect(screen.getByLabelText(`surface-row-works-${wall().id}`)).toHaveAttribute('title', 'Prace w planie');
    expect(screen.getByLabelText(`surface-row-area-${wall().id}`)).toHaveTextContent('11.70 m²');
    expect(row).toHaveTextContent('Ściana 3');
    expect(screen.queryByLabelText(`surface-row-works-${other.id}`)).toBeNull();
  });

  it('U-7: an opened wall shows the net area alone; the calculation (gross, openings, reveals) opens on a tap on it', async () => {
    renderCompact(true, [wall()]);
    const toggle = await screen.findByLabelText(`area-details-${wall().id}`);
    expect(toggle).toHaveTextContent('11.70 m²');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle.className).toContain('min-h-11');
    expect(screen.queryByLabelText(`area-calculation-${wall().id}`)).toBeNull();
    expect(screen.queryByText(/Powierzchnia brutto/)).toBeNull();
    fireEvent.click(toggle);
    const calculation = screen.getByLabelText(`area-calculation-${wall().id}`);
    expect(calculation).toHaveTextContent('Powierzchnia brutto');
    expect(calculation).toHaveTextContent('13.50 m²');
    expect(calculation).toHaveTextContent('1.80 m²');
    expect(screen.getByLabelText(`area-details-${wall().id}`)).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(screen.getByLabelText(`area-details-${wall().id}`));
    expect(screen.queryByLabelText(`area-calculation-${wall().id}`)).toBeNull();
  });

  it('U-7: the size of an opened wall is one line with its "Edytuj" button', async () => {
    renderCompact(true, [wall()]);
    const edit = await screen.findByLabelText(`edit-dimensions-${wall().id}`);
    expect(edit).toHaveTextContent('Edytuj');
    expect(edit.parentElement).toHaveTextContent('5.00 × 2.70 m');
  });

  it('U-5: Plan | Realizacja are two segments of one row under the caption; each opens its own view, only one at a time', async () => {
    renderCompact(true, [wall()]);
    const group = await screen.findByLabelText(`plan-tabs-${wall().id}`);
    expect(group.parentElement).toHaveTextContent('Rodzaje prac i jakość');
    const plan = within(group).getByLabelText(`work-plan-${wall().id}`);
    const execution = within(group).getByLabelText(`execution-${wall().id}`);
    expect(plan).toHaveTextContent('Plan');
    expect(execution).toHaveTextContent('Realizacja');
    expect(plan.className).toContain('min-h-11');
    expect(execution.className).toContain('min-h-11');
    // the execution button is not repeated under the block
    expect(screen.getAllByLabelText(`execution-${wall().id}`)).toHaveLength(1);
    fireEvent.click(plan);
    expect(await screen.findByLabelText(`work-plan-editor-${wall().id}`)).toBeInTheDocument();
    fireEvent.click(execution);
    expect(await screen.findByLabelText(`execution-view-${wall().id}`)).toBeInTheDocument();
    expect(screen.queryByLabelText(`work-plan-editor-${wall().id}`)).toBeNull();
    expect(execution).toHaveAttribute('aria-expanded', 'true');
    expect(plan).toHaveAttribute('aria-expanded', 'false');
  });
});
