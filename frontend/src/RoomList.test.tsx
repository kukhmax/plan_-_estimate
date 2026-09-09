import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as roomsApi from './api/rooms';
import { RoomList } from './components/RoomList';
import { I18nProvider } from './hooks/useI18n';
import { RoomType } from './types/room';

vi.mock('./api/rooms', () => ({
  fetchRooms: vi.fn(),
  createRoom: vi.fn(),
  updateRoom: vi.fn(),
  archiveRoom: vi.fn(),
  restoreRoom: vi.fn(),
}));

const projectId = '11111111-1111-1111-1111-111111111111';
const room: RoomType = {
  id: '22222222-2222-2222-2222-222222222222',
  project_id: projectId,
  name: 'Salon',
  description: 'Pomieszczenie dzienne',
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

function renderRooms(onOpenRoom = vi.fn()) {
  return render(
    <I18nProvider>
      <RoomList projectId={projectId} onOpenRoom={onOpenRoom} />
    </I18nProvider>,
  );
}

describe('RoomList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [room], total: 1 });
  });

  it('renders rooms and opens the selected room', async () => {
    const onOpenRoom = vi.fn();
    renderRooms(onOpenRoom);

    await waitFor(() => expect(screen.getByText('Salon')).toBeInTheDocument());
    expect(screen.getByText('Pomieszczenie dzienne')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(`open-room-${room.id}`));
    expect(onOpenRoom).toHaveBeenCalledWith(room);
  });

  it('creates a room inside the current project', async () => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(roomsApi.createRoom).mockResolvedValue(room);
    renderRooms();

    await waitFor(() => expect(screen.getByLabelText('no-rooms')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-room'));
    fireEvent.change(screen.getByLabelText('room-name'), { target: { value: '  Salon  ' } });
    fireEvent.change(screen.getByLabelText('room-description'), { target: { value: '  Pomieszczenie dzienne  ' } });
    fireEvent.submit(screen.getByLabelText('room-form'));

    await waitFor(() => {
      expect(roomsApi.createRoom).toHaveBeenCalledWith(projectId, {
        name: 'Salon',
        description: 'Pomieszczenie dzienne',
      });
    });
    expect(await screen.findByText('Pomieszczenie zostało utworzone')).toBeInTheDocument();
  });

  it('archives an active room and reloads the list', async () => {
    vi.mocked(roomsApi.archiveRoom).mockResolvedValue({ ...room, is_archived: true });
    renderRooms();

    await waitFor(() => expect(screen.getByLabelText(`archive-room-${room.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`archive-room-${room.id}`));

    await waitFor(() => expect(roomsApi.archiveRoom).toHaveBeenCalledWith(projectId, room.id));
    expect(await screen.findByText('Pomieszczenie zostało zarchiwizowane')).toBeInTheDocument();
    expect(roomsApi.fetchRooms).toHaveBeenCalledTimes(2);
  });
});
