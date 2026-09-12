import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as checklistsApi from './api/checklists';
import * as clientsApi from './api/clients';
import * as inspectionsApi from './api/inspections';
import * as openingsApi from './api/openings';
import * as projectsApi from './api/projects';
import * as roomsApi from './api/rooms';
import * as surfacesApi from './api/surfaces';
import { ProjectWorkspace } from './components/ProjectWorkspace';
import { I18nProvider } from './hooks/useI18n';
import { ChecklistTemplate } from './types/checklist';
import { ClientType } from './types/client';
import { Inspection } from './types/inspection';
import { OpeningType } from './types/opening';
import { ProjectType } from './types/project';
import { RoomType } from './types/room';
import { SurfaceType } from './types/surface';

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
  fetchRoom: vi.fn(),
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
  generateWalls: vi.fn(),
}));
vi.mock('./api/openings', () => ({
  fetchOpenings: vi.fn(),
  createOpening: vi.fn(),
  updateOpening: vi.fn(),
  archiveOpening: vi.fn(),
  restoreOpening: vi.fn(),
}));
vi.mock('./api/checklists', () => ({
  fetchChecklistTemplates: vi.fn(),
  fetchChecklistTemplate: vi.fn(),
}));
vi.mock('./api/inspections', () => ({
  fetchInspections: vi.fn(),
  createInspection: vi.fn(),
  fetchInspection: vi.fn(),
  updateInspection: vi.fn(),
  fetchInspectionAnswers: vi.fn(),
  putInspectionAnswers: vi.fn(),
  completeInspection: vi.fn(),
  reopenInspection: vi.fn(),
  archiveInspection: vi.fn(),
  restoreInspection: vi.fn(),
  fetchInspectionFindings: vi.fn(),
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

const measuredRoom: RoomType = {
  id: '33333333-3333-3333-3333-333333333333',
  project_id: project.id,
  name: 'Salon',
  description: 'Główne pomieszczenie',
  length: 5,
  width: 4,
  height: 2.7,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
  calculations: {
    floor_area: '20.000',
    ceiling_area: '20.000',
    perimeter: '18.000',
    total_wall_area: '48.600',
    wall_area_length: '27.000',
    wall_area_width: '21.600',
    total_deduction_area: null,
    net_wall_area: null,
  },
};

const wallSurface: SurfaceType = {
  id: '44444444-4444-4444-4444-444444444444',
  room_id: measuredRoom.id,
  name: 'Ściana północna',
  surface_type: 'WALL',
  width: 5,
  height: 2.7,
  gross_area: '13.500',
  deduction_area: null,
  net_area: '13.500',
  description: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const doorOpening: OpeningType = {
  id: '55555555-5555-5555-5555-555555555555',
  surface_id: wallSurface.id,
  opening_type: 'DOOR',
  name: 'Drzwi balkonowe',
  width: 0.9,
  height: 2.0,
  quantity: 1,
  single_area: '1.800',
  total_area: '1.800',
  description: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const concreteTemplate: ChecklistTemplate = {
  id: 'tpl-1',
  code: 'substrate-concrete',
  version: 1,
  substrate: 'CONCRETE',
  title_key: 'checklist.template.concrete.title',
  active: true,
  sections: [
    {
      id: 'sec-1',
      key: 'general_conditions',
      position: 0,
      title_key: 'checklist.section.general_conditions',
      description_key: null,
      questions: [
        {
          id: 'q-bool',
          position: 0,
          key: 'cracks_present',
          text_key: 'checklist.question.cracks_present',
          hint_key: null,
          unit_key: null,
          answer_type: 'BOOLEAN',
          finding_key: 'CRACK',
          options: [],
        },
      ],
    },
  ],
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const inspection: Inspection = {
  id: 'ins-1',
  room_id: measuredRoom.id,
  surface_id: null,
  plane: null,
  template_id: concreteTemplate.id,
  substrate: 'CONCRETE',
  quality_target: 'S2',
  status: 'DRAFT',
  notes: null,
  completed_at: null,
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
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(room);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(checklistsApi.fetchChecklistTemplates).mockResolvedValue({
      items: [concreteTemplate],
      total: 1,
    });
    vi.mocked(checklistsApi.fetchChecklistTemplate).mockResolvedValue(concreteTemplate);
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({
      items: [],
      total: 0,
    });
    vi.mocked(inspectionsApi.createInspection).mockResolvedValue(inspection);
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

  it('integrates Telegram BackButton: hidden at top level, visible in project and room detail, and navigates hierarchy', async () => {
    let clickHandler: (() => void) | undefined;
    const backButton = {
      isVisible: false,
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn((cb: () => void) => {
        clickHandler = cb;
      }),
      offClick: vi.fn(),
    };
    window.Telegram = {
      WebApp: {
        initData: '',
        initDataUnsafe: {},
        version: '8.0',
        platform: 'web',
        colorScheme: 'light',
        themeParams: {},
        isExpanded: false,
        viewportHeight: 800,
        viewportStableHeight: 800,
        ready: vi.fn(),
        expand: vi.fn(),
        close: vi.fn(),
        BackButton: backButton,
      },
    };

    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [room], total: 1 });
    const { unmount } = renderWorkspace();

    // 1. Top level: BackButton is hidden
    await waitFor(() => expect(screen.getByText('Mieszkanie Mokotów')).toBeInTheDocument());
    expect(backButton.hide).toHaveBeenCalled();
    expect(backButton.show).not.toHaveBeenCalled();

    // 2. Open project detail: BackButton becomes visible
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${room.id}`)).toBeInTheDocument());
    expect(backButton.show).toHaveBeenCalledTimes(1);
    expect(backButton.onClick).toHaveBeenCalled();

    // 3. Open room detail: BackButton remains active
    fireEvent.click(screen.getByLabelText(`open-room-${room.id}`));
    expect(await screen.findByLabelText('no-surfaces')).toBeInTheDocument();

    // 4. Click native BackButton: returns to parent Project (rooms list)
    act(() => {
      clickHandler?.();
    });
    await waitFor(() => expect(screen.getByLabelText(`open-room-${room.id}`)).toBeInTheDocument());

    // 5. Click native BackButton again: returns to Projects list and hides BackButton
    act(() => {
      clickHandler?.();
    });
    await waitFor(() => expect(screen.getByText('Mieszkanie Mokotów')).toBeInTheDocument());
    expect(backButton.hide).toHaveBeenCalled();

    // 6. Unmount cleanly
    unmount();
    expect(backButton.offClick).toHaveBeenCalled();
  });

  it('displays room calculations summary when opening a measured room', async () => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [measuredRoom], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(measuredRoom);
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));

    await waitFor(() => expect(screen.getByLabelText(`open-room-${measuredRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${measuredRoom.id}`));

    const summary = await screen.findByLabelText('room-calculations-summary');
    expect(summary).toBeInTheDocument();
    expect(within(summary).getByText(/5\.000 × 4\.000 × 2\.700 m/)).toBeInTheDocument();
    expect(within(summary).getAllByText('20.000 m²')).toHaveLength(2); // floor & ceiling
    expect(within(summary).getByText('18.000 m')).toBeInTheDocument(); // perimeter
    expect(within(summary).getAllByText('48.600 m²')).toHaveLength(2); // total wall area & net wall area
    expect(within(summary).getByText('0.000 m²')).toBeInTheDocument(); // total deductions
  });

  it('reconciles dependent state across Opening -> Surface -> Room on opening creation without page reload', async () => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [measuredRoom], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(measuredRoom);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallSurface], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });

    renderWorkspace();

    // 1. Open project and room
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${measuredRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${measuredRoom.id}`));

    // Initial check: wall surface has 13.500 gross, 0 deduction, 13.500 net
    await waitFor(() => expect(screen.getByText('Ściana północna')).toBeInTheDocument());
    expect(screen.getByLabelText(`toggle-openings-${wallSurface.id}`)).toBeInTheDocument();

    // 2. Open openings list for wallSurface
    fireEvent.click(screen.getByLabelText(`toggle-openings-${wallSurface.id}`));
    expect(await screen.findByLabelText(`no-openings-${wallSurface.id}`)).toBeInTheDocument();

    // 3. Prepare mocked responses for after opening creation
    const wallWithDeduction: SurfaceType = {
      ...wallSurface,
      deduction_area: '1.800',
      net_area: '11.700',
    };
    const roomWithDeduction: RoomType = {
      ...measuredRoom,
      calculations: {
        ...measuredRoom.calculations!,
        total_deduction_area: '1.800',
        net_wall_area: '46.800',
      },
    };

    vi.mocked(openingsApi.createOpening).mockResolvedValue(doorOpening);
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [doorOpening], total: 1 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallWithDeduction], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(roomWithDeduction);

    // 4. Click add opening and submit form
    fireEvent.click(screen.getByLabelText(`add-opening-${wallSurface.id}`));
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2.0' } });
    fireEvent.submit(screen.getByLabelText(`opening-form-${wallSurface.id}`));

    // 5. Verify Opening list refreshed
    await waitFor(() => expect(screen.getByText('Drzwi')).toBeInTheDocument());
    expect(screen.getByText(/0\.900 × 2\.000 m/)).toBeInTheDocument();

    // 6. Verify Surface deduction & net area refreshed
    const surfaceItem = screen.getByLabelText(`surface-item-${wallSurface.id}`);
    expect(within(surfaceItem).getAllByText(/1\.800 m²/)).toHaveLength(2);
    expect(within(surfaceItem).getByText(/11\.700 m²/)).toBeInTheDocument();

    // 7. Verify Room aggregate calculations refreshed (total deductions and net wall area)
    const roomSummary = screen.getByLabelText('room-calculations-summary');
    expect(within(roomSummary).getByText('1.800 m²')).toBeInTheDocument();
    expect(within(roomSummary).getByText('46.800 m²')).toBeInTheDocument();
  });

  it('reconciles dependent state across Opening -> Surface -> Room on opening archive and restore', async () => {
    const wallWithDeduction: SurfaceType = {
      ...wallSurface,
      deduction_area: '1.800',
      net_area: '11.700',
    };
    const roomWithDeduction: RoomType = {
      ...measuredRoom,
      calculations: {
        ...measuredRoom.calculations!,
        total_deduction_area: '1.800',
        net_wall_area: '46.800',
      },
    };

    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [roomWithDeduction], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(roomWithDeduction);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallWithDeduction], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [doorOpening], total: 1 });

    renderWorkspace();

    // Open project and room
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${measuredRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${measuredRoom.id}`));

    // Open openings list
    await waitFor(() => expect(screen.getByLabelText(`toggle-openings-${wallSurface.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`toggle-openings-${wallSurface.id}`));
    await waitFor(() => expect(screen.getByLabelText(`archive-opening-${doorOpening.id}`)).toBeInTheDocument());

    // Prepare mock responses for after ARCHIVE
    vi.mocked(openingsApi.archiveOpening).mockResolvedValue({ ...doorOpening, is_archived: true });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallSurface], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(measuredRoom);

    // Click archive
    fireEvent.click(screen.getByLabelText(`archive-opening-${doorOpening.id}`));

    // Check Surface refreshed: deduction 0.000, net 13.500
    await waitFor(() => {
      const surfaceItem = screen.getByLabelText(`surface-item-${wallSurface.id}`);
      expect(within(surfaceItem).getByText(/0\.000 m²/)).toBeInTheDocument();
      expect(within(surfaceItem).getAllByText(/13\.500 m²/)).toHaveLength(2);
    });

    // Check Room summary refreshed: deductions 0.000, net 48.600
    const roomSummaryAfterArchive = screen.getByLabelText('room-calculations-summary');
    expect(within(roomSummaryAfterArchive).getByText('0.000 m²')).toBeInTheDocument();
    expect(within(roomSummaryAfterArchive).getAllByText('48.600 m²')).toHaveLength(2);

    // Now test RESTORE:
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [{ ...doorOpening, is_archived: true }],
      total: 1,
    });
    // Show archived openings
    fireEvent.click(screen.getByLabelText(`show-archived-openings-${wallSurface.id}`));

    await waitFor(() => expect(screen.getByLabelText(`restore-opening-${doorOpening.id}`)).toBeInTheDocument());

    // Prepare mock responses for after RESTORE
    vi.mocked(openingsApi.restoreOpening).mockResolvedValue(doorOpening);
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [doorOpening], total: 1 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallWithDeduction], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(roomWithDeduction);

    // Click restore
    fireEvent.click(screen.getByLabelText(`restore-opening-${doorOpening.id}`));

    // Check Surface deduction restored to 1.800, net back to 11.700
    await waitFor(() => {
      const surfaceItem = screen.getByLabelText(`surface-item-${wallSurface.id}`);
      expect(within(surfaceItem).getAllByText(/1\.800 m²/)).toHaveLength(2);
      expect(within(surfaceItem).getByText(/11\.700 m²/)).toBeInTheDocument();
    });

    // Check Room aggregate restored
    const roomSummaryAfterRestore = screen.getByLabelText('room-calculations-summary');
    expect(within(roomSummaryAfterRestore).getByText('1.800 m²')).toBeInTheDocument();
    expect(within(roomSummaryAfterRestore).getByText('46.800 m²')).toBeInTheDocument();
  });

  it('reconciles dependent state on opening update', async () => {
    const wallWithDeduction: SurfaceType = {
      ...wallSurface,
      deduction_area: '1.800',
      net_area: '11.700',
    };
    const roomWithDeduction: RoomType = {
      ...measuredRoom,
      calculations: {
        ...measuredRoom.calculations!,
        total_deduction_area: '1.800',
        net_wall_area: '46.800',
      },
    };

    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [roomWithDeduction], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(roomWithDeduction);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallWithDeduction], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [doorOpening], total: 1 });

    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${measuredRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${measuredRoom.id}`));

    await waitFor(() => expect(screen.getByLabelText(`toggle-openings-${wallSurface.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`toggle-openings-${wallSurface.id}`));

    await waitFor(() => expect(screen.getByLabelText(`edit-opening-${doorOpening.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`edit-opening-${doorOpening.id}`));

    // Prepare mocks for updated opening (width 1.0 -> area 2.000)
    const updatedOpening: OpeningType = {
      ...doorOpening,
      width: 1.0,
      single_area: '2.000',
      total_area: '2.000',
    };
    const updatedSurface: SurfaceType = {
      ...wallSurface,
      deduction_area: '2.000',
      net_area: '11.500',
    };
    const updatedRoom: RoomType = {
      ...measuredRoom,
      calculations: {
        ...measuredRoom.calculations!,
        total_deduction_area: '2.000',
        net_wall_area: '46.600',
      },
    };

    vi.mocked(openingsApi.updateOpening).mockResolvedValue(updatedOpening);
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [updatedOpening], total: 1 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [updatedSurface], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(updatedRoom);

    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '1.0' } });
    fireEvent.submit(screen.getByLabelText(`opening-form-${wallSurface.id}`));

    // Verify Opening updated
    await waitFor(() => expect(screen.getByText(/1\.000 × 2\.000 m/)).toBeInTheDocument());

    // Verify Surface deduction and net refreshed
    const surfaceItem = screen.getByLabelText(`surface-item-${wallSurface.id}`);
    expect(within(surfaceItem).getAllByText(/2\.000 m²/)).toHaveLength(2);
    expect(within(surfaceItem).getByText(/11\.500 m²/)).toBeInTheDocument();

    // Verify Room deductions and net wall area refreshed
    const roomSummary = screen.getByLabelText('room-calculations-summary');
    expect(within(roomSummary).getByText('2.000 m²')).toBeInTheDocument();
    expect(within(roomSummary).getByText('46.600 m²')).toBeInTheDocument();
  });

  it('refreshes room measurements when editing room dimensions in-place', async () => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [measuredRoom], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(measuredRoom);
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${measuredRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${measuredRoom.id}`));

    await waitFor(() => expect(screen.getByLabelText('edit-room-detail')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('edit-room-detail'));

    expect(screen.getByLabelText('room-edit-form')).toBeInTheDocument();

    const expandedRoom: RoomType = {
      ...measuredRoom,
      length: 6,
      width: 4,
      height: 2.7,
      calculations: {
        floor_area: '24.000',
        ceiling_area: '24.000',
        perimeter: '20.000',
        total_wall_area: '54.000',
        wall_area_length: '32.400',
        wall_area_width: '21.600',
        total_deduction_area: null,
        net_wall_area: null,
      },
    };

    vi.mocked(roomsApi.updateRoom).mockResolvedValue(expandedRoom);
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(expandedRoom);

    fireEvent.change(screen.getByLabelText('room-edit-length'), { target: { value: '6' } });
    fireEvent.submit(screen.getByLabelText('room-edit-form'));

    await waitFor(() => expect(screen.queryByLabelText('room-edit-form')).not.toBeInTheDocument());

    const summary = screen.getByLabelText('room-calculations-summary');
    expect(within(summary).getByText(/6\.000 × 4\.000 × 2\.700 m/)).toBeInTheDocument();
    expect(within(summary).getAllByText('24.000 m²')).toHaveLength(2); // floor & ceiling
    expect(within(summary).getByText('20.000 m')).toBeInTheDocument();
    expect(within(summary).getAllByText('54.000 m²')).toHaveLength(2); // total wall & net wall
  });

  it('represents the canonical room scenario with multiple walls, door, and window deductions', async () => {
    const wall1: SurfaceType = {
      id: '44444444-4444-4444-4444-444444444441',
      room_id: measuredRoom.id,
      name: 'Ściana 1',
      surface_type: 'WALL',
      width: 5,
      height: 2.7,
      gross_area: '13.500',
      deduction_area: '1.800',
      net_area: '11.700',
      description: null,
      is_archived: false,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    };

    const wall2: SurfaceType = {
      id: '44444444-4444-4444-4444-444444444442',
      room_id: measuredRoom.id,
      name: 'Ściana 2',
      surface_type: 'WALL',
      width: 4,
      height: 2.7,
      gross_area: '10.800',
      deduction_area: '2.100',
      net_area: '8.700',
      description: null,
      is_archived: false,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    };

    const canonicalRoom: RoomType = {
      ...measuredRoom,
      calculations: {
        floor_area: '20.000',
        ceiling_area: '20.000',
        perimeter: '18.000',
        total_wall_area: '48.600',
        wall_area_length: '27.000',
        wall_area_width: '21.600',
        total_deduction_area: '3.900',
        net_wall_area: '44.700',
      },
    };

    const door: OpeningType = {
      id: '55555555-5555-5555-5555-555555555551',
      surface_id: wall1.id,
      opening_type: 'DOOR',
      name: 'Drzwi',
      width: 0.9,
      height: 2.0,
      quantity: 1,
      single_area: '1.800',
      total_area: '1.800',
      description: null,
      is_archived: false,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    };

    const windowOpening: OpeningType = {
      id: '55555555-5555-5555-5555-555555555552',
      surface_id: wall2.id,
      opening_type: 'WINDOW',
      name: 'Okno',
      width: 1.5,
      height: 1.4,
      quantity: 1,
      single_area: '2.100',
      total_area: '2.100',
      description: null,
      is_archived: false,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    };

    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [canonicalRoom], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(canonicalRoom);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wall1, wall2], total: 2 });
    vi.mocked(openingsApi.fetchOpenings).mockImplementation(async (_p, _r, surfaceId) => {
      if (surfaceId === wall1.id) return { items: [door], total: 1 };
      if (surfaceId === wall2.id) return { items: [windowOpening], total: 1 };
      return { items: [], total: 0 };
    });

    renderWorkspace();

    // Open project and room
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${canonicalRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${canonicalRoom.id}`));

    // 1. Verify Room aggregate calculations:
    const roomSummary = await screen.findByLabelText('room-calculations-summary');
    expect(within(roomSummary).getByText(/5\.000 × 4\.000 × 2\.700 m/)).toBeInTheDocument();
    expect(within(roomSummary).getAllByText('20.000 m²')).toHaveLength(2); // floor & ceiling
    expect(within(roomSummary).getByText('18.000 m')).toBeInTheDocument(); // perimeter
    expect(within(roomSummary).getByText('48.600 m²')).toBeInTheDocument(); // total gross wall area
    expect(within(roomSummary).getByText('3.900 m²')).toBeInTheDocument(); // total deduction area
    expect(within(roomSummary).getByText('44.700 m²')).toBeInTheDocument(); // net wall area

    // 2. Verify Wall 1:
    const wall1Item = screen.getByLabelText(`surface-item-${wall1.id}`);
    expect(within(wall1Item).getByText('Ściana 1')).toBeInTheDocument();
    expect(within(wall1Item).getByText(/5\.000 × 2\.700 m/)).toBeInTheDocument();
    expect(within(wall1Item).getByText(/13\.500 m²/)).toBeInTheDocument();
    expect(within(wall1Item).getByText(/1\.800 m²/)).toBeInTheDocument();
    expect(within(wall1Item).getByText(/11\.700 m²/)).toBeInTheDocument();

    // 3. Verify Wall 2:
    const wall2Item = screen.getByLabelText(`surface-item-${wall2.id}`);
    expect(within(wall2Item).getByText('Ściana 2')).toBeInTheDocument();
    expect(within(wall2Item).getByText(/4\.000 × 2\.700 m/)).toBeInTheDocument();
    expect(within(wall2Item).getByText(/10\.800 m²/)).toBeInTheDocument();
    expect(within(wall2Item).getByText(/2\.100 m²/)).toBeInTheDocument();
    expect(within(wall2Item).getByText(/8\.700 m²/)).toBeInTheDocument();

    // 4. Open Wall 1 openings and verify Door:
    fireEvent.click(screen.getByLabelText(`toggle-openings-${wall1.id}`));
    await waitFor(() => expect(within(wall1Item).getByText('Drzwi')).toBeInTheDocument());
    expect(within(wall1Item).getByText(/0\.900 × 2\.000 m/)).toBeInTheDocument();

    // 5. Open Wall 2 openings and verify Window:
    fireEvent.click(screen.getByLabelText(`toggle-openings-${wall2.id}`));
    await waitFor(() => expect(within(wall2Item).getByText('Okno')).toBeInTheDocument());
    expect(within(wall2Item).getByText(/1\.500 × 1\.400 m/)).toBeInTheDocument();
  });

  it('opens room edit form when clicking measure-room-action in unmeasured notice', async () => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [room], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(room);
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${room.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${room.id}`));

    const unmeasuredNotice = await screen.findByLabelText('room-unmeasured-notice');
    expect(unmeasuredNotice).toBeInTheDocument();
    const measureBtn = screen.getByLabelText('measure-room-action');
    expect(measureBtn).toBeInTheDocument();

    fireEvent.click(measureBtn);
    expect(screen.getByLabelText('room-edit-form')).toBeInTheDocument();
    expect(screen.getByLabelText('room-edit-length')).toHaveAttribute('inputMode', 'decimal');
    expect(screen.getByLabelText('room-edit-width')).toHaveAttribute('inputMode', 'decimal');
    expect(screen.getByLabelText('room-edit-height')).toHaveAttribute('inputMode', 'decimal');
  });

  it('generates 4 walls from room dimensions inside the room detail (Stage 5D.1A)', async () => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [measuredRoom], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(measuredRoom);
    vi.mocked(surfacesApi.generateWalls).mockResolvedValue({ items: [], total: 0 });
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${measuredRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${measuredRoom.id}`));

    await waitFor(() => expect(screen.getByLabelText('generate-walls')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('generate-walls'));

    await waitFor(() => {
      expect(surfacesApi.generateWalls).toHaveBeenCalledWith(project.id, measuredRoom.id);
    });
  });

  it('shows wall_count and unavailable floor/ceiling for a custom irregular room (Stage 5D.1A)', async () => {
    const customRoom: RoomType = {
      ...room,
      name: 'Salon ze skosami',
      description: 'Poddasze',
      calculations: {
        floor_area: null,
        ceiling_area: null,
        wall_area_length: null,
        wall_area_width: null,
        perimeter: '21.000',
        total_wall_area: '59.050',
        total_deduction_area: '1.800',
        net_wall_area: '57.250',
        wall_count: 5,
      },
    };
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [customRoom], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(customRoom);
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${customRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${customRoom.id}`));

    const summary = await screen.findByLabelText('room-calculations-summary');
    expect(within(summary).getAllByText(/—/)).toHaveLength(2); // floor & ceiling unavailable
    expect(within(summary).getByText('21.000 m')).toBeInTheDocument(); // perimeter from wall widths
    expect(within(summary).getByText('59.050 m²')).toBeInTheDocument(); // total wall gross
    expect(within(summary).getByText('1.800 m²')).toBeInTheDocument(); // deductions
    expect(within(summary).getByText('57.250 m²')).toBeInTheDocument(); // net wall area
    expect(within(summary).getByText('Ściany:')).toBeInTheDocument(); // wall_count label
    expect(within(summary).getByText('5')).toBeInTheDocument(); // wall_count value
  });

  it('prefills new custom walls with the room default height captured at creation (Stage 5D.1A.1)', async () => {
    // A custom-shape room created in 5D.1A.1 stores its default wall height as Room.height
    // and has no L/W, so the shape is inferred as CUSTOM and wall entry is direct.
    const customRoom: RoomType = {
      id: '88888888-8888-8888-8888-888888888888',
      project_id: project.id,
      name: 'Poddasze',
      description: null,
      height: 2.7,
      is_archived: false,
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    };
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [customRoom], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(customRoom);
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${customRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${customRoom.id}`));

    const customEntry = await screen.findByLabelText('custom-wall-entry');
    expect(within(customEntry).getByLabelText('custom-wall-height')).toHaveValue('2.700 m');
    expect(screen.queryByLabelText('mode-custom')).not.toBeInTheDocument();
  });

  it('RECTANGLE room 4.900 × 5.000 × 2.700 with zero walls is measured: summary, no enter-dimensions CTA, generate 4 walls (Stage 7D.1 D3)', async () => {
    const rectRoom: RoomType = {
      id: '99999999-9999-9999-9999-999999999999',
      project_id: project.id,
      name: 'Nowa łazienka',
      description: null,
      length: 4.9,
      width: 5.0,
      height: 2.7,
      is_archived: false,
      created_at: '2026-09-12T00:00:00Z',
      updated_at: '2026-09-12T00:00:00Z',
      calculations: {
        floor_area: '24.500',
        ceiling_area: '24.500',
        perimeter: '19.800',
        total_wall_area: '53.460',
        wall_area_length: '26.460',
        wall_area_width: '27.000',
        total_deduction_area: null,
        net_wall_area: null,
        wall_count: 0,
      },
    };

    vi.mocked(roomsApi.createRoom).mockResolvedValue(rectRoom);
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(rectRoom);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });

    // Backend list: empty before the room is created, then the new room appears.
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [], total: 0 });
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));

    // Create the RECTANGLE room exactly as the owner did: 4.900 × 5.000 × 2.700, zero walls.
    await waitFor(() => expect(screen.getByLabelText('add-room')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-room'));
    fireEvent.change(screen.getByLabelText('room-name'), { target: { value: 'Nowa łazienka' } });
    fireEvent.change(screen.getByLabelText('room-length'), { target: { value: '4.9' } });
    fireEvent.change(screen.getByLabelText('room-width'), { target: { value: '5.0' } });
    fireEvent.change(screen.getByLabelText('room-height'), { target: { value: '2.7' } });
    fireEvent.submit(screen.getByLabelText('room-form'));

    // New room appears in the list; open it.
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [rectRoom], total: 1 });
    await waitFor(() => expect(screen.getByLabelText(`open-room-${rectRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${rectRoom.id}`));

    // Measured state: summary with dims + floor/ceiling/perimeter, never the unmeasured notice.
    const summary = await screen.findByLabelText('room-calculations-summary');
    expect(screen.queryByLabelText('room-unmeasured-notice')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('measure-room-action')).not.toBeInTheDocument();
    expect(within(summary).getByText(/4\.900 × 5\.000 × 2\.700 m/)).toBeInTheDocument();
    expect(within(summary).getAllByText('24.500 m²')).toHaveLength(2); // floor & ceiling
    expect(within(summary).getByText('19.800 m')).toBeInTheDocument(); // perimeter
    // net falls back to total for zero-deduction rooms, so 53.460 appears twice (net & gross).
    expect(within(summary).getAllByText('53.460 m²')).toHaveLength(2); // wall gross (0 walls)

    // Wall generation is available for the dimensioned RECTANGLE room.
    await waitFor(() => expect(screen.getByLabelText('generate-walls')).toBeInTheDocument());

    // Generation produces exactly 4 walls.
    const generatedWalls: SurfaceType[] = [0, 1, 2, 3].map((i) => ({
      ...wallSurface,
      id: `aaaaaaa1-aaaa-aaaa-aaaa-aaaaaaa${i}`, // aaaaaaa1-...-aaaaaaa3
      name: `Ściana ${i + 1}`,
    }));
    vi.mocked(surfacesApi.generateWalls).mockResolvedValue({ items: generatedWalls, total: 4 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: generatedWalls, total: 4 });

    fireEvent.click(screen.getByLabelText('generate-walls'));

    await waitFor(() =>
      expect(surfacesApi.generateWalls).toHaveBeenCalledWith(project.id, rectRoom.id),
    );
    await waitFor(() => expect(screen.getAllByLabelText(/surface-item-/)).toHaveLength(4));
  });

  it('regards a dimensioned RECTANGLE room as measured even when calculations payload is absent (Stage 7D.1 D3)', async () => {
    // The backend always serializes calculations for L×W×H rooms, but the measured state must
    // not depend on that object: domain semantics say RECTANGLE is measured iff L && W && H.
    const rectRoomWithoutCalculations: RoomType = {
      id: '99999999-9999-9999-9999-999999999999',
      project_id: project.id,
      name: 'Kuchnia',
      description: null,
      length: 4.9,
      width: 5.0,
      height: 2.7,
      is_archived: false,
      created_at: '2026-09-12T00:00:00Z',
      updated_at: '2026-09-12T00:00:00Z',
    };
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [rectRoomWithoutCalculations], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(rectRoomWithoutCalculations);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${rectRoomWithoutCalculations.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${rectRoomWithoutCalculations.id}`));

    // The unmeasured notice and its "+ Enter dimensions" CTA must never appear for this room.
    await screen.findByLabelText('room-calculations-summary');
    expect(screen.queryByLabelText('room-unmeasured-notice')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('measure-room-action')).not.toBeInTheDocument();
    // Generate-walls stays available.
    expect(screen.getByLabelText('generate-walls')).toBeInTheDocument();
  });
});

describe('Room measurement CTA routing (Stage 5D.1A.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [project], total: 1 });
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [client], total: 1 });
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [room], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(room);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
  });

  // A CUSTOM-shape room created in 5D.1A.1: default wall height in Room.height, no L/W.
  const customMeasurementRoom: RoomType = {
    id: '77777777-7777-7777-7777-777777777777',
    project_id: project.id,
    name: 'Poddasze',
    description: 'Skosy',
    height: 2.7,
    is_archived: false,
    created_at: '2026-09-09T10:00:00Z',
    updated_at: '2026-09-09T10:00:00Z',
  };

  const openRoomView = async (roomToOpen: RoomType, roomsList: RoomType[]) => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: roomsList, total: roomsList.length });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(roomToOpen);
    renderWorkspace();
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${roomToOpen.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${roomToOpen.id}`));
  };

  it('RECTANGLE room CTA opens the L/W/H room editor', async () => {
    await openRoomView(room, [room]);
    await screen.findByLabelText('room-unmeasured-notice');
    const measureBtn = screen.getByLabelText('measure-room-action');
    expect(measureBtn).toHaveTextContent('Wprowadź wymiary');

    fireEvent.click(measureBtn);
    expect(screen.getByLabelText('room-edit-form')).toBeInTheDocument();
    expect(screen.getByLabelText('room-edit-length')).toBeInTheDocument();
    expect(screen.getByLabelText('room-edit-width')).toBeInTheDocument();
    expect(screen.getByLabelText('room-edit-height')).toBeInTheDocument();
  });

  it('CUSTOM room CTA launches sequential wall entry and never shows L/W', async () => {
    await openRoomView(customMeasurementRoom, [customMeasurementRoom]);
    await screen.findByLabelText('room-unmeasured-notice');
    const measureBtn = screen.getByLabelText('measure-room-action');
    expect(measureBtn).toHaveTextContent('Rozpocznij pomiar ścian');

    fireEvent.click(measureBtn);
    // The rectangular Room editor must never appear; Room.length/width stay null.
    expect(screen.queryByLabelText('room-edit-form')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('room-edit-length')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('room-edit-width')).not.toBeInTheDocument();
    // Sequential wall entry is immediately active with focus on Wall 1 length.
    const entry = await screen.findByLabelText('custom-wall-entry');
    expect(within(entry).getByLabelText('custom-wall-width')).toHaveFocus();
  });

  it('CUSTOM room defaults to wall entry on open using Room.height as wall height', async () => {
    await openRoomView(customMeasurementRoom, [customMeasurementRoom]);
    const entry = await screen.findByLabelText('custom-wall-entry');
    expect(within(entry).getByLabelText('custom-wall-height')).toHaveValue('2.700 m');
  });

  it('preserves CUSTOM mode across navigation/reload via per-room storage', async () => {
    // Seed the same storage a browser reload would leave behind, even for a room whose
    // inferred shape alone would be RECTANGLE — storage is the source of truth.
    localStorage.setItem(`plan-estimate:room-measurement-mode:${room.id}`, 'CUSTOM');
    await openRoomView(room, [room]);

    expect(await screen.findByLabelText('custom-wall-entry')).toBeInTheDocument();

    // Navigate away and back — mode must be re-read from storage, not reset to default.
    fireEvent.click(screen.getByLabelText('back-to-rooms'));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${room.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${room.id}`));
    expect(await screen.findByLabelText('custom-wall-entry')).toBeInTheDocument();
  });

  it('does not leak CUSTOM mode between rooms', async () => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [customMeasurementRoom, room], total: 2 });
    vi.mocked(roomsApi.fetchRoom).mockImplementation(async (_projId, id) =>
      id === customMeasurementRoom.id ? customMeasurementRoom : room,
    );
    renderWorkspace();

    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${customMeasurementRoom.id}`)).toBeInTheDocument());

    // Custom room enters wall entry directly.
    fireEvent.click(screen.getByLabelText(`open-room-${customMeasurementRoom.id}`));
    expect(await screen.findByLabelText('custom-wall-entry')).toBeInTheDocument();

    // Switching to the rectangle room must not inherit custom mode.
    fireEvent.click(screen.getByLabelText('back-to-rooms'));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${room.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${room.id}`));
    await screen.findByLabelText('room-unmeasured-notice');
    expect(screen.queryByLabelText('custom-wall-entry')).not.toBeInTheDocument();
    expect(screen.getByLabelText('measure-room-action')).toHaveTextContent('Wprowadź wymiary');
  });
});

describe('Inspection entry points and navigation (Stage 6C)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [project], total: 1 });
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [client], total: 1 });
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [measuredRoom], total: 1 });
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue(measuredRoom);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wallSurface], total: 1 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(checklistsApi.fetchChecklistTemplates).mockResolvedValue({
      items: [concreteTemplate],
      total: 1,
    });
    vi.mocked(checklistsApi.fetchChecklistTemplate).mockResolvedValue(concreteTemplate);
    vi.mocked(inspectionsApi.fetchInspections).mockResolvedValue({ items: [inspection], total: 1 });
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(inspectionsApi.createInspection).mockResolvedValue(inspection);
  });

  const openRoomView = async () => {
    renderWorkspace();
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    await waitFor(() => expect(screen.getByLabelText(`open-room-${measuredRoom.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-room-${measuredRoom.id}`));
    await screen.findByLabelText('room-inspection-entry');
  };

  it('exposes room, floor, ceiling, and wall inspection entry points (ENTRY)', async () => {
    await openRoomView();
    expect(screen.getByLabelText('inspect-room')).toBeInTheDocument();
    expect(screen.getByLabelText('inspect-floor')).toBeInTheDocument();
    expect(screen.getByLabelText('inspect-ceiling')).toBeInTheDocument();
    expect(screen.getByLabelText(`inspect-surface-${wallSurface.id}`)).toBeInTheDocument();
  });

  it('opens a room-level inspection list filtered to room inspections (ENTRY)', async () => {
    await openRoomView();
    fireEvent.click(screen.getByLabelText('inspect-room'));
    await screen.findByText('Badanie pomieszczenia');
    expect(await screen.findByText('Beton')).toBeInTheDocument();
  });

  it('opens a wall-targeted inspection list from the wall card (ENTRY)', async () => {
    await openRoomView();
    fireEvent.click(screen.getByLabelText(`inspect-surface-${wallSurface.id}`));
    expect(await screen.findByText('Ściana północna')).toBeInTheDocument();
  });

  it('starts a new wall inspection and creates a DRAFT via the flow (ENTRY)', async () => {
    await openRoomView();
    fireEvent.click(screen.getByLabelText(`inspect-surface-${wallSurface.id}`));
    fireEvent.click(await screen.findByLabelText('Nowe badanie'));
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await waitFor(() =>
      expect(inspectionsApi.createInspection).toHaveBeenCalledWith(
        project.id,
        measuredRoom.id,
        expect.objectContaining({
          surface_id: wallSurface.id,
          substrate: 'CONCRETE',
          quality_target: null,
        }),
      ),
    );
  });

  it('respects BackButton hierarchy flow -> list -> room -> rooms (NAVIGATION)', async () => {
    let clickHandler: (() => void) | undefined;
    const backButton = {
      isVisible: false,
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn((cb: () => void) => {
        clickHandler = cb;
      }),
      offClick: vi.fn(),
    };
    window.Telegram = {
      WebApp: {
        initData: '',
        initDataUnsafe: {},
        version: '8.0',
        platform: 'web',
        colorScheme: 'light',
        themeParams: {},
        isExpanded: false,
        viewportHeight: 800,
        viewportStableHeight: 800,
        ready: vi.fn(),
        expand: vi.fn(),
        close: vi.fn(),
        BackButton: backButton,
      },
    };

    await openRoomView();

    // Open the room-level inspection list
    fireEvent.click(screen.getByLabelText('inspect-room'));
    await screen.findByText('Badanie pomieszczenia');
    // Start a new inspection -> flow (substrate step)
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await screen.findByLabelText('Beton');

    // Back from flow -> inspection list
    act(() => {
      clickHandler?.();
    });
    expect(await screen.findByText('Badanie pomieszczenia')).toBeInTheDocument();

    // Back from list -> room detail
    act(() => {
      clickHandler?.();
    });
    expect(await screen.findByLabelText('room-inspection-entry')).toBeInTheDocument();

    // Back from room -> rooms list
    act(() => {
      clickHandler?.();
    });
    expect(await screen.findByLabelText(`open-room-${measuredRoom.id}`)).toBeInTheDocument();
  });
});
