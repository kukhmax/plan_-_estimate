import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as clientsApi from './api/clients';
import * as projectsApi from './api/projects';
import * as roomsApi from './api/rooms';
import * as surfacesApi from './api/surfaces';
import { ProjectWorkspace } from './components/ProjectWorkspace';
import { I18nProvider } from './hooks/useI18n';
import { ClientType } from './types/client';
import { ProjectType } from './types/project';
import { RoomType } from './types/room';

vi.mock('./api/clients', () => ({ fetchClients: vi.fn() }));
vi.mock('./api/projects', () => ({
  fetchProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  archiveProject: vi.fn(),
  restoreProject: vi.fn(),
}));
vi.mock('./api/rooms', () => ({
  fetchRooms: vi.fn(),
  createRoom: vi.fn(),
  updateRoom: vi.fn(),
  archiveRoom: vi.fn(),
  restoreRoom: vi.fn(),
}));
vi.mock('./api/surfaces', () => ({
  fetchSurfaces: vi.fn(),
  createSurface: vi.fn(),
  updateSurface: vi.fn(),
  archiveSurface: vi.fn(),
  restoreSurface: vi.fn(),
}));

const project: ProjectType = {
  id: '11111111-1111-1111-1111-111111111111',
  owner_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  client_id: '22222222-2222-2222-2222-222222222222',
  name: 'Mieszkanie Mokotów',
  address: 'ul. Dobra 10',
  city: 'Warszawa',
  postal_code: '00-001',
  description: 'Remont mieszkania',
  status: 'PLANNING',
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const client: ClientType = {
  id: '22222222-2222-2222-2222-222222222222',
  owner_user_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  client_type: 'PRIVATE_PERSON',
  first_name: 'Jan',
  last_name: 'Kowalski',
  company_name: null,
  phone: null,
  email: null,
  nip: null,
  notes: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const room: RoomType = {
  id: '33333333-3333-3333-3333-333333333333',
  project_id: project.id,
  name: 'Salon',
  description: 'Główne pomieszczenie',
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

function renderWorkspace() {
  return render(<I18nProvider><ProjectWorkspace /></I18nProvider>);
}

describe('ProjectWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [project], total: 1 });
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [client], total: 1 });
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
  });

  it('renders projects with their assigned clients', async () => {
    renderWorkspace();

    await waitFor(() => expect(screen.getByText('Mieszkanie Mokotów')).toBeInTheDocument());
    expect(screen.getByText(/Jan Kowalski/)).toBeInTheDocument();
    expect(screen.getByText('Planowanie')).toBeInTheDocument();
  });

  it('creates a project and opens its room view', async () => {
    const created = { ...project, client_id: null, name: 'Nowy obiekt' };
    vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(projectsApi.createProject).mockResolvedValue(created);
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText('no-projects')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-project'));
    fireEvent.change(screen.getByLabelText('project-name'), { target: { value: 'Nowy obiekt' } });
    fireEvent.change(screen.getByLabelText('project-address'), { target: { value: 'ul. Nowa 5' } });
    fireEvent.change(screen.getByLabelText('project-city'), { target: { value: 'Kraków' } });
    fireEvent.change(screen.getByLabelText('project-postal-code'), { target: { value: '30-001' } });
    fireEvent.submit(screen.getByLabelText('project-form'));

    await waitFor(() => {
      expect(projectsApi.createProject).toHaveBeenCalledWith({
        name: 'Nowy obiekt',
        address: 'ul. Nowa 5',
        city: 'Kraków',
        postal_code: '30-001',
        description: null,
        status: 'PLANNING',
        client_id: null,
      });
    });
    expect(await screen.findByText('Obiekt został utworzony')).toBeInTheDocument();
    expect(screen.getByLabelText('project-detail')).toBeInTheDocument();
    expect(await screen.findByLabelText('no-rooms')).toBeInTheDocument();
  });

  it('navigates from a project through a room to surfaces and back', async () => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [room], total: 1 });
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${room.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${room.id}`));

    const navigation = screen.getByRole('navigation', { name: 'hierarchy-navigation' });
    expect(within(navigation).getByText('Obiekty')).toBeInTheDocument();
    expect(within(navigation).getByText('Pomieszczenia')).toBeInTheDocument();
    expect(within(navigation).getByText('Salon')).toBeInTheDocument();
    expect(within(navigation).getByText('Powierzchnie')).toBeInTheDocument();
    expect(await screen.findByLabelText('no-surfaces')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('back-to-rooms'));
    expect(await screen.findByLabelText(`open-room-${room.id}`)).toBeInTheDocument();
  });

  it('shows archived projects with a restore action', async () => {
    vi.mocked(projectsApi.fetchProjects).mockResolvedValue({
      items: [{ ...project, is_archived: true }],
      total: 1,
    });
    renderWorkspace();

    expect(await screen.findByText('Zarchiwizowany')).toBeInTheDocument();
    expect(screen.getByLabelText(`restore-project-${project.id}`)).toBeInTheDocument();
  });
});
