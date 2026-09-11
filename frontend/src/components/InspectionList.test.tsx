import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as inspectionsApi from '../api/inspections';
import { I18nProvider } from '../hooks/useI18n';
import { Inspection, InspectionTarget } from '../types/inspection';
import { InspectionList } from './InspectionList';

vi.mock('../api/inspections', () => ({
  fetchInspections: vi.fn(),
  fetchInspectionFindings: vi.fn(),
  archiveInspection: vi.fn(),
  restoreInspection: vi.fn(),
  reopenInspection: vi.fn(),
}));

const roomInspection: Inspection = {
  id: 'ins-room',
  room_id: 'room-1',
  surface_id: null,
  plane: null,
  template_id: 'tpl-1',
  substrate: 'CONCRETE',
  quality_target: 'S2',
  status: 'DRAFT',
  notes: null,
  completed_at: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const wallInspection: Inspection = {
  ...roomInspection,
  id: 'ins-wall',
  surface_id: 'surf-1',
  status: 'COMPLETED',
  completed_at: '2026-09-09T12:00:00Z',
};

const roomTarget: InspectionTarget = { kind: 'room' };
const wallTarget: InspectionTarget = { kind: 'surface', surfaceId: 'surf-1', surfaceName: 'Ściana północna' };

function renderList(target: InspectionTarget, onStart = vi.fn(), onOpen = vi.fn()) {
  return render(
    <I18nProvider>
      <InspectionList
        projectId="proj-1"
        roomId="room-1"
        target={target}
        onStart={onStart}
        onOpen={onOpen}
      />
    </I18nProvider>,
  );
}

describe('InspectionList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({
      items: [],
      total: 0,
    });
  });

  it('filters inspections to the target and renders substrate/status/quality/findings (INSPECTION_LIST)', async () => {
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({
      items: [roomInspection, wallInspection],
      total: 2,
    });
    renderList(roomTarget);
    expect(await screen.findByText('Beton')).toBeInTheDocument();
    expect(screen.queryByText('Ściana północna')).not.toBeInTheDocument();
  });

  it('renders wall inspection when the wall target matches (ENTRY)', async () => {
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({
      items: [roomInspection, wallInspection],
      total: 2,
    });
    renderList(wallTarget);
    expect(await screen.findByText('Beton')).toBeInTheDocument();
    expect(screen.queryByText('Badanie pomieszczenia')).not.toBeInTheDocument();
  });

  it('shows a completed inspection with completed date', async () => {
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({
      items: [wallInspection],
      total: 1,
    });
    renderList(wallTarget);
    expect(await screen.findByText('Zakończone')).toBeInTheDocument();
    expect(screen.getByText(/Zakończono/)).toBeInTheDocument();
    expect(screen.getByLabelText('Podgląd')).toBeInTheDocument();
    expect(screen.getByLabelText('Wznów')).toBeInTheDocument();
  });

  it('does not issue per-card findings requests when rendering the list (N+1)', async () => {
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({
      items: [
        roomInspection,
        { ...roomInspection, id: 'ins-2' },
        { ...roomInspection, id: 'ins-3' },
      ],
      total: 3,
    });
    renderList(roomTarget);
    expect(await screen.findAllByLabelText(/Otwórz/)).toHaveLength(3);
    expect(inspectionsApi.fetchInspectionFindings).not.toHaveBeenCalled();
  });

  it('starts a new inspection for the target (ENTRY)', async () => {
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({
      items: [],
      total: 0,
    });
    const onStart = vi.fn();
    renderList(roomTarget, onStart);
    await screen.findByText('Brak badań podłoża');
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    expect(onStart).toHaveBeenCalledWith(roomTarget);
  });

  it('opens an inspection via onOpen (ENTRY)', async () => {
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({
      items: [roomInspection],
      total: 1,
    });
    const onOpen = vi.fn();
    renderList(roomTarget, vi.fn(), onOpen);
    fireEvent.click(await screen.findByLabelText('Otwórz'));
    expect(onOpen).toHaveBeenCalledWith('ins-room');
  });

  it('archives an inspection and reloads the list', async () => {
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({
      items: [roomInspection],
      total: 1,
    });
    vi.mocked(inspectionsApi.archiveInspection).mockResolvedValue({
      ...roomInspection,
      is_archived: true,
    });
    renderList(roomTarget);
    fireEvent.click(await screen.findByLabelText('Archiwizuj'));
    await waitFor(() =>
      expect(inspectionsApi.archiveInspection).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-room',
      ),
    );
    expect(inspectionsApi.fetchInspections).toHaveBeenCalled();
  });

  it('reopens a completed inspection and reloads', async () => {
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({
      items: [wallInspection],
      total: 1,
    });
    vi.mocked(inspectionsApi.reopenInspection).mockResolvedValue({
      ...wallInspection,
      status: 'DRAFT',
      completed_at: null,
    });
    renderList(wallTarget);
    fireEvent.click(await screen.findByLabelText('Wznów'));
    await waitFor(() =>
      expect(inspectionsApi.reopenInspection).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-wall',
      ),
    );
  });

  it('restores an archived inspection when show archived is enabled', async () => {
    const archived = { ...roomInspection, is_archived: true };
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({
      items: [archived],
      total: 1,
    });
    vi.mocked(inspectionsApi.restoreInspection).mockResolvedValue(roomInspection);
    renderList(roomTarget);
    fireEvent.click(await screen.findByLabelText('Pokaż zarchiwizowane'));
    await screen.findByLabelText('Przywróć');
    fireEvent.click(screen.getByLabelText('Przywróć'));
    await waitFor(() =>
      expect(inspectionsApi.restoreInspection).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-room',
      ),
    );
  });
});
