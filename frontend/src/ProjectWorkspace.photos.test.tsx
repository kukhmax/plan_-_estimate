import { jpegFile, jpegWithExif } from './test/jpegFixtures';
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

const floorSurface: SurfaceType = { ...wall, id: '44444444-4444-4444-8444-444444444445', name: 'Podłoga', surface_type: 'FLOOR', width: null, height: null };
const ceilingSurface: SurfaceType = { ...wall, id: '44444444-4444-4444-8444-444444444446', name: 'Sufit', surface_type: 'CEILING', width: null, height: null };

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
  room_totals: { [salon.id]: 2 + 3 + 1 }, // the room's own, the wall's and the wall's opening's
  inspections: {}, findings: {}, lineages: {}, questions: {},
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
const countButton = (scope: HTMLElement, count: number | RegExp) =>
  within(scope).findByRole('button', { name: typeof count === 'number' ? `Zdjęcia: ${count}` : count });

let backClick: (() => void) | undefined;
let uploads: Array<{ resolve: (r: PhotoUploadResponse) => void }>;

function uploadResponse(item = makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } })): PhotoUploadResponse {
  return {
    asset: item.asset, attachment: item.attachment, thumbnail_url: 't', display_url: 'd',
    urls_expire_at: '2099-01-01T00:00:00Z', storage: { state: 'OK' },
  };
}

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
  vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [wall, floorSurface, ceilingSurface], total: 3 });
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

describe('ProjectWorkspace photos — the object card (view and edit everything)', () => {
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
    // 1 (object) + 2 (Salon) + 3 (wall) + 1 (opening) — what the object's list will show
    expect(await countButton(card, 7)).toBeInTheDocument();
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

  it('expands the object list: every photo (no target filter), NO way to add one, names loaded for the paths', async () => {
    renderWorkspace();
    await openProject();
    const card = screen.getByLabelText('project-photos');
    const button = await countButton(card, 7);
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(photosApi.fetchPhotos).not.toHaveBeenCalled(); // nothing is fetched while collapsed

    fireEvent.click(button);
    await waitFor(() => expect(photosApi.fetchPhotos).toHaveBeenCalledTimes(1));
    expect(lastListParams()).toMatchObject({ archived: false });
    expect(lastListParams()?.context).toBeUndefined();
    expect(lastListParams()?.inRoomId).toBeUndefined();
    expect(button).toHaveAttribute('aria-expanded', 'true');
    await screen.findByText('Brak zdjęć. Dodaj je w karcie ściany, podłogi lub sufitu.');
    expect(within(card).queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
    expect(within(card).queryByRole('button', { name: 'Z galerii' })).toBeNull();
    await waitFor(() => expect(photosApi.fetchPhotoCounts).toHaveBeenCalledTimes(2)); // refetched on expand
    await waitFor(() => expect(surfacesApi.fetchSurfaces).toHaveBeenCalled());
    await waitFor(() => expect(openingsApi.fetchOpenings).toHaveBeenCalled());
  });

  it('writes the full path of every photo in the object list', async () => {
    const roomPhoto = makeItem({ attachment: { context: 'ROOM', room_id: salon.id } });
    const wallPhoto = makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } });
    const doorPhoto = makeItem({ attachment: { context: 'OPENING', room_id: null, opening_id: door.id } });
    const projectPhoto = makeItem({ attachment: { context: 'PROJECT', room_id: null } });
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(listPage([roomPhoto, wallPhoto, doorPhoto, projectPhoto]));
    renderWorkspace();
    await openProject();
    fireEvent.click(await countButton(screen.getByLabelText('project-photos'), 7));

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
    fireEvent.click(await countButton(screen.getByLabelText('project-photos'), 7));
    await screen.findByText(/^— → — → 23\.06\.2026/);
  });

  it('an object photo can still be opened, edited and archived from the list (view / edit only)', async () => {
    const photo = makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } });
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(listPage([photo]));
    vi.mocked(photosApi.fetchPhoto).mockResolvedValue(detailFor(photo));
    renderWorkspace();
    await openProject();
    const card = screen.getByLabelText('project-photos');
    fireEvent.click(await countButton(card, 7));
    fireEvent.click(await within(card).findByRole('button', { name: /23\.06\.2026/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('Opis')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Archiwizuj' })).toBeInTheDocument();
  });
});

describe('ProjectWorkspace photos — rooms show everything in the room (view and edit)', () => {
  it('every room card has a button with the number of ALL its photos; only that room expands', async () => {
    renderWorkspace();
    await openProject();
    const salonCard = await screen.findByLabelText(`room-item-${salon.id}`);
    const kuchniaCard = screen.getByLabelText(`room-item-${kuchnia.id}`);
    const button = await countButton(salonCard, 6); // 2 own + 3 on the wall + 1 on the opening
    expect(button).toHaveClass('min-h-11');
    expect(within(kuchniaCard).getByRole('button', { name: 'Zdjęcia: 0' })).toBeInTheDocument();

    fireEvent.click(button);
    await waitFor(() => expect(photosApi.fetchPhotos).toHaveBeenCalledTimes(1));
    expect(lastListParams()).toMatchObject({ inRoomId: salon.id, archived: false });
    expect(lastListParams()?.context).toBeUndefined();
    expect(within(salonCard).getByRole('region', { name: 'Zdjęcia' })).toBeInTheDocument();
    expect(within(kuchniaCard).queryByRole('region', { name: 'Zdjęcia' })).toBeNull();

    fireEvent.click(button); // a second tap collapses
    expect(within(salonCard).queryByRole('region', { name: 'Zdjęcia' })).toBeNull();
  });

  it('a room list on the object tab offers no way to add a photo', async () => {
    renderWorkspace();
    await openProject();
    const card = await screen.findByLabelText(`room-item-${salon.id}`);
    fireEvent.click(await countButton(card, 6));
    await within(card).findByText('Brak zdjęć. Dodaj je w karcie ściany, podłogi lub sufitu.');
    expect(within(card).queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
    expect(within(card).queryByRole('button', { name: 'Z galerii' })).toBeNull();
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

  it('the photos of a room on its card carry the path down to the wall', async () => {
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(
      listPage([
        makeItem({ attachment: { context: 'ROOM', room_id: salon.id } }),
        makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } }),
      ]),
    );
    renderWorkspace();
    await openProject();
    const card = await screen.findByLabelText(`room-item-${salon.id}`);
    fireEvent.click(await countButton(card, 6));
    await within(card).findByText(/^Salon → 23\.06\.2026 \(10:15\) · zrobione w aplikacji/);
    await within(card).findByText(/^Salon → Ściana 1 → 23\.06\.2026/);
  });

  it('the room view has its own photo card with the same list (what the card on the object tab counts)', async () => {
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(
      listPage([makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } })]),
    );
    renderWorkspace();
    await openSalon();
    const card = screen.getByLabelText('room-photos');
    expect(within(card).getByRole('heading', { name: 'Zdjęcia pomieszczenia' })).toBeInTheDocument();
    const button = await countButton(card, 6);
    fireEvent.click(button);
    await waitFor(() => expect(lastListParams()).toMatchObject({ inRoomId: salon.id }));
    await within(card).findByText(/^Salon → Ściana 1 → 23\.06\.2026/);
    expect(within(card).queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull(); // view / edit only
  });

  it('keeps a section expanded while moving between the object and a room view', async () => {
    renderWorkspace();
    await openProject();
    const button = await countButton(await screen.findByLabelText(`room-item-${salon.id}`), 6);
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
    fireEvent.click(await countButton(screen.getByLabelText('project-photos'), 7));
    await screen.findByRole('region', { name: 'Zdjęcia' });
    fireEvent.click(screen.getByLabelText('back-to-projects'));
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    vi.mocked(photosApi.fetchPhotoCounts).mockResolvedValue({ project: 0, rooms: {}, surfaces: {}, openings: {}, room_totals: {}, inspections: {}, findings: {}, lineages: {}, questions: {} });
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    const card = await screen.findByLabelText('project-photos');
    expect(await countButton(card, 0)).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region', { name: 'Zdjęcia' })).toBeNull();
  });
});

describe('ProjectWorkspace photos — photos are added on surfaces', () => {
  it('a wall card: the compact button shares the header line, left of Opcje, and its section can add', async () => {
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(
      listPage([makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } })]),
    );
    renderWorkspace();
    await openSalon();
    const card = screen.getByLabelText(`surface-item-${wall.id}`);
    const button = within(card).getByRole('button', { name: 'Zdjęcia: 3' });
    const options = within(card).getByLabelText(`options-toggle-${wall.id}`);
    // same header row as Opcje, immediately before it (no row of its own)
    expect(button.parentElement).toBe(options.parentElement);
    expect(button.nextElementSibling).toBe(options);

    fireEvent.click(button);
    await waitFor(() => expect(lastListParams()).toMatchObject({ context: 'SURFACE', surfaceId: wall.id }));
    expect(await within(card).findByRole('button', { name: 'Zrób zdjęcie' })).toBeEnabled();
    expect(within(card).getByRole('button', { name: 'Z galerii' })).toBeInTheDocument();
    await within(card).findByText('Salon → Ściana 1 → 23.06.2026 (10:15) · zrobione w aplikacji');
  });

  it.each([
    ['floor', floorSurface, 'Podłoga'],
    ['ceiling', ceilingSurface, 'Sufit'],
  ] as const)('the %s card has a photo button too, and adds photos to its own surface', async (planeKey, plane, label) => {
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(
      listPage([makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: plane.id } })]),
    );
    renderWorkspace();
    await openSalon();
    const card = await screen.findByLabelText(`${planeKey}-segments`);
    const button = await within(card).findByRole('button', { name: 'Zdjęcia: 0' });
    // same header line as the plane title
    const heading = within(card).getByRole('heading', { name: label });
    expect(heading.parentElement).toContainElement(button);
    fireEvent.click(button);
    await waitFor(() => expect(lastListParams()).toMatchObject({ context: 'SURFACE', surfaceId: plane.id }));
    expect(await within(card).findByRole('button', { name: 'Zrób zdjęcie' })).toBeInTheDocument();
    await within(card).findByText(new RegExp(`^Salon → ${label} → 23\\.06\\.2026`));
  });

  it('an uploaded photo of the floor goes to the floor surface and counts for the room', async () => {
    renderWorkspace();
    await openSalon();
    const card = await screen.findByLabelText('floor-segments');
    fireEvent.click(await within(card).findByRole('button', { name: 'Zdjęcia: 0' }));
    fireEvent.change(await within(card).findByTestId('photo-input-gallery'), {
      target: { files: [new File(['x'], 'p.jpg', { type: 'image/jpeg' })] },
    });
    await waitFor(() => expect(photosApi.uploadPhoto).toHaveBeenCalledTimes(1));
    expect(photosApi.uploadPhoto).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: project.id, context: 'SURFACE', surfaceId: floorSurface.id, roomId: salon.id, source: 'GALLERY' }),
      expect.anything(),
    );
  });

  it('an opening row has NO photo button any more (photos are added on its wall)', async () => {
    renderWorkspace();
    await openSalon();
    fireEvent.click(screen.getByLabelText(`options-toggle-${wall.id}`));
    fireEvent.click(await screen.findByLabelText(`toggle-openings-${wall.id}`));
    const row = await screen.findByLabelText(`opening-item-${door.id}`);
    expect(within(row).queryByRole('button', { name: /^Zdjęcia:/ })).toBeNull();
    expect(within(row).getByLabelText(`edit-opening-${door.id}`)).toBeInTheDocument();
    expect(within(row).getByLabelText(`archive-opening-${door.id}`)).toBeInTheDocument();
  });
});

describe('ProjectWorkspace photos — counts and uploads', () => {
  async function startWallUpload() {
    renderWorkspace();
    await openSalon();
    const card = screen.getByLabelText(`surface-item-${wall.id}`);
    const button = within(card).getByRole('button', { name: 'Zdjęcia: 3' });
    fireEvent.click(button);
    fireEvent.change(await within(card).findByTestId('photo-input-camera'), {
      target: { files: [jpegFile('c.jpg', jpegWithExif({ original: new Date() }))] },
    });
    await waitFor(() => expect(photosApi.uploadPhoto).toHaveBeenCalledTimes(1));
    return { card, button };
  }

  it('counts a finished upload once — wall, its room and the object — even when the section was collapsed meanwhile', async () => {
    const { card, button } = await startWallUpload();
    expect(photosApi.uploadPhoto).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: project.id, context: 'SURFACE', surfaceId: wall.id, roomId: salon.id, source: 'CAMERA' }),
      expect.anything(),
    );
    fireEvent.click(button); // collapse while the upload is still running
    expect(within(card).queryByRole('region', { name: 'Zdjęcia' })).toBeNull();

    // the server confirms the new numbers after the upload
    vi.mocked(photosApi.fetchPhotoCounts).mockResolvedValue({
      ...COUNTS, surfaces: { [wall.id]: 4 }, room_totals: { [salon.id]: 7 },
    });
    await act(async () => uploads[0].resolve(uploadResponse()));
    expect(await within(card).findByRole('button', { name: 'Zdjęcia: 4' })).toBeInTheDocument();
    expect(within(screen.getByLabelText('room-photos')).getByRole('button', { name: 'Zdjęcia: 7' })).toBeInTheDocument();
    // back on the object tab: the room card and the object's total follow the same single correction
    fireEvent.click(screen.getByLabelText('back-to-rooms'));
    expect(await within(await screen.findByLabelText(`room-item-${salon.id}`)).findByRole('button', { name: 'Zdjęcia: 7' })).toBeInTheDocument();
    expect(within(screen.getByLabelText('project-photos')).getByRole('button', { name: 'Zdjęcia: 8' })).toBeInTheDocument();
  });

  it('the room card on the object tab follows the wall upload (room total)', async () => {
    renderWorkspace();
    await openProject();
    const roomCard = await screen.findByLabelText(`room-item-${salon.id}`);
    await countButton(roomCard, 6);
    fireEvent.click(screen.getByLabelText(`open-room-${salon.id}`));
    await screen.findByLabelText(`surface-item-${wall.id}`);
    const wallCard = screen.getByLabelText(`surface-item-${wall.id}`);
    fireEvent.click(within(wallCard).getByRole('button', { name: 'Zdjęcia: 3' }));
    fireEvent.change(await within(wallCard).findByTestId('photo-input-gallery'), {
      target: { files: [new File(['x'], 'g.jpg', { type: 'image/jpeg' })] },
    });
    await waitFor(() => expect(photosApi.uploadPhoto).toHaveBeenCalledTimes(1));
    vi.mocked(photosApi.fetchPhotoCounts).mockResolvedValue({ ...COUNTS, surfaces: { [wall.id]: 4 }, room_totals: { [salon.id]: 7 } });
    await act(async () => uploads[0].resolve(uploadResponse()));
    // the room's own view button shows the new total as well
    expect(await within(screen.getByLabelText('room-photos')).findByRole('button', { name: 'Zdjęcia: 7' })).toBeInTheDocument();
  });

  it('shows no upload buttons in a wall section while uploads are switched off (D5), but the photos stay viewable', async () => {
    vi.mocked(photosApi.fetchPhotoStorage).mockResolvedValue(storageStatus({ uploads_enabled: false }));
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue(
      listPage([makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: wall.id } })]),
    );
    renderWorkspace();
    await openSalon();
    const card = screen.getByLabelText(`surface-item-${wall.id}`);
    fireEvent.click(within(card).getByRole('button', { name: 'Zdjęcia: 3' }));
    await within(card).findByText(/Dodawanie zdjęć jest obecnie wyłączone/);
    expect(within(card).queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
    expect(await within(card).findByRole('button', { name: /23\.06\.2026/ })).toBeInTheDocument();
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
    fireEvent.click(await countButton(card, 6));
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
  it('speaks Russian in the card, the button and the section; adding is explained where it is not offered', async () => {
    localStorage.setItem('locale', 'ru');
    renderWorkspace();
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    const card = await screen.findByLabelText('project-photos');
    expect(within(card).getByRole('heading', { name: 'Фото объекта' })).toBeInTheDocument();
    fireEvent.click(await within(card).findByRole('button', { name: 'Фото: 7' }));
    expect(await within(card).findByText('Фото пока нет. Добавьте их в карточке стены, пола или потолка.')).toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'Сделать фото' })).toBeNull();
  });

  it('the wall section is where Russian users find the camera button', async () => {
    localStorage.setItem('locale', 'ru');
    renderWorkspace();
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-project-${project.id}`));
    fireEvent.click(await screen.findByLabelText(`open-room-${salon.id}`));
    const card = await screen.findByLabelText(`surface-item-${wall.id}`);
    fireEvent.click(within(card).getByRole('button', { name: 'Фото: 3' }));
    expect(await within(card).findByRole('button', { name: 'Сделать фото' })).toBeInTheDocument();
  });
});
