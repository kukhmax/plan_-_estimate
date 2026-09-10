import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

function renderSurfaces() {
  return render(
    <I18nProvider>
      <SurfaceList projectId={projectId} roomId={roomId} />
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

  it('creates a surface with the selected type and optional dimensions as null', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.createSurface).mockResolvedValue({
      ...surface,
      name: 'Sufit główny',
      surface_type: 'CEILING',
      description: null,
    });
    renderSurfaces();

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-surface'));
    fireEvent.change(screen.getByLabelText('surface-name'), { target: { value: 'Sufit główny' } });
    fireEvent.change(screen.getByLabelText('surface-type'), { target: { value: 'CEILING' } });
    fireEvent.submit(screen.getByLabelText('surface-form'));

    await waitFor(() => {
      expect(surfacesApi.createSurface).toHaveBeenCalledWith(projectId, roomId, {
        name: 'Sufit główny',
        surface_type: 'CEILING',
        description: null,
        width: null,
        height: null,
      });
    });
    expect(await screen.findByText('Powierzchnia została utworzona')).toBeInTheDocument();
  });

  it('creates a wall surface with metric dimensions', async () => {
    const wallWithDims: SurfaceType = {
      ...surface,
      width: 5,
      height: 2.7,
      gross_area: '13.500',
      deduction_area: '0.000',
      net_area: '13.500',
    };
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.createSurface).mockResolvedValue(wallWithDims);
    renderSurfaces();

    await waitFor(() => expect(screen.getByLabelText('no-surfaces')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-surface'));
    fireEvent.change(screen.getByLabelText('surface-name'), { target: { value: 'Ściana północna' } });
    fireEvent.change(screen.getByLabelText('surface-type'), { target: { value: 'WALL' } });
    fireEvent.change(screen.getByLabelText('surface-width'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('surface-height'), { target: { value: '2.7' } });
    fireEvent.submit(screen.getByLabelText('surface-form'));

    await waitFor(() => {
      expect(surfacesApi.createSurface).toHaveBeenCalledWith(projectId, roomId, {
        name: 'Ściana północna',
        surface_type: 'WALL',
        description: null,
        width: 5,
        height: 2.7,
      });
    });
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
    expect(screen.getByText(/5\.000 × 2\.700 m/)).toBeInTheDocument();
    expect(screen.getByText(/13\.500 m²/)).toBeInTheDocument();
    expect(screen.getByText(/1\.800 m²/)).toBeInTheDocument();
    expect(screen.getByText(/11\.700 m²/)).toBeInTheDocument();
    expect(screen.getByLabelText(`toggle-openings-${surface.id}`)).toBeInTheDocument();
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
});
