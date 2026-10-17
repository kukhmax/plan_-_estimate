import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { ArchiveScreen } from './ArchiveScreen';
import { I18nProvider } from '../hooks/useI18n';
import * as clientsApi from '../api/clients';
import * as projectsApi from '../api/projects';
import * as photosApi from '../api/photos';
import * as structureApi from '../api/archiveStructure';
import { ClientType } from '../types/client';
import { ProjectType } from '../types/project';

vi.mock('../api/clients', () => ({ fetchClients: vi.fn(), restoreClient: vi.fn() }));
vi.mock('../api/projects', () => ({ fetchProjects: vi.fn(), restoreProject: vi.fn() }));
vi.mock('../api/archiveStructure', () => ({ fetchArchivedStructure: vi.fn() }));
vi.mock('../api/photos', async () => ({
  ...(await vi.importActual<typeof import('../api/photos')>('../api/photos')),
  fetchPhotoArchive: vi.fn(),
}));

const client = (id: string, overrides: Partial<ClientType> = {}): ClientType => ({
  id, owner_user_id: 'x', client_type: 'PRIVATE_PERSON', first_name: 'Anna', last_name: 'Nowak', company_name: null, phone: null,
  email: null, nip: null, street: null, postal_code: null, city: null, telegram_username: null, notes: null, is_archived: true,
  created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z', ...overrides,
});

const project = (id: string, overrides: Partial<ProjectType> = {}): ProjectType => ({
  id, owner_id: 'x', client_id: null, name: 'Mieszkanie Mokotów', address: 'ul. Dobra 10', city: 'Warszawa', postal_code: '00-001',
  description: null, status: 'PLANNING', is_archived: true, created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z', ...overrides,
} as ProjectType);

function renderScreen() {
  return render(<I18nProvider><ArchiveScreen /></I18nProvider>);
}

describe('ArchiveScreen (Stage 16K.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({
      items: [client('c1'), client('c2', { client_type: 'COMPANY', company_name: 'Budex sp. z o.o.', first_name: null, last_name: null }), client('c3', { is_archived: false, first_name: 'Active', last_name: 'Client' })],
      total: 3,
    });
    vi.mocked(structureApi.fetchArchivedStructure).mockResolvedValue({ rooms: [], surfaces: [], rooms_total: 0, surfaces_total: 0 });
    vi.mocked(photosApi.fetchPhotoArchive).mockResolvedValue({ items: [], archived_total: 2, trashed_total: 1, urls_expire_at: null });
    vi.mocked(projectsApi.fetchProjects).mockResolvedValue({
      items: [project('p1'), project('p2', { name: 'Dom pod Krakowem', city: 'Kraków' }), project('p3', { name: 'In work', is_archived: false })],
      total: 3,
    });
  });

  it('asks for the archived clients and objects and shows only the archived ones, with the numbers on the tabs', async () => {
    renderScreen();
    expect(await screen.findByLabelText('archive-clients-list')).toBeInTheDocument();
    expect(clientsApi.fetchClients).toHaveBeenCalledWith({ include_archived: true });
    expect(projectsApi.fetchProjects).toHaveBeenCalledWith(true);
    const list = screen.getByLabelText('archive-clients-list');
    expect(within(list).getByText('Anna Nowak')).toBeInTheDocument();
    expect(within(list).getByText('Budex sp. z o.o.')).toBeInTheDocument();
    expect(screen.queryByText('Active Client')).toBeNull();
    expect(screen.getByLabelText('archive-count-clients')).toHaveTextContent('(2)');
    expect(screen.getByLabelText('archive-count-projects')).toHaveTextContent('(2)');
  });

  it('the objects tab shows the archived objects with the address and no object that is in work', async () => {
    renderScreen();
    await screen.findByLabelText('archive-clients-list');
    fireEvent.click(screen.getByLabelText('archive-tab-projects'));
    const list = await screen.findByLabelText('archive-projects-list');
    expect(within(list).getByText('Mieszkanie Mokotów')).toBeInTheDocument();
    expect(within(list).getByText('Dom pod Krakowem')).toBeInTheDocument();
    expect(within(list).getByText('ul. Dobra 10, Warszawa')).toBeInTheDocument();
    expect(screen.queryByText('In work')).toBeNull();
    expect(screen.queryByLabelText('archive-clients-list')).toBeNull();
  });

  it('restores a client with one tap: the row leaves the archive, the number goes down, the owner is told', async () => {
    vi.mocked(clientsApi.restoreClient).mockResolvedValue(client('c1', { is_archived: false }));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('restore-client-c1'));
    await waitFor(() => expect(screen.queryByLabelText('archived-client-c1')).toBeNull());
    expect(clientsApi.restoreClient).toHaveBeenCalledWith('c1');
    expect(screen.getByRole('status')).toHaveTextContent('Klient przywrócony.');
    expect(screen.getByLabelText('archive-count-clients')).toHaveTextContent('(1)');
    expect(screen.getByLabelText('archived-client-c2')).toBeInTheDocument();
  });

  it('restores an object with one tap', async () => {
    vi.mocked(projectsApi.restoreProject).mockResolvedValue(project('p1', { is_archived: false }));
    renderScreen();
    await screen.findByLabelText('archive-clients-list');
    fireEvent.click(screen.getByLabelText('archive-tab-projects'));
    fireEvent.click(await screen.findByLabelText('restore-project-p1'));
    await waitFor(() => expect(screen.queryByLabelText('archived-project-p1')).toBeNull());
    expect(projectsApi.restoreProject).toHaveBeenCalledWith('p1');
    expect(screen.getByRole('status')).toHaveTextContent('Obiekt przywrócony.');
  });

  it('a refused restore keeps the row and says so', async () => {
    vi.mocked(clientsApi.restoreClient).mockRejectedValue(new Error('boom'));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('restore-client-c1'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się przywrócić.');
    expect(screen.getByLabelText('archived-client-c1')).toBeInTheDocument();
    expect(screen.getByLabelText('restore-client-c1')).not.toBeDisabled();
  });

  it('while one restore runs the other buttons wait (no double tap)', async () => {
    let finish: (value: ClientType) => void = () => undefined;
    vi.mocked(clientsApi.restoreClient).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('restore-client-c1'));
    expect(screen.getByLabelText('restore-client-c1')).toHaveTextContent('Przywracanie…');
    expect(screen.getByLabelText('restore-client-c2')).toBeDisabled();
    fireEvent.click(screen.getByLabelText('restore-client-c2'));
    expect(clientsApi.restoreClient).toHaveBeenCalledTimes(1);
    finish(client('c1', { is_archived: false }));
    await waitFor(() => expect(screen.queryByLabelText('archived-client-c1')).toBeNull());
  });

  it('says when the archive is empty, and when it cannot be loaded, with a retry', async () => {
    vi.mocked(clientsApi.fetchClients).mockRejectedValueOnce(new Error('offline'));
    renderScreen();
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać archiwum.');
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [], total: 0 });
    fireEvent.click(screen.getByLabelText('archive-retry'));
    expect(await screen.findByLabelText('archive-empty-clients')).toHaveTextContent('Brak zarchiwizowanych klientów.');
    fireEvent.click(screen.getByLabelText('archive-tab-projects'));
    expect(await screen.findByLabelText('archive-empty-projects')).toBeInTheDocument();
  });

  it('every button is a full-width 44 px control and long names wrap', async () => {
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [client('c1', { first_name: 'Александр', last_name: 'Константинопольский-Заморский-Великолепный' })], total: 1 });
    renderScreen();
    const restore = await screen.findByLabelText('restore-client-c1');
    expect(restore.className).toContain('w-full');
    expect(restore.className).toContain('min-h-11');
    expect(screen.getByLabelText('archive-tab-clients').className).toContain('min-h-11');
    expect(screen.getByLabelText('archive-tab-projects').className).toContain('min-h-11');
    expect(screen.getByText(/Константинопольский/).className).toContain('break-words');
  });

  it('is in Russian too', async () => {
    localStorage.setItem('locale', 'ru');
    renderScreen();
    expect(await screen.findByRole('heading', { name: 'Архив' })).toBeInTheDocument();
    expect(screen.getByLabelText('restore-client-c1')).toHaveTextContent('Восстановить');
    expect(screen.getByLabelText('archive-tab-projects')).toHaveTextContent('Объекты');
  });

  it('the photos tab carries the number of photos in the archive and in the trash and opens the list of them (AC-3a)', async () => {
    renderScreen();
    await screen.findByLabelText('archive-clients-list');
    await waitFor(() => expect(screen.getByLabelText('archive-count-photos')).toHaveTextContent('(3)'));
    expect(screen.queryByLabelText('archive-photos')).toBeNull();
    fireEvent.click(screen.getByLabelText('archive-tab-photos'));
    expect(await screen.findByLabelText('archive-photos')).toBeInTheDocument();
    expect(screen.queryByLabelText('archive-clients-list')).toBeNull();
    expect(photosApi.fetchPhotoArchive).toHaveBeenCalledWith('archived', 100);
    fireEvent.click(screen.getByLabelText('archive-tab-clients'));
    expect(screen.queryByLabelText('archive-photos')).toBeNull();
    expect(screen.getByLabelText('archive-clients-list')).toBeInTheDocument();
  });
});
