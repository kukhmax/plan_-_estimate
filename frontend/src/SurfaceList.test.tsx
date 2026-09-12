import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as openingsApi from './api/openings';
import * as surfacesApi from './api/surfaces';
import { SurfaceList } from './components/SurfaceList';
import { I18nProvider } from './hooks/useI18n';
import { SurfaceType } from './types/surface';

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
      />
    </I18nProvider>,
  );
}

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
      expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toBeInTheDocument(),
    );
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
    expect(screen.getByLabelText(`edit-surface-${surface.id}`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`archive-surface-${surface.id}`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`add-opening-${surface.id}-DOOR`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`add-opening-${surface.id}-WINDOW`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`add-opening-${surface.id}-OTHER`)).toHaveClass('min-h-11');
    expect(screen.getByLabelText(`toggle-openings-${surface.id}`)).toHaveClass('min-h-11');
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

    await waitFor(() => expect(screen.getByLabelText(`restore-surface-${surface.id}`)).toBeInTheDocument());
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
    expect(await screen.findByText('Wall 4')).toBeInTheDocument();
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
    await waitFor(() => expect(screen.getByText('Wall 4')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('generate-walls'));
    await waitFor(() => expect(surfacesApi.generateWalls).toHaveBeenCalledTimes(2));

    expect(screen.getByLabelText('surfaces-list').querySelectorAll('li')).toHaveLength(4);
    expect(screen.getAllByText('Wall 1')).toHaveLength(1);
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
