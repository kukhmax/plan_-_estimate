import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { ClientType } from '../types/client';
import { ArchiveScreen } from './ArchiveScreen';

vi.mock('../api/clients', () => ({
  fetchClients: vi.fn(),
  restoreClient: vi.fn(),
  fetchClientDeletePreview: vi.fn(),
  deleteClient: vi.fn(),
}));
vi.mock('../api/projects', () => ({
  fetchProjects: vi.fn(),
  restoreProject: vi.fn(),
  fetchProjectPurgePreview: vi.fn(),
  purgeProject: vi.fn(),
}));
vi.mock('../api/archiveStructure', () => ({ fetchArchivedStructure: vi.fn() }));
vi.mock('../api/rooms', () => ({ restoreRoom: vi.fn() }));
vi.mock('../api/surfaces', () => ({ restoreSurface: vi.fn() }));
vi.mock('../api/photos', async () => ({
  ...(await vi.importActual<typeof import('../api/photos')>('../api/photos')),
  fetchPhotoArchive: vi.fn(),
}));
import { fetchArchivedStructure } from '../api/archiveStructure';
import { deleteClient, fetchClientDeletePreview, fetchClients, restoreClient } from '../api/clients';
import { fetchPhotoArchive } from '../api/photos';
import { fetchProjectPurgePreview, fetchProjects, purgeProject } from '../api/projects';
import { ProjectPurgePreview } from '../api/projects';
import { ProjectType } from '../types/project';
import { restoreRoom } from '../api/rooms';
import { restoreSurface } from '../api/surfaces';

const P1 = '11111111-1111-4111-8111-111111111111';
const R1 = '22222222-2222-4222-8222-222222222222';

const client = (id: string, over: Partial<ClientType> = {}): ClientType => ({
  id, owner_user_id: 'x', client_type: 'PRIVATE_PERSON', first_name: 'Anna', last_name: 'Nowak', company_name: null, phone: null,
  email: null, nip: null, street: null, postal_code: null, city: null, telegram_username: null, notes: null, is_archived: true,
  created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z', ...over,
});

const structure = (over: Partial<Awaited<ReturnType<typeof fetchArchivedStructure>>> = {}) => ({
  rooms: [
    { id: R1, name: 'Salon', project_id: P1, project_name: 'Mieszkanie Mokotów' },
    { id: '33333333-3333-4333-8333-333333333333', name: 'Łazienka', project_id: P1, project_name: 'Mieszkanie Mokotów' },
  ],
  surfaces: [
    { id: 's1', name: 'Ściana 1', surface_type: 'WALL' as const, room_id: 'room-9', room_name: 'Sypialnia', project_id: P1, project_name: 'Dom' },
    { id: 's2', name: 'Sufit', surface_type: 'CEILING' as const, room_id: 'room-9', room_name: 'Sypialnia', project_id: P1, project_name: 'Dom' },
  ],
  rooms_total: 2,
  surfaces_total: 2,
  ...over,
});

function renderScreen() {
  return render(<I18nProvider><ArchiveScreen /></I18nProvider>);
}

const openTab = async (name: string) => {
  fireEvent.click(await screen.findByLabelText(`archive-tab-${name}`));
};

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(fetchClients).mockResolvedValue({ items: [client('c1'), client('c2', { first_name: 'Piotr', last_name: 'Kowalski' })], total: 2 });
  vi.mocked(fetchProjects).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(fetchArchivedStructure).mockResolvedValue(structure());
  vi.mocked(fetchPhotoArchive).mockResolvedValue({ items: [], archived_total: 0, trashed_total: 0, urls_expire_at: null });
});

describe('ArchiveScreen: rooms and surfaces of all objects (archive cleanup AC-4a)', () => {
  it('has the tabs of rooms and surfaces with the numbers the server counted', async () => {
    renderScreen();
    await waitFor(() => expect(screen.getByLabelText('archive-count-rooms')).toHaveTextContent('(2)'));
    expect(screen.getByLabelText('archive-count-surfaces')).toHaveTextContent('(2)');
    expect(screen.getByLabelText('archive-tab-rooms')).toHaveTextContent('Pomieszczenia');
    expect(screen.getByLabelText('archive-tab-surfaces')).toHaveTextContent('Powierzchnie');
  });

  it('lists the archived rooms with their object', async () => {
    renderScreen();
    await openTab('rooms');
    const list = await screen.findByLabelText('archive-rooms-list');
    expect(within(list).getByText('Salon')).toBeInTheDocument();
    expect(within(list).getByText('Łazienka')).toBeInTheDocument();
    expect(within(list).getAllByText('Obiekt: Mieszkanie Mokotów')).toHaveLength(2);
  });

  it('lists the archived surfaces named in the current language, with the object and the room', async () => {
    renderScreen();
    await openTab('surfaces');
    const list = await screen.findByLabelText('archive-surfaces-list');
    expect(within(list).getByText('Ściana 1')).toBeInTheDocument();
    expect(within(list).getByText('Sufit')).toBeInTheDocument();
    expect(within(list).getAllByText('Obiekt: Dom → pomieszczenie: Sypialnia')).toHaveLength(2);
  });

  it('restores a room in its own object: the row leaves, the number goes down, the owner is told', async () => {
    vi.mocked(restoreRoom).mockResolvedValue({} as never);
    renderScreen();
    await openTab('rooms');
    fireEvent.click(await screen.findByLabelText(`restore-room-${R1}`));
    await waitFor(() => expect(restoreRoom).toHaveBeenCalledWith(P1, R1));
    await waitFor(() => expect(screen.queryByLabelText(`archived-room-${R1}`)).toBeNull());
    expect(screen.getByLabelText('archive-count-rooms')).toHaveTextContent('(1)');
    expect(screen.getByRole('status')).toHaveTextContent('Pomieszczenie przywrócone.');
  });

  it('restores a surface in its room and object', async () => {
    vi.mocked(restoreSurface).mockResolvedValue({} as never);
    renderScreen();
    await openTab('surfaces');
    fireEvent.click(await screen.findByLabelText('restore-surface-s1'));
    await waitFor(() => expect(restoreSurface).toHaveBeenCalledWith(P1, 'room-9', 's1'));
    await waitFor(() => expect(screen.queryByLabelText('archived-surface-s1')).toBeNull());
    expect(screen.getByRole('status')).toHaveTextContent('Powierzchnia przywrócona.');
  });

  it('a floor or ceiling that clashes with an active one stays in the list and the owner is told why', async () => {
    vi.mocked(restoreSurface).mockRejectedValue(new ApiError('Room already has an active CEILING surface', 409));
    renderScreen();
    await openTab('surfaces');
    fireEvent.click(await screen.findByLabelText('restore-surface-s2'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Pomieszczenie ma już aktywną podłogę lub sufit');
    expect(screen.getByLabelText('archived-surface-s2')).toBeInTheDocument();
  });

  it('empty lists say so', async () => {
    vi.mocked(fetchArchivedStructure).mockResolvedValue(structure({ rooms: [], surfaces: [], rooms_total: 0, surfaces_total: 0 }));
    renderScreen();
    await openTab('rooms');
    expect(await screen.findByLabelText('archive-empty-rooms')).toHaveTextContent('Brak zarchiwizowanych pomieszczeń.');
    await openTab('surfaces');
    expect(await screen.findByLabelText('archive-empty-surfaces')).toBeInTheDocument();
  });

  it('says when only the first part of a long list is shown', async () => {
    vi.mocked(fetchArchivedStructure).mockResolvedValue(structure({ rooms_total: 230 }));
    renderScreen();
    await openTab('rooms');
    expect(await screen.findByText('Pokazano pierwsze 2 z 230.')).toBeInTheDocument();
  });

  it('a failed read of the rooms does not hide the clients, and the retry reads again', async () => {
    vi.mocked(fetchArchivedStructure).mockRejectedValueOnce(new ApiError('boom', 0, 'NETWORK_ERROR'));
    renderScreen();
    expect(await screen.findByLabelText('archive-clients-list')).toBeInTheDocument();
    await openTab('rooms');
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać archiwum.');
    fireEvent.click(screen.getByLabelText('archive-retry'));
    expect(await screen.findByLabelText('archive-rooms-list')).toBeInTheDocument();
  });

  it('the Russian interface uses the Russian names of the tabs and rows', async () => {
    localStorage.setItem('locale', 'ru');
    renderScreen();
    await openTab('surfaces');
    const list = await screen.findByLabelText('archive-surfaces-list');
    expect(within(list).getAllByText('Объект: Dom → помещение: Sypialnia')).toHaveLength(2);
    expect(screen.getByLabelText('archive-tab-rooms')).toHaveTextContent('Помещения');
  });
});

describe('ArchiveScreen: deleting an archived client for good (archive cleanup AC-5a)', () => {
  const preview = (over: Partial<{ projects: number; can_delete: boolean }> = {}) => ({
    client_id: 'c1', archived: true, projects: 0, can_delete: true, ...over,
  });

  it('asks the server first, shows what will be deleted, and deletes only after the confirmation', async () => {
    vi.mocked(fetchClientDeletePreview).mockResolvedValue(preview());
    vi.mocked(deleteClient).mockResolvedValue(undefined);
    renderScreen();
    fireEvent.click(await screen.findByLabelText('delete-client-c1'));
    expect(await screen.findByText(/Zostanie usunięty klient „Anna Nowak”/)).toBeInTheDocument();
    expect(screen.getByText('Tej operacji nie można cofnąć.')).toBeInTheDocument();
    expect(fetchClientDeletePreview).toHaveBeenCalledWith('c1');
    expect(deleteClient).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText('client-delete-confirm'));
    await waitFor(() => expect(deleteClient).toHaveBeenCalledWith('c1'));
    await waitFor(() => expect(screen.queryByLabelText('archived-client-c1')).toBeNull());
    expect(screen.getByLabelText('archived-client-c2')).toBeInTheDocument();
    expect(screen.getByLabelText('archive-count-clients')).toHaveTextContent('(1)');
    expect(screen.getByRole('status')).toHaveTextContent('Klient usunięty.');
  });

  it('the deletion cannot be confirmed before the server has answered what it meets', async () => {
    let answer: (value: ReturnType<typeof preview>) => void = () => undefined;
    vi.mocked(fetchClientDeletePreview).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('delete-client-c1'));
    expect(screen.getByRole('status')).toHaveTextContent('Sprawdzanie…');
    fireEvent.click(screen.getByLabelText('client-delete-confirm'));
    expect(deleteClient).not.toHaveBeenCalled();
    expect(screen.getByLabelText('client-delete-confirm')).toBeDisabled();
    answer(preview());
    await waitFor(() => expect(screen.getByLabelText('client-delete-confirm')).not.toBeDisabled());
  });

  it('"Anuluj" deletes nothing and closes the panel', async () => {
    vi.mocked(fetchClientDeletePreview).mockResolvedValue(preview());
    renderScreen();
    fireEvent.click(await screen.findByLabelText('delete-client-c1'));
    fireEvent.click(await screen.findByLabelText('client-delete-cancel'));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(deleteClient).not.toHaveBeenCalled();
    expect(screen.getByLabelText('archived-client-c1')).toBeInTheDocument();
  });

  it('a client with objects cannot be deleted: the count is told and there is no confirm button', async () => {
    vi.mocked(fetchClientDeletePreview).mockResolvedValue(preview({ projects: 2, can_delete: false }));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('delete-client-c1'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Klient ma obiekty: 2 (także w archiwum)');
    expect(screen.queryByLabelText('client-delete-confirm')).toBeNull();
    expect(deleteClient).not.toHaveBeenCalled();
  });

  it('an object that appeared meanwhile turns the panel into the blocked state instead of a vague error', async () => {
    vi.mocked(fetchClientDeletePreview).mockResolvedValue(preview());
    vi.mocked(deleteClient).mockRejectedValue(new ApiError('The client still has objects', 409, 'CLIENT_HAS_PROJECTS', { code: 'CLIENT_HAS_PROJECTS', projects: 1 }));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('delete-client-c1'));
    fireEvent.click(await screen.findByLabelText('client-delete-confirm'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Klient ma obiekty: 1');
    expect(screen.queryByLabelText('client-delete-confirm')).toBeNull();
    expect(screen.getByLabelText('archived-client-c1')).toBeInTheDocument();
  });

  it('another failure keeps the client and says the deletion did not work', async () => {
    vi.mocked(fetchClientDeletePreview).mockResolvedValue(preview());
    vi.mocked(deleteClient).mockRejectedValue(new ApiError('boom', 0, 'NETWORK_ERROR'));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('delete-client-c1'));
    fireEvent.click(await screen.findByLabelText('client-delete-confirm'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się usunąć klienta.');
    expect(screen.getByLabelText('archived-client-c1')).toBeInTheDocument();
    expect(screen.getByLabelText('client-delete-confirm')).not.toBeDisabled();
  });

  it('restoring still works next to the deletion', async () => {
    vi.mocked(restoreClient).mockResolvedValue(client('c1', { is_archived: false }));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('restore-client-c1'));
    await waitFor(() => expect(screen.queryByLabelText('archived-client-c1')).toBeNull());
  });

  it('the Russian texts of the deletion', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(fetchClientDeletePreview).mockResolvedValue(preview());
    renderScreen();
    fireEvent.click(await screen.findByLabelText('delete-client-c1'));
    expect(await screen.findByText(/Будет удалён клиент «Anna Nowak»/)).toBeInTheDocument();
    expect(screen.getByText('Это действие нельзя отменить.')).toBeInTheDocument();
  });
});

describe('ArchiveScreen: deleting an archived object for good (archive cleanup AC-5b)', () => {
  const project = (id: string, name = 'Mieszkanie Mokotów'): ProjectType => ({
    id, owner_id: 'x', client_id: null, name, address: 'ul. Dobra 10', city: 'Warszawa', postal_code: '00-001', description: null,
    status: 'PLANNING', is_archived: true, created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z',
  } as ProjectType);
  const full = (over: Partial<ProjectPurgePreview> = {}): ProjectPurgePreview => ({
    project_id: 'p1', name: 'Mieszkanie Mokotów', archived: true, can_purge: true, rooms: 3, surfaces: 14, openings: 5, inspections: 2, estimates: 1,
    documents: 4, sent_documents: 0, photos: 12, photo_files: 11, bytes: 5 * 1024 * 1024, annotations: 6, may_be_in_backups: true, blockers: [], ...over,
  });
  const openPanel = async () => {
    fireEvent.click(await screen.findByLabelText('archive-tab-projects'));
    fireEvent.click(await screen.findByLabelText('delete-project-p1'));
  };

  beforeEach(() => {
    vi.mocked(fetchProjects).mockResolvedValue({ items: [project('p1'), project('p2', 'Dom')], total: 2 });
  });

  it('shows what the server counted, and the deletion waits for the tick and the button', async () => {
    vi.mocked(fetchProjectPurgePreview).mockResolvedValue(full({ sent_documents: 2 }));
    // after the deletion the server no longer has the object: the lists that are read again do not hold it
    vi.mocked(purgeProject).mockImplementation(async () => {
      vi.mocked(fetchProjects).mockResolvedValue({ items: [project('p2', 'Dom')], total: 1 });
      return { purged: true, photo_files: 11, storage_pending: 0 };
    });
    renderScreen();
    await openPanel();
    const lines = await screen.findByLabelText('project-delete-lines');
    expect(fetchProjectPurgePreview).toHaveBeenCalledWith('p1');
    for (const expected of ['Pomieszczenia: 3', 'Powierzchnie: 14', 'Otwory: 5', 'Badania: 2', 'Kosztorysy: 1', 'Umowy i protokoły: 4', 'Zdjęcia: 12; pliki w magazynie: 11 (5.2 MB)', 'Znaczniki na zdjęciach: 6']) {
      expect(within(lines).getByText(expected, { exact: false })).toBeInTheDocument();
    }
    expect(screen.getByText(/Wysłane dokumenty: 2/)).toBeInTheDocument();
    expect(screen.getByText(/osobny krok właściciela/)).toBeInTheDocument();
    const confirm = screen.getByLabelText('project-delete-confirm');
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(purgeProject).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText('project-delete-understood'));
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(purgeProject).toHaveBeenCalledWith('p1'));
    await waitFor(() => expect(screen.queryByLabelText('archived-project-p1')).toBeNull());
    expect(screen.getByLabelText('archived-project-p2')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Obiekt usunięty.');
    // the lists are read again: the rooms and the photos of the object went with it
    await waitFor(() => expect(vi.mocked(fetchArchivedStructure).mock.calls.length).toBeGreaterThan(1));
    await waitFor(() => expect(vi.mocked(fetchPhotoArchive).mock.calls.length).toBeGreaterThan(1));
  });

  it('the files that are still in the storage are said, so the owner knows a retry follows', async () => {
    vi.mocked(fetchProjectPurgePreview).mockResolvedValue(full());
    vi.mocked(purgeProject).mockResolvedValue({ purged: true, photo_files: 11, storage_pending: 11 });
    renderScreen();
    await openPanel();
    fireEvent.click(await screen.findByLabelText('project-delete-understood'));
    fireEvent.click(screen.getByLabelText('project-delete-confirm'));
    expect(await screen.findByText('Obiekt usunięty. Pliki zdjęć w magazynie zostaną usunięte przy ponowieniu.')).toBeInTheDocument();
  });

  it('an object held by an issued or signed document cannot be deleted: the reasons are told, no tick, no confirm button', async () => {
    vi.mocked(fetchProjectPurgePreview).mockResolvedValue(full({
      can_purge: false,
      blockers: [{ kind: 'CONTRACT', protocol_id: 'a', status: 'SIGNED' }, { kind: 'DOWNTIME', protocol_id: 'b', status: 'NOTICED' }],
    }));
    renderScreen();
    await openPanel();
    expect(await screen.findByRole('alert')).toHaveTextContent('wydana lub podpisana umowa');
    expect(screen.getByRole('alert')).toHaveTextContent('zgłoszony lub zamknięty przestój');
    expect(screen.getByRole('alert')).toHaveTextContent('można tylko zarchiwizować');
    expect(screen.queryByLabelText('project-delete-confirm')).toBeNull();
    expect(screen.queryByLabelText('project-delete-understood')).toBeNull();
    expect(purgeProject).not.toHaveBeenCalled();
  });

  it('"Anuluj" deletes nothing', async () => {
    vi.mocked(fetchProjectPurgePreview).mockResolvedValue(full());
    renderScreen();
    await openPanel();
    fireEvent.click(await screen.findByLabelText('project-delete-cancel'));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(purgeProject).not.toHaveBeenCalled();
    expect(screen.getByLabelText('archived-project-p1')).toBeInTheDocument();
  });

  it('an object that is not archived (the server says so) cannot be confirmed', async () => {
    vi.mocked(fetchProjectPurgePreview).mockResolvedValue(full({ archived: false, can_purge: false }));
    renderScreen();
    await openPanel();
    fireEvent.click(await screen.findByLabelText('project-delete-understood'));
    expect(screen.getByLabelText('project-delete-confirm')).toBeDisabled();
  });

  it('a photo that appeared meanwhile: nothing is deleted, the owner is told, the count is read again and the tick is taken back', async () => {
    vi.mocked(fetchProjectPurgePreview).mockResolvedValue(full());
    vi.mocked(purgeProject).mockRejectedValue(new ApiError('changed', 409, 'PROJECT_PURGE_CONFLICT'));
    renderScreen();
    await openPanel();
    fireEvent.click(await screen.findByLabelText('project-delete-understood'));
    fireEvent.click(screen.getByLabelText('project-delete-confirm'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nic nie usunięto');
    expect(vi.mocked(fetchProjectPurgePreview).mock.calls.length).toBe(2);
    expect(screen.getByLabelText('project-delete-understood')).not.toBeChecked();
    expect(screen.getByLabelText('archived-project-p1')).toBeInTheDocument();
  });

  it('a document issued meanwhile turns the panel into the blocked state', async () => {
    vi.mocked(fetchProjectPurgePreview).mockResolvedValueOnce(full());
    vi.mocked(fetchProjectPurgePreview).mockResolvedValueOnce(full({ can_purge: false, blockers: [{ kind: 'ACCEPTANCE', protocol_id: 'z', status: 'ISSUED' }] }));
    vi.mocked(purgeProject).mockRejectedValue(new ApiError('held', 409, 'PROJECT_PURGE_BLOCKED'));
    renderScreen();
    await openPanel();
    fireEvent.click(await screen.findByLabelText('project-delete-understood'));
    fireEvent.click(screen.getByLabelText('project-delete-confirm'));
    expect(await screen.findByText('wydany protokół odbioru')).toBeInTheDocument();
    expect(screen.queryByLabelText('project-delete-confirm')).toBeNull();
  });

  it('another failure keeps the object and says the deletion did not work', async () => {
    vi.mocked(fetchProjectPurgePreview).mockResolvedValue(full());
    vi.mocked(purgeProject).mockRejectedValue(new ApiError('boom', 0, 'NETWORK_ERROR'));
    renderScreen();
    await openPanel();
    fireEvent.click(await screen.findByLabelText('project-delete-understood'));
    fireEvent.click(screen.getByLabelText('project-delete-confirm'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się usunąć obiektu.');
    expect(screen.getByLabelText('archived-project-p1')).toBeInTheDocument();
  });

  it('an empty object says it is empty', async () => {
    vi.mocked(fetchProjectPurgePreview).mockResolvedValue(full({
      rooms: 0, surfaces: 0, openings: 0, inspections: 0, estimates: 0, documents: 0, photos: 0, photo_files: 0, bytes: 0, annotations: 0, may_be_in_backups: false,
    }));
    renderScreen();
    await openPanel();
    expect(await screen.findByText(/Obiekt jest pusty/)).toBeInTheDocument();
    expect(screen.queryByText(/osobny krok właściciela/)).toBeNull();
  });

  it('the Russian texts of the deletion of an object', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(fetchProjectPurgePreview).mockResolvedValue(full({ blockers: [] }));
    renderScreen();
    await openPanel();
    expect(await screen.findByText('Помещения: 3')).toBeInTheDocument();
    expect(screen.getByText('Я понимаю, что это действие нельзя отменить.')).toBeInTheDocument();
  });
});

