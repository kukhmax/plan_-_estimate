import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as roomsApi from '../api/rooms';
import { I18nProvider } from '../hooks/useI18n';
import { RoomCreatePayload, RoomType } from '../types/room';
import { RoomList } from './RoomList';

vi.mock('../api/rooms', () => ({
  fetchRooms: vi.fn(),
  createRoom: vi.fn(),
  updateRoom: vi.fn(),
  archiveRoom: vi.fn(),
  restoreRoom: vi.fn(),
}));

const room: RoomType = {
  id: 'room-1',
  project_id: 'proj-1',
  name: 'Salon',
  description: null,
  length: null,
  width: null,
  height: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

function renderList() {
  return render(
    <I18nProvider>
      <RoomList projectId="proj-1" onOpenRoom={vi.fn()} />
    </I18nProvider>,
  );
}

describe('RoomList measurement inputs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(roomsApi.createRoom).mockResolvedValue(room);
    vi.mocked(roomsApi.updateRoom).mockResolvedValue(room);
    vi.mocked(roomsApi.archiveRoom).mockResolvedValue(room);
    vi.mocked(roomsApi.restoreRoom).mockResolvedValue(room);
  });

  it('uses step="any" so natural decimals are valid (8C.1)', async () => {
    renderList();
    fireEvent.click(await screen.findByLabelText('add-room'));

    // Regression (Blocker A): min="0.001" combined with step="0.01" made
    // ordinary values like 6 / 4.9 / 4.76 fall outside the step lattice and
    // native browser validation blocked them. step="any" keeps only min.
    for (const label of ['room-length', 'room-width', 'room-height']) {
      const input = screen.getByLabelText(label);
      expect(input).toHaveAttribute('type', 'number');
      expect(input).toHaveAttribute('inputMode', 'decimal');
      expect(input).toHaveAttribute('min', '0.001');
      expect(input).toHaveAttribute('step', 'any');
    }
  });

  it('accepts and submits ordinary integer and decimal dimensions (8C.1)', async () => {
    renderList();
    fireEvent.click(await screen.findByLabelText('add-room'));

    fireEvent.change(screen.getByLabelText('room-name'), { target: { value: 'Salon' } });
    fireEvent.change(screen.getByLabelText('room-length'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('room-width'), { target: { value: '4.9' } });
    fireEvent.change(screen.getByLabelText('room-height'), { target: { value: '4.76' } });
    fireEvent.submit(screen.getByLabelText('room-form'));

    await waitFor(() =>
      expect(roomsApi.createRoom).toHaveBeenCalledWith(
        'proj-1',
        expect.objectContaining<RoomCreatePayload>({
          name: 'Salon',
          length: 6,
          width: 4.9,
          height: 4.76,
        }),
      ),
    );
  });
});