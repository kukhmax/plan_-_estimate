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

  it('creates a surface with the selected type', async () => {
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
      });
    });
    expect(await screen.findByText('Powierzchnia została utworzona')).toBeInTheDocument();
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
