import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as areaSegmentsApi from './api/areaSegments';
import * as clientsApi from './api/clients';
import * as estimatesApi from './api/estimates';
import * as openingsApi from './api/openings';
import * as projectsApi from './api/projects';
import * as roomsApi from './api/rooms';
import * as surfacesApi from './api/surfaces';
import * as photosApi from './api/photos';
import { ProjectWorkspace } from './components/ProjectWorkspace';
import { I18nProvider } from './hooks/useI18n';
import { resetPhotoStorage } from './hooks/usePhotoStorage';
import { resetPhotoUploadQueue } from './hooks/usePhotoUploadQueue';
import { OpeningType } from './types/opening';
import { PhotoCounts, PhotoUploadResponse } from './types/photo';
import { ProjectType } from './types/project';
import { RoomType } from './types/room';
import { SurfaceType } from './types/surface';
import { detailFor, listPage, makeItem, storageStatus } from './test/photoFixtures';

// Stage 14E.5 — photo entry points wired into the object, room, surface and opening cards.

vi.mock('./api/clients', () => ({ fetchClients: vi.fn() }));
vi.mock('./api/estimates', () => ({ listEstimates: vi.fn(), generateEstimate: vi.fn(), getEstimate: vi.fn() }));
vi.mock('./api/projects', () => ({
  fetchProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  archiveProject: vi.fn(),
  restoreProject: vi.fn(),
}));
vi.mock('./api/rooms', () => ({
  fetchProjectSummary: vi.fn(async () => ({
    room_count: 0, floor_area: null, ceiling_area: null, total_wall_area: null,
    total_deduction_area: null, net_wall_area: null, reveal_total_length: null,
    reveal_total_area: null, opening_groups: [],
  })),
  fetchRooms: vi.fn(),
  fetchRoom: vi.fn(),
  createRoom: vi.fn(),
  updateRoom: vi.fn(),
  archiveRoom: vi.fn(),
  restoreRoom: vi.fn(),
}));
vi.mock('./api/areaSegments', () => ({
  fetchAreaSegments: vi.fn(async () => ({ items: [], total: 0 })),
  createAreaSegment: vi.fn(),
  updateAreaSegment: vi.fn(),
  archiveAreaSegment: vi.fn(),
  restoreAreaSegment: vi.fn(),
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
vi.mock('./api/checklists', () => ({ fetchChecklistTemplates: vi.fn(async () => ({ items: [], total: 0 })), fetchChecklistTemplate: vi.fn() }));
vi.mock('./api/inspections', () => ({
  fetchInspections: vi.fn(async () => ({ items: [], total: 0 })),
  createInspection: vi.fn(),
  fetchInspection: vi.fn(),
  updateInspection: vi.fn(),
  fetchInspectionAnswers: vi.fn(),
  putInspectionAnswers: vi.fn(),
  completeInspection: vi.fn(),
  reopenInspection: vi.fn(),
  archiveInspection: vi.fn(),
  restoreInspection: vi.fn(),
  fetchInspectionFindings: vi.fn(async () => ({ items: [], total: 0 })),
}));
vi.mock('./api/photos', async () => {
  const actual = await vi.importActual<typeof import('./api/photos')>('./api/photos');
  return {
    ...actual,
    fetchPhotoCounts: vi.fn(),
    fetchPhotos: vi.fn(),
    fetchPhoto: vi.fn(),
    fetchPhotoStorage: vi.fn(),
    uploadPhoto: vi.fn(),
    patchPhotoAttachment: vi.fn(),
    archivePhotoAttachment: vi.fn(),
    restorePhotoAttachment: vi.fn(),
  };
});

const project: ProjectType = {
  id: '11111111-1111-4111-8111-111111111111',
  owner_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  client_id: null,
  name: 'Mieszkanie Mokotów',
  address: 'ul. Dobra 10',
  city: 'Warszawa',
  postal_code: '00-001',
  description: null,
  status: 'PLANNING',
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const salon: RoomType = {
  id: '33333333-3333-4333-8333-333333333333',
  project_id: project.id,
  name: 'Salon',
  description: null,
  length: 5, width: 4, height: 2.7,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};
const kuchnia: RoomType = { ...salon, id: '33333333-3333-4333-8333-333333333334', name: 'Kuchnia' };

const wall: SurfaceType = {
  id: '44444444-4444-4444-8444-444444444444',
  room_id: salon.id,
  name: 'Ściana 1',
  surface_type: 'WALL',
  width: 5, height: 2.7,
  gross_area: '13.500', deduction_area: null, net_area: '13.500',
  description: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const door: OpeningType = {
  id: '55555555-5555-4555-8555-555555555555',
  surface_id: wall.id,
  opening_type: 'DOOR',
  name: 'balkonowe',
  width: 0.9, height: 2.0, quantity: 1,
  single_area: '1.800', total_area: '1.800',
  description: null,
  reveal_enabled: false, reveal_depth: null,
  reveal_left: true, reveal_right: true, reveal_top: true, reveal_bottom: false,
  reveal_single_length: null, reveal_single_area: null, reveal_total_length: null, reveal_total_area: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const COUNTS: PhotoCounts = {
  project: 1,
  rooms: { [salon.id]: 2 },
  surfaces: { [wall.id]: 3 },
  openings: { [door.id]: 1 },
};

function renderWorkspace() {
  return render(
    <I18nProvider>
      <ProjectWorkspace />
    </I18nProvider>,
  );
}

async function openProject() {
  await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
  fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
  await screen.findByLabelText('project-photos');
}

async function openSalon() {
  await openProject();
  fireEvent.click(await screen.findByLabelText(`open-room-${salon.id}`));
  await screen.findByLabelText(`surface-item-${wall.id}`);
}

const lastListParams = () => {
  const calls = vi.mocked(photosApi.fetchPhotos).mock.calls;
  return calls[calls.length - 1]?.[1];
};

let backClick: (() => void) | undefined;
let uploads: Array<{ resolve: (r: PhotoUploadResponse) => void }>;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  resetPhotoStorage();
  resetPhotoUploadQueue();
  uploads = [];
  backClick = undefined;
  vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [project], total: 1 });
  vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(estimatesApi.listEstimates).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [salon, kuchnia], total: 2 });
  vi.mocked(roomsApi.fetchRoom).mockResolvedValue(salon);
  vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wall], total: 1 });
  vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [door], total: 1 });
  vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(photosApi.fetchPhotoCounts).mockResolvedValue(COUNTS);
  vi.mocked(photosApi.fetchPhotos).mockResolvedValue(listPage([]));
  vi.mocked(photosApi.fetchPhotoStorage).mockResolvedValue(storageStatus());
  vi.mocked(photosApi.uploadPhoto).mockImplementation(
    () => new Promise<PhotoUploadResponse>((resolve) => uploads.push({ resolve })),
  );
  window.Telegram = {
    WebApp: {
      initData: '', initDataUnsafe: {}, version: '8.0', platform: 'web', colorScheme: 'light', themeParams: {},
      isExpanded: false, viewportHeight: 800, viewportStableHeight: 800,
      ready: vi.fn(), expand: vi.fn(), close: vi.fn(),
      BackButton: {
        isVisible: false,
        show: vi.fn(),
        hide: vi.fn(),
        onClick: vi.fn((cb: () => void) => {
          backClick = cb;
        }),
        offClick: vi.fn(),
      },
    },
  };
});

afterEach(() => {
  delete window.Telegram;
  resetPhotoUploadQueue();
  resetPhotoStorage();
});

describe('ProjectWorkspace photos — the object card', () => {
  it('loads the counts once when the object opens, and not on the project list', async () => {
    renderWorkspace();
    await waitFor(() => expect(screen.getByText('Mieszkanie Mokotów')).toBeInTheDocument());
    expect(photosApi.fetchPhotoCounts).not.toHaveBeenCalled();
    await openProject();
    await waitFor(() => expect(photosApi.fetchPhotoCounts).toHaveBeenCalledTimes(1));
    expect(photosApi.fetchPhotoCounts).toHaveBeenCalledWith(project.id);
  });

  it('shows a card between the summary and the rooms with the total count of the whole object', async () => {
    renderWorkspace();
    await openProject();
    const card = screen.getByLabelText('project-photos');
    expect(within(card).getByRole('heading', { name: 'Zdjęcia obiektu' })).toBeInTheDocument();
    // 1 (object) + 2 (Salon) + 3 (wall) + 1 (opening) — what the project-wide list will show
    expect(await within(card).findByRole('button', { name: 'Zdjęcia: 7' })).toBeInTheDocument();
    const detail = screen.getByLabelText('project-detail');
    const rooms = await screen.findByLabelText('rooms-list');
    expect(detail.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(card.compareDocumentPosition(rooms) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('keeps the object card a fixed white surface with an explicit dark title (like project-detail)', async () => {
    renderWorkspace();
    await openProject();
    const card = screen.getByLabelText('project-photos');
    expect(card.className).toContain('bg-white');
    const title = within(card).getByRole('heading', { name: 'Zdjęcia obiektu' });
    expect(title.className).toContain('text-slate-900');
    expect(title.className).not.toContain('var(--tg-theme');
  });

  it('expands the project-wide list (no context filter), refetches counts and loads names for the paths', async () => {
    renderWorkspace();
    await openProject();
    const card = screen.getByLabelText('project-photos');
    const button = await within(card).findByRole('button', { name: 'Zdjęcia: 7' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(photosApi.fetchPhotos).not.toHaveBeenCalled(); // nothing is fetched while collapsed

    fireEvent.click(button);
    await waitFor(() => expect(photosApi.fetchPhotos).toHaveBeenCalledTimes(1));
    expect(lastListParams()).toMatchObject({ archived: false });
    expect(lastListParams()?.context).toBeUndefined();
    expect(button).toHaveAttribute('aria-expanded', 'true');
    await waitFor(() => expect(photosApi.fetchPhotoCounts).toHaveBeenCalledTimes(2)); // refetched on expand
    // surfaces and openings carry photos: the names are loaded for the paths (walls only for openings)
    await waitFor(() => expect(surfacesApi.fetchSurfaces).toHaveBeenCalled());
    await waitFor(() => expect(openingsApi.fetchOpenings).toHaveBeenCalled());
  });

  it('writes the full path of every photo in the project-wide list', async () => {
    const roomPhoto = makeItem({ attachment: { context: 'ROOM', room_id: salon.id } });
    const wallPhoto = makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } });
    const doorPhoto = makeItem({ attachment: { context: 'OPENING', room_id: null, opening_id: door.id } });
    const projectPhoto = makeItem({ attachment: { context: 'PROJECT', room_id: null } });
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(listPage([roomPhoto, wallPhoto, doorPhoto, projectPhoto]));
    renderWorkspace();
    await openProject();
    fireEvent.click(await within(screen.getByLabelText('project-photos')).findByRole('button', { name: /Zdjęcia:/ }));

    await screen.findByText(/^Salon → Ściana 1 → Drzwi \(balkonowe\) → 23\.06\.2026/);
    expect(screen.getByText(/^Salon → Ściana 1 → 23\.06\.2026/)).toBeInTheDocument();
    expect(screen.getByText(/^Salon → 23\.06\.2026/)).toBeInTheDocument();
    expect(screen.getByText(/^Obiekt → 23\.06\.2026/)).toBeInTheDocument();
  });

  it('shows a dash for a name that cannot be resolved instead of failing', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockRejectedValue(new Error('offline'));
    const wallPhoto = makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } });
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(listPage([wallPhoto]));
    renderWorkspace();
    await openProject();
    fireEvent.click(await within(screen.getByLabelText('project-photos')).findByRole('button', { name: /Zdjęcia:/ }));
    await screen.findByText(/^— → — → 23\.06\.2026/);
  });
});

describe('ProjectWorkspace photos — room, surface and opening cards', () => {
  it('puts a corner button with its own count on every room card and expands only that room', async () => {
    renderWorkspace();
    await openProject();
    const salonCard = await screen.findByLabelText(`room-item-${salon.id}`);
    const kuchniaCard = screen.getByLabelText(`room-item-${kuchnia.id}`);
    const button = await within(salonCard).findByRole('button', { name: 'Zdjęcia: 2' });
    expect(button).toHaveClass('min-h-11');
    expect(within(kuchniaCard).getByRole('button', { name: 'Zdjęcia: 0' })).toBeInTheDocument();

    vi.mocked(photosApi.fetchPhotoCounts).mockClear();
    fireEvent.click(button);
    await waitFor(() => expect(photosApi.fetchPhotos).toHaveBeenCalledTimes(1));
    expect(lastListParams()).toMatchObject({ context: 'ROOM', roomId: salon.id });
    expect(within(salonCard).getByRole('region', { name: 'Zdjęcia' })).toBeInTheDocument();
    expect(within(kuchniaCard).queryByRole('region', { name: 'Zdjęcia' })).toBeNull();

    fireEvent.click(button); // a second tap collapses
    expect(within(salonCard).queryByRole('region', { name: 'Zdjęcia' })).toBeNull();
  });

  it('keeps the existing room actions and the room name intact', async () => {
    renderWorkspace();
    await openProject();
    const card = await screen.findByLabelText(`room-item-${salon.id}`);
    expect(within(card).getByText('Salon')).toBeInTheDocument();
    expect(within(card).getByLabelText(`open-room-${salon.id}`)).toBeInTheDocument();
    expect(within(card).getByLabelText(`edit-room-${salon.id}`)).toBeInTheDocument();
    expect(within(card).getByLabelText(`archive-room-${salon.id}`)).toBeInTheDocument();
  });

  it('a room photo carries the room name in its caption line', async () => {
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(
      listPage([makeItem({ attachment: { context: 'ROOM', room_id: salon.id } })]),
    );
    renderWorkspace();
    await openProject();
    const card = await screen.findByLabelText(`room-item-${salon.id}`);
    fireEvent.click(await within(card).findByRole('button', { name: /Zdjęcia: 2/ }));
    await within(card).findByText('Salon → 23.06.2026 (10:15) · zrobione w aplikacji');
  });

  it('puts the surface button on its own right-aligned line under Opcje, and uses "room → surface" as the path', async () => {
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(
      listPage([makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } })]),
    );
    renderWorkspace();
    await openSalon();
    const card = screen.getByLabelText(`surface-item-${wall.id}`);
    const button = within(card).getByRole('button', { name: 'Zdjęcia: 3' });
    expect(button.parentElement).toHaveClass('flex', 'justify-end');
    const options = within(card).getByLabelText(`options-toggle-${wall.id}`);
    expect(options.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(button);
    await waitFor(() => expect(lastListParams()).toMatchObject({ context: 'SURFACE', surfaceId: wall.id }));
    await within(card).findByText('Salon → Ściana 1 → 23.06.2026 (10:15) · zrobione w aplikacji');
  });

  it('an opening row has its own corner button; its path is room → surface → opening', async () => {
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(
      listPage([makeItem({ attachment: { context: 'OPENING', room_id: null, opening_id: door.id } })]),
    );
    renderWorkspace();
    await openSalon();
    fireEvent.click(screen.getByLabelText(`options-toggle-${wall.id}`));
    fireEvent.click(await screen.findByLabelText(`toggle-openings-${wall.id}`));
    const row = await screen.findByLabelText(`opening-item-${door.id}`);
    const button = within(row).getByRole('button', { name: 'Zdjęcia: 1' });
    expect(button).toHaveClass('min-h-11');
    expect(within(row).getByLabelText(`edit-opening-${door.id}`)).toBeInTheDocument();

    fireEvent.click(button);
    await waitFor(() => expect(lastListParams()).toMatchObject({ context: 'OPENING', openingId: door.id }));
    await within(row).findByText(/^Salon → Ściana 1 → Drzwi \(balkonowe\) → 23\.06\.2026/);
  });

  it('collapsing the room view and coming back keeps a section expanded (state lives in the object context)', async () => {
    renderWorkspace();
    await openProject();
    const button = await within(await screen.findByLabelText(`room-item-${salon.id}`)).findByRole('button', { name: 'Zdjęcia: 2' });
    fireEvent.click(button);
    await screen.findByRole('region', { name: 'Zdjęcia' });
    fireEvent.click(screen.getByLabelText(`open-room-${salon.id}`));
    await screen.findByLabelText(`surface-item-${wall.id}`);
    fireEvent.click(screen.getByLabelText('back-to-rooms'));
    await screen.findByLabelText(`room-item-${salon.id}`);
    expect(within(screen.getByLabelText(`room-item-${salon.id}`)).getByRole('region', { name: 'Zdjęcia' })).toBeInTheDocument();
  });

  it('a different object starts collapsed with its own counts', async () => {
    renderWorkspace();
    await openProject();
    fireEvent.click(await within(screen.getByLabelText('project-photos')).findByRole('button', { name: /Zdjęcia:/ }));
    await screen.findByRole('region', { name: 'Zdjęcia' });
    fireEvent.click(screen.getByLabelText('back-to-projects'));
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    vi.mocked(photosApi.fetchPhotoCounts).mockResolvedValue({ project: 0, rooms: {}, surfaces: {}, openings: {} });
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    const card = await screen.findByLabelText('project-photos');
    expect(await within(card).findByRole('button', { name: 'Zdjęcia: 0' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region', { name: 'Zdjęcia' })).toBeNull();
  });
});

describe('ProjectWorkspace photos — counts and uploads', () => {
  async function startRoomUpload() {
    renderWorkspace();
    await openProject();
    const card = await screen.findByLabelText(`room-item-${salon.id}`);
    const button = await within(card).findByRole('button', { name: 'Zdjęcia: 2' });
    fireEvent.click(button);
    fireEvent.change(await within(card).findByTestId('photo-input-camera'), {
      target: { files: [new File(['x'], 'c.jpg', { type: 'image/jpeg' })] },
    });
    await waitFor(() => expect(photosApi.uploadPhoto).toHaveBeenCalledTimes(1));
    return { card, button };
  }

  it('counts a finished upload exactly once, even when its section was collapsed meanwhile', async () => {
    const { card, button } = await startRoomUpload();
    expect(photosApi.uploadPhoto).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: project.id, context: 'ROOM', roomId: salon.id, source: 'CAMERA' }),
      expect.anything(),
    );
    fireEvent.click(button); // collapse while the upload is still running
    expect(within(card).queryByRole('region', { name: 'Zdjęcia' })).toBeNull();

    const item = makeItem({ attachment: { context: 'ROOM', room_id: salon.id } });
    await act(async () =>
      uploads[0].resolve({
        asset: item.asset, attachment: item.attachment, thumbnail_url: 't', display_url: 'd',
        urls_expire_at: '2099-01-01T00:00:00Z', storage: { state: 'OK' },
      }),
    );
    expect(await within(card).findByRole('button', { name: 'Zdjęcia: 3' })).toBeInTheDocument();
    // the total in the object card follows the same single correction
    expect(within(screen.getByLabelText('project-photos')).getByRole('button', { name: 'Zdjęcia: 8' })).toBeInTheDocument();
  });

  it('does not double-count when two sections of the same object are open', async () => {
    renderWorkspace();
    await openProject();
    const card = await screen.findByLabelText(`room-item-${salon.id}`);
    fireEvent.click(await within(card).findByRole('button', { name: 'Zdjęcia: 2' }));
    fireEvent.click(within(screen.getByLabelText('project-photos')).getByRole('button', { name: /Zdjęcia:/ }));
    fireEvent.change(await within(card).findByTestId('photo-input-gallery'), {
      target: { files: [new File(['x'], 'g.jpg', { type: 'image/jpeg' })] },
    });
    await waitFor(() => expect(photosApi.uploadPhoto).toHaveBeenCalledTimes(1));
    const item = makeItem({ attachment: { context: 'ROOM', room_id: salon.id } });
    await act(async () =>
      uploads[0].resolve({
        asset: item.asset, attachment: item.attachment, thumbnail_url: 't', display_url: 'd',
        urls_expire_at: '2099-01-01T00:00:00Z', storage: { state: 'OK' },
      }),
    );
    expect(await within(card).findByRole('button', { name: 'Zdjęcia: 3' })).toBeInTheDocument();
  });

  it('shows no upload buttons in an expanded section while uploads are switched off (D5)', async () => {
    vi.mocked(photosApi.fetchPhotoStorage).mockResolvedValue(storageStatus({ uploads_enabled: false }));
    renderWorkspace();
    await openProject();
    const card = await screen.findByLabelText(`room-item-${salon.id}`);
    fireEvent.click(await within(card).findByRole('button', { name: 'Zdjęcia: 2' }));
    await within(card).findByText(/Dodawanie zdjęć jest obecnie wyłączone/);
    expect(within(card).queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
  });
});

describe('ProjectWorkspace photos — Telegram BackButton', () => {
  async function openViewerInSalonCard() {
    const item = makeItem({ attachment: { context: 'ROOM', room_id: salon.id } });
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(listPage([item]));
    vi.mocked(photosApi.fetchPhoto).mockResolvedValue(detailFor(item));
    renderWorkspace();
    await openProject();
    const card = await screen.findByLabelText(`room-item-${salon.id}`);
    fireEvent.click(await within(card).findByRole('button', { name: 'Zdjęcia: 2' }));
    fireEvent.click(await within(card).findByRole('button', { name: /23\.06\.2026/ }));
    await screen.findByRole('dialog');
  }

  it('Back closes the open viewer first and does not navigate; the next Back leaves the object', async () => {
    await openViewerInSalonCard();
    act(() => backClick?.());
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // still inside the object: the rooms are on screen and the section is still open
    expect(screen.getByLabelText(`room-item-${salon.id}`)).toBeInTheDocument();
    expect(screen.getByLabelText('project-photos')).toBeInTheDocument();

    act(() => backClick?.());
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    expect(screen.queryByLabelText('project-photos')).toBeNull();
  });

  it('Back inside the viewer saves an unsaved caption before it closes', async () => {
    await openViewerInSalonCard();
    const updated = makeItem().attachment;
    vi.mocked(photosApi.patchPhotoAttachment).mockResolvedValue({ ...updated, caption: 'szkic' });
    fireEvent.change(screen.getByLabelText('Opis'), { target: { value: 'szkic' } });
    act(() => backClick?.());
    await waitFor(() => expect(photosApi.patchPhotoAttachment).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('with no viewer open Back behaves exactly as before (room → rooms → objects)', async () => {
    renderWorkspace();
    await openSalon();
    act(() => backClick?.());
    await waitFor(() => expect(screen.getByLabelText(`room-item-${salon.id}`)).toBeInTheDocument());
    act(() => backClick?.());
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
  });
});

describe('ProjectWorkspace photos — locales', () => {
  it('speaks Russian in the card, the button and the section', async () => {
    localStorage.setItem('locale', 'ru');
    renderWorkspace();
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    const card = await screen.findByLabelText('project-photos');
    expect(within(card).getByRole('heading', { name: 'Фото объекта' })).toBeInTheDocument();
    const button = await within(card).findByRole('button', { name: 'Фото: 7' });
    fireEvent.click(button);
    expect(await screen.findByRole('button', { name: 'Сделать фото' })).toBeInTheDocument();
  });
});
