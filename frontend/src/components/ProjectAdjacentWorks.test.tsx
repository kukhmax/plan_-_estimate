import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/adjacentWorks';
import { ApiError } from '../api/http';
import * as roomsApi from '../api/rooms';
import { I18nProvider } from '../hooks/useI18n';
import type { AdjacentWork } from '../types/adjacentWork';
import { ProjectAdjacentWorks } from './ProjectAdjacentWorks';

vi.mock('../api/adjacentWorks', () => ({
  fetchAdjacentWorks: vi.fn(),
  createAdjacentWork: vi.fn(),
  updateAdjacentWork: vi.fn(),
  archiveAdjacentWork: vi.fn(),
  restoreAdjacentWork: vi.fn(),
}));
vi.mock('../api/rooms', () => ({ fetchRooms: vi.fn() }));

const ROOMS = {
  items: [
    { id: 'r-salon', project_id: 'p1', name: 'Salon', description: null, is_archived: false },
    { id: 'r-kuchnia', project_id: 'p1', name: 'Kuchnia', description: null, is_archived: false },
  ],
  total: 2,
};

function work(over: Partial<AdjacentWork> = {}): AdjacentWork {
  return {
    id: 'w1', project_id: 'p1', work_name: 'Instalacja elektryczna', performer: 'Firma Prąd', room_ids: ['r-salon', 'r-kuchnia'],
    period_from: '2026-10-12', period_to: '2026-10-14', order_relation: 'BEFORE_OURS', order_note: 'elektryka przed tynkiem',
    responsibility_note: 'sprząta wykonawca instalacji', coordination_note: null, is_archived: false,
    created_at: '2026-10-09T10:00:00Z', updated_at: '2026-10-09T10:00:00Z', ...over,
  };
}

const list = (...items: AdjacentWork[]) => ({ items, total: items.length });

function renderCard() {
  return render(<I18nProvider><ProjectAdjacentWorks projectId="p1" /></I18nProvider>);
}

async function openAddForm() {
  fireEvent.click(await screen.findByLabelText('add-adjacent-work'));
  return screen.getByLabelText('adjacent-work-form');
}

describe('ProjectAdjacentWorks (Stage 16D.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchAdjacentWorks).mockResolvedValue(list());
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue(ROOMS as never);
  });

  it('loads the register and says when it is empty', async () => {
    renderCard();
    expect(await screen.findByText('Nie zarejestrowano jeszcze prac innych wykonawców.')).toBeInTheDocument();
    expect(api.fetchAdjacentWorks).toHaveBeenCalledWith('p1', false);
    expect(screen.getByLabelText('add-adjacent-work').className).toContain('min-h-11');
  });

  it('shows an entry with its performer, order, rooms by name, period and notes', async () => {
    vi.mocked(api.fetchAdjacentWorks).mockResolvedValue(list(work()));
    renderCard();
    const row = await screen.findByLabelText('adjacent-work-w1');
    expect(row).toHaveTextContent('Instalacja elektryczna');
    expect(row).toHaveTextContent('Firma Prąd');
    expect(row).toHaveTextContent('Przed naszymi pracami');
    expect(row).toHaveTextContent('Salon, Kuchnia');
    expect(row).toHaveTextContent('2026-10-12 – 2026-10-14');
    expect(row).toHaveTextContent('elektryka przed tynkiem');
    expect(row).toHaveTextContent('sprząta wykonawca instalacji');
  });

  it('shows "the whole object" when no rooms are named and a half-open period in words', async () => {
    vi.mocked(api.fetchAdjacentWorks).mockResolvedValue(list(work({ room_ids: null, period_to: null })));
    renderCard();
    const row = await screen.findByLabelText('adjacent-work-w1');
    expect(row).toHaveTextContent('Cały obiekt');
    expect(row).toHaveTextContent('od 2026-10-12');
  });

  it('adds an entry for the whole object by default, sending only what was filled in', async () => {
    vi.mocked(api.createAdjacentWork).mockResolvedValue(work());
    renderCard();
    await openAddForm();
    fireEvent.change(screen.getByLabelText('adjacent-work-name'), { target: { value: '  Hydraulika ' } });
    await act(async () => { fireEvent.submit(screen.getByLabelText('adjacent-work-form')); });
    expect(api.createAdjacentWork).toHaveBeenCalledWith('p1', {
      work_name: 'Hydraulika', performer: undefined, room_ids: undefined, period_from: undefined, period_to: undefined,
      order_relation: 'BEFORE_OURS', order_note: undefined, responsibility_note: undefined, coordination_note: undefined,
    });
    await waitFor(() => expect(screen.queryByLabelText('adjacent-work-form')).toBeNull());
  });

  it('names rooms when "the whole object" is switched off and refuses an empty choice before the server', async () => {
    vi.mocked(api.createAdjacentWork).mockResolvedValue(work());
    renderCard();
    await openAddForm();
    fireEvent.change(screen.getByLabelText('adjacent-work-name'), { target: { value: 'Płytki' } });
    fireEvent.click(screen.getByLabelText('adjacent-work-whole-object'));
    await act(async () => { fireEvent.submit(screen.getByLabelText('adjacent-work-form')); });
    expect(screen.getByLabelText('adjacent-work-error')).toHaveTextContent('Wybierz pomieszczenia albo zaznacz „Cały obiekt”');
    expect(api.createAdjacentWork).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('adjacent-work-room-r-kuchnia'));
    fireEvent.change(screen.getByLabelText('adjacent-work-order'), { target: { value: 'AFTER_OURS' } });
    await act(async () => { fireEvent.submit(screen.getByLabelText('adjacent-work-form')); });
    expect(api.createAdjacentWork).toHaveBeenCalledWith('p1', expect.objectContaining({ room_ids: ['r-kuchnia'], order_relation: 'AFTER_OURS' }));
  });

  it('refuses a blank name and an upside-down period on the phone', async () => {
    renderCard();
    await openAddForm();
    await act(async () => { fireEvent.submit(screen.getByLabelText('adjacent-work-form')); });
    expect(screen.getByLabelText('adjacent-work-error')).toHaveTextContent('Podaj rodzaj prac');
    fireEvent.change(screen.getByLabelText('adjacent-work-name'), { target: { value: 'Płytki' } });
    fireEvent.change(screen.getByLabelText('adjacent-work-from'), { target: { value: '2026-10-14' } });
    fireEvent.change(screen.getByLabelText('adjacent-work-to'), { target: { value: '2026-10-12' } });
    await act(async () => { fireEvent.submit(screen.getByLabelText('adjacent-work-form')); });
    expect(screen.getByLabelText('adjacent-work-error')).toHaveTextContent('Data „do” nie może być wcześniejsza niż „od”');
    expect(api.createAdjacentWork).not.toHaveBeenCalled();
  });

  it('edits an entry: an emptied optional field is sent as null, the whole object as room_ids null', async () => {
    vi.mocked(api.fetchAdjacentWorks).mockResolvedValue(list(work()));
    vi.mocked(api.updateAdjacentWork).mockResolvedValue(work());
    renderCard();
    fireEvent.click(await screen.findByLabelText('edit-adjacent-work-w1'));
    expect(screen.getByLabelText('adjacent-work-name')).toHaveValue('Instalacja elektryczna');
    fireEvent.change(screen.getByLabelText('adjacent-work-performer'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('adjacent-work-from'), { target: { value: '' } });
    fireEvent.click(screen.getByLabelText('adjacent-work-whole-object'));
    await act(async () => { fireEvent.submit(screen.getByLabelText('adjacent-work-form')); });
    expect(api.updateAdjacentWork).toHaveBeenCalledWith('p1', 'w1', expect.objectContaining({
      performer: null, period_from: null, room_ids: null, period_to: '2026-10-14', order_note: 'elektryka przed tynkiem',
    }));
  });

  it('says in words what the server refused', async () => {
    vi.mocked(api.createAdjacentWork).mockRejectedValue(new ApiError('English', 422, 'ADJACENT_WORK_ROOM_INVALID', { code: 'ADJACENT_WORK_ROOM_INVALID' }));
    renderCard();
    await openAddForm();
    fireEvent.change(screen.getByLabelText('adjacent-work-name'), { target: { value: 'Płytki' } });
    await act(async () => { fireEvent.submit(screen.getByLabelText('adjacent-work-form')); });
    expect(await screen.findByLabelText('adjacent-work-error')).toHaveTextContent('nie należy do tego obiektu');
  });

  it('archives and restores, and can show the archived ones', async () => {
    vi.mocked(api.fetchAdjacentWorks).mockResolvedValue(list(work()));
    vi.mocked(api.archiveAdjacentWork).mockResolvedValue(work({ is_archived: true }));
    vi.mocked(api.restoreAdjacentWork).mockResolvedValue(work());
    renderCard();
    const archive = await screen.findByLabelText('archive-adjacent-work-w1');
    await act(async () => { fireEvent.click(archive); });
    expect(api.archiveAdjacentWork).toHaveBeenCalledWith('p1', 'w1');
    vi.mocked(api.fetchAdjacentWorks).mockResolvedValue(list(work({ is_archived: true })));
    await act(async () => { fireEvent.click(screen.getByLabelText('show-archived-adjacent-works')); });
    const row = await screen.findByLabelText('adjacent-work-w1');
    expect(within(row).getByText('Zarchiwizowana')).toBeInTheDocument();
    expect(within(row).queryByLabelText('edit-adjacent-work-w1')).toBeNull();
    await act(async () => { fireEvent.click(within(row).getByLabelText('restore-adjacent-work-w1')); });
    expect(api.restoreAdjacentWork).toHaveBeenCalledWith('p1', 'w1');
  });

  it('offers a retry when the first load fails and is localised in Russian', async () => {
    vi.mocked(api.fetchAdjacentWorks).mockRejectedValueOnce(new Error('net')).mockResolvedValue(list(work()));
    localStorage.setItem('locale', 'ru');
    renderCard();
    expect(await screen.findByText('Не удалось загрузить работы других подрядчиков.')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Повторить' })); });
    const row = await screen.findByLabelText('adjacent-work-w1');
    expect(row).toHaveTextContent('До наших работ');
    expect(screen.getByText('Работы других подрядчиков')).toBeInTheDocument();
  });
});
