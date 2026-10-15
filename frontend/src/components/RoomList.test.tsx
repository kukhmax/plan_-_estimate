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

  it('takes centimetres in a text field with the decimal keypad, so no decimal point has to be typed (Stage 18G)', async () => {
    renderList();
    fireEvent.click(await screen.findByLabelText('add-room'));

    for (const label of ['room-length', 'room-width', 'room-height']) {
      const input = screen.getByLabelText(label);
      expect(input).toHaveAttribute('type', 'text');
      expect(input).toHaveAttribute('inputMode', 'decimal');
      expect(input).not.toHaveAttribute('step');
    }
  });

  it('accepts and submits ordinary integer and decimal dimensions (8C.1)', async () => {
    renderList();
    fireEvent.click(await screen.findByLabelText('add-room'));

    fireEvent.change(screen.getByLabelText('room-name'), { target: { value: 'Salon' } });
    fireEvent.change(screen.getByLabelText('room-length'), { target: { value: '600' } });
    fireEvent.change(screen.getByLabelText('room-width'), { target: { value: '490' } });
    fireEvent.change(screen.getByLabelText('room-height'), { target: { value: '476' } });
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
describe('RoomList action row on a narrow phone', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [room], total: 1 });
  });

  it('stacks "open" over a two-column "edit / archive" row so long Russian labels fit at 320 px, with 44 px targets', async () => {
    renderList();
    const actions = await screen.findByLabelText('room-actions-room-1');
    expect(actions).toHaveClass('grid', 'grid-cols-2');
    expect(actions).not.toHaveClass('grid-cols-3');
    const open = screen.getByLabelText('open-room-room-1');
    expect(open).toHaveClass('col-span-2', 'min-h-10');
    for (const label of ['edit-room-room-1', 'archive-room-room-1']) {
      const button = screen.getByLabelText(label);
      expect(button).toHaveClass('min-h-10', 'min-w-0', 'break-words');
    }
    expect(open).toHaveClass('break-words');
  });
});
