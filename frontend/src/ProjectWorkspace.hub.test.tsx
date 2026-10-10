import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as clientsApi from './api/clients';
import * as photosApi from './api/photos';
import * as projectsApi from './api/projects';
import { ProjectWorkspace } from './components/ProjectWorkspace';
import { I18nProvider } from './hooks/useI18n';
import { ProjectType } from './types/project';

// Stage 16K.3: the screen of an object is a hub of tiles. The cards of the earlier stages are replaced by stubs here:
// this file is about where they are, not about what they do.

vi.mock('./api/clients', () => ({ fetchClients: vi.fn() }));
vi.mock('./api/projects', () => ({
  fetchProject: vi.fn(),
  fetchProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  archiveProject: vi.fn(),
  restoreProject: vi.fn(),
}));
vi.mock('./api/photos', async () => {
  const actual = await vi.importActual<typeof import('./api/photos')>('./api/photos');
  return { ...actual, fetchPhotoCounts: vi.fn(), fetchPhotos: vi.fn(), fetchPhotoStorage: vi.fn() };
});
vi.mock('./api/rooms', () => ({
  fetchRooms: vi.fn(async () => ({ items: [], total: 0 })),
  fetchRoom: vi.fn(),
  fetchProjectSummary: vi.fn(),
  createRoom: vi.fn(),
  updateRoom: vi.fn(),
  archiveRoom: vi.fn(),
  restoreRoom: vi.fn(),
}));
vi.mock('./api/surfaces', () => ({ fetchSurfaces: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('./api/openings', () => ({ fetchOpenings: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('./api/estimates', () => ({ listEstimates: vi.fn(async () => ({ items: [], total: 0 })), generateEstimate: vi.fn(), getEstimate: vi.fn() }));

const { stub } = vi.hoisted(() => ({
  stub: (name: string) => () => <div aria-label={`stub-${name}`}>{name}</div>,
}));
vi.mock('./components/ProjectDocuments', () => ({ ProjectDocuments: stub('documents') }));
vi.mock('./components/ProjectRepresentatives', () => ({ ProjectRepresentatives: stub('representatives') }));
vi.mock('./components/ProjectAdjacentWorks', () => ({ ProjectAdjacentWorks: stub('adjacent') }));
vi.mock('./components/ProjectContract', () => ({ ProjectContract: stub('contract') }));
vi.mock('./components/ProjectHandover', () => ({ ProjectHandover: stub('handover') }));
vi.mock('./components/ProjectConcealedWorks', () => ({ ProjectConcealedWorks: stub('concealed') }));
vi.mock('./components/ProjectAcceptance', () => ({ ProjectAcceptance: stub('acceptance') }));
vi.mock('./components/ProjectDecisions', () => ({ ProjectDecisions: stub('decisions') }));
vi.mock('./components/ProjectDowntime', () => ({ ProjectDowntime: stub('downtime') }));
vi.mock('./components/ProjectSummaryCard', () => ({ ProjectSummaryCard: stub('summary') }));
vi.mock('./components/RoomList', () => ({ RoomList: stub('rooms') }));

const project: ProjectType = {
  id: '11111111-1111-1111-1111-111111111111',
  owner_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
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

const COUNTS = {
  project: 4, rooms: {}, surfaces: {}, openings: {}, room_totals: {}, inspections: {}, findings: {}, lineages: {}, questions: {},
  works: {}, work_surfaces: {}, inspection_surfaces: {}, inspection_planes: {},
};

let backClick: (() => void) | undefined;

function renderWorkspace(props: Partial<React.ComponentProps<typeof ProjectWorkspace>> = {}) {
  return render(
    <I18nProvider>
      <ProjectWorkspace {...props} />
    </I18nProvider>,
  );
}

async function openHub() {
  fireEvent.click(await screen.findByLabelText(`open-project-${project.id}`));
  await screen.findByLabelText('object-hub');
}

const crumbs = () => screen.getByRole('navigation', { name: 'hierarchy-navigation' }).textContent;

describe('ProjectWorkspace — the hub of an object (Stage 16K.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    backClick = undefined;
    window.Telegram = {
      WebApp: {
        initData: '', initDataUnsafe: {}, version: '8.0', platform: 'web', colorScheme: 'light', themeParams: {}, isExpanded: false,
        viewportHeight: 800, viewportStableHeight: 800, ready: vi.fn(), expand: vi.fn(), close: vi.fn(),
        BackButton: { isVisible: false, show: vi.fn(), hide: vi.fn(), onClick: vi.fn((cb: () => void) => { backClick = cb; }), offClick: vi.fn() },
      },
    } as unknown as typeof window.Telegram;
    vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [project], total: 1 });
    vi.mocked(projectsApi.fetchProject).mockResolvedValue(project);
    vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(photosApi.fetchPhotoCounts).mockResolvedValue(COUNTS);
    vi.mocked(photosApi.fetchPhotoStorage).mockResolvedValue({ enabled: false } as never);
    vi.mocked(photosApi.fetchPhotos).mockResolvedValue({ items: [], total: 0, limit: 30, offset: 0 } as never);
  });

  it('is five large tiles after the card of the object: the estimate first, then rooms, photos, documents, agreement and protocols', async () => {
    renderWorkspace();
    await openHub();
    expect(screen.getByLabelText('project-detail')).toBeInTheDocument();
    const hub = screen.getByLabelText('object-hub');
    const tiles = Array.from(hub.children) as HTMLElement[];
    expect(tiles.map((tile) => tile.getAttribute('aria-label'))).toEqual([
      'open-estimates', 'object-tile-rooms', 'object-tile-photos', 'object-tile-documents', 'object-tile-legal',
    ]);
    expect(tiles.map((tile) => tile.textContent?.replace(/[›\d]/g, '').trim())).toEqual([
      'Kosztorys', 'Pomieszczenia', 'Zdjęcia obiektu', 'Dokumenty PDF', 'Umowa i protokoły',
    ]);
    for (const tile of tiles) expect(tile.className).toContain('min-h-14');
    expect(tiles[0].className).toContain('bg-amber-500');
    // the number of the photos of the whole object is on its tile
    await waitFor(() => expect(screen.getByLabelText('object-tile-photos-count')).toHaveTextContent('4'));
  });

  it('keeps every card of the earlier stages off the hub', async () => {
    renderWorkspace();
    await openHub();
    for (const name of ['rooms', 'summary', 'documents', 'representatives', 'adjacent', 'contract', 'handover', 'concealed', 'acceptance', 'decisions', 'downtime']) {
      expect(screen.queryByLabelText(`stub-${name}`)).toBeNull();
    }
    expect(screen.queryByLabelText('project-photos')).toBeNull();
    expect(crumbs()).toBe('Obiekty/Mieszkanie Mokotów');
  });

  it('the rooms tile opens the rooms and the summary of the object; the name in the breadcrumb leads back to the hub', async () => {
    renderWorkspace();
    await openHub();
    fireEvent.click(screen.getByLabelText('object-tile-rooms'));
    expect(screen.getByLabelText('stub-rooms')).toBeInTheDocument();
    expect(screen.getByLabelText('stub-summary')).toBeInTheDocument();
    expect(screen.queryByLabelText('object-hub')).toBeNull();
    expect(screen.queryByLabelText('project-detail')).toBeNull();
    expect(crumbs()).toBe('Obiekty/Mieszkanie Mokotów/Pomieszczenia');
    fireEvent.click(screen.getByLabelText('back-to-project'));
    expect(screen.getByLabelText('object-hub')).toBeInTheDocument();
  });

  it('the title of the object and "Edytuj" belong to the hub; the other screens are named by the breadcrumb alone', async () => {
    renderWorkspace();
    await openHub();
    expect(screen.getByRole('heading', { name: 'Mieszkanie Mokotów' })).toBeInTheDocument();
    expect(screen.getByLabelText('edit-project-detail').className).toContain('min-h-11');
    fireEvent.click(screen.getByLabelText('object-tile-legal'));
    expect(screen.queryByRole('heading', { name: 'Mieszkanie Mokotów' })).toBeNull();
    expect(screen.queryByLabelText('edit-project-detail')).toBeNull();
    fireEvent.click(screen.getByLabelText('back-to-project'));
    expect(screen.getByRole('heading', { name: 'Mieszkanie Mokotów' })).toBeInTheDocument();
  });

  it('every link of the breadcrumb is a 44 px button that wraps long names', async () => {
    renderWorkspace();
    await openHub();
    fireEvent.click(screen.getByLabelText('object-tile-legal'));
    fireEvent.click(screen.getByLabelText('legal-tile-contract'));
    for (const name of ['back-to-projects', 'back-to-project', 'back-to-legal']) {
      const link = screen.getByLabelText(name);
      expect(link.className).toContain('min-h-11');
      expect(link.className).toContain('break-words');
    }
  });

  it('the photos tile opens the photos of the object with the list open at once', async () => {
    renderWorkspace();
    await openHub();
    fireEvent.click(screen.getByLabelText('object-tile-photos'));
    const card = await screen.findByLabelText('project-photos');
    expect(within(card).getByRole('heading', { name: 'Zdjęcia obiektu' })).toBeInTheDocument();
    await waitFor(() => expect(photosApi.fetchPhotos).toHaveBeenCalled());
    expect(await within(card).findByRole('button', { name: 'Zdjęcia: 4' })).toHaveAttribute('aria-expanded', 'true');
    expect(crumbs()).toBe('Obiekty/Mieszkanie Mokotów/Zdjęcia obiektu');
  });

  it('the documents tile opens the documents', async () => {
    renderWorkspace();
    await openHub();
    fireEvent.click(screen.getByLabelText('object-tile-documents'));
    expect(screen.getByLabelText('stub-documents')).toBeInTheDocument();
    expect(crumbs()).toBe('Obiekty/Mieszkanie Mokotów/Dokumenty PDF');
  });

  it('"Umowa i protokoły" is a short list in three groups, not a pile of cards', async () => {
    renderWorkspace();
    await openHub();
    fireEvent.click(screen.getByLabelText('object-tile-legal'));
    const menu = screen.getByLabelText('legal-menu');
    expect(within(menu).getAllByRole('heading').map((h) => h.textContent)).toEqual(['Strony i wykonawcy', 'Umowa', 'Protokoły']);
    const rows = within(menu).getAllByRole('button');
    expect(rows.map((row) => row.getAttribute('aria-label'))).toEqual([
      'legal-tile-representatives', 'legal-tile-adjacent', 'legal-tile-contract',
      'legal-tile-handover', 'legal-tile-concealed', 'legal-tile-acceptance', 'legal-tile-decisions', 'legal-tile-downtime',
    ]);
    for (const row of rows) expect(row.className).toContain('min-h-14');
    for (const name of ['representatives', 'adjacent', 'contract', 'handover', 'concealed', 'acceptance', 'decisions', 'downtime']) {
      expect(screen.queryByLabelText(`stub-${name}`)).toBeNull();
    }
    expect(crumbs()).toBe('Obiekty/Mieszkanie Mokotów/Umowa i protokoły');
  });

  it.each([
    ['representatives', 'Osoby objektu'],
    ['adjacent', 'Prace innych wykonawców'],
    ['contract', 'Umowa'],
    ['handover', 'Protokół przekazania pomieszczeń'],
    ['concealed', 'Protokół odbioru robót zanikających'],
    ['acceptance', 'Protokół odbioru prac'],
    ['decisions', 'Protokół informacji i decyzji'],
    ['downtime', 'Przestój po stronie Zamawiającego'],
  ])('the row "%s" opens that card alone, and the breadcrumb leads back to the list', async (id, title) => {
    renderWorkspace();
    await openHub();
    fireEvent.click(screen.getByLabelText('object-tile-legal'));
    fireEvent.click(screen.getByLabelText(`legal-tile-${id}`));
    expect(screen.getByLabelText(`stub-${id}`)).toBeInTheDocument();
    expect(screen.queryByLabelText('legal-menu')).toBeNull();
    expect(document.querySelectorAll('[aria-label^="stub-"]')).toHaveLength(1);
    expect(crumbs()).toBe(`Obiekty/Mieszkanie Mokotów/Umowa i protokoły/${title}`);
    fireEvent.click(screen.getByLabelText('back-to-legal'));
    expect(screen.getByLabelText('legal-menu')).toBeInTheDocument();
  });

  it('the Telegram BackButton goes one step up: card → list → hub → list of objects', async () => {
    renderWorkspace();
    await openHub();
    fireEvent.click(screen.getByLabelText('object-tile-legal'));
    fireEvent.click(screen.getByLabelText('legal-tile-contract'));
    expect(screen.getByLabelText('stub-contract')).toBeInTheDocument();
    act(() => backClick?.());
    expect(screen.getByLabelText('legal-menu')).toBeInTheDocument();
    act(() => backClick?.());
    expect(screen.getByLabelText('object-hub')).toBeInTheDocument();
    act(() => backClick?.());
    await waitFor(() => expect(screen.getByLabelText(`open-project-${project.id}`)).toBeInTheDocument());
  });

  it('the estimate tile opens the estimates, and Back returns to the hub', async () => {
    renderWorkspace();
    await openHub();
    fireEvent.click(screen.getByLabelText('open-estimates'));
    await screen.findByLabelText('estimates-empty-state');
    act(() => backClick?.());
    expect(screen.getByLabelText('object-hub')).toBeInTheDocument();
  });

  it('a request from the card of a client lands on the estimates, and Back leads to the hub of that object', async () => {
    renderWorkspace({ openRequest: { token: 1, projectId: project.id, view: 'estimates' } });
    await screen.findByLabelText('estimates-empty-state');
    act(() => backClick?.());
    expect(await screen.findByLabelText('object-hub')).toBeInTheDocument();
  });

  it('opens the hub again, not the last screen, when the object is opened a second time', async () => {
    renderWorkspace();
    await openHub();
    fireEvent.click(screen.getByLabelText('object-tile-legal'));
    fireEvent.click(screen.getByLabelText('back-to-projects'));
    fireEvent.click(await screen.findByLabelText(`open-project-${project.id}`));
    expect(await screen.findByLabelText('object-hub')).toBeInTheDocument();
  });

  it('is in Russian: the tile and the groups', async () => {
    localStorage.setItem('locale', 'ru');
    renderWorkspace();
    await openHub();
    expect(screen.getByLabelText('object-tile-legal')).toHaveTextContent('Договор и протоколы');
    fireEvent.click(screen.getByLabelText('object-tile-legal'));
    expect(within(screen.getByLabelText('legal-menu')).getAllByRole('heading').map((h) => h.textContent)).toEqual([
      'Стороны и подрядчики', 'Договор', 'Протоколы',
    ]);
  });

  it('long names wrap inside the tile (nothing is cut or pushed out)', async () => {
    renderWorkspace();
    await openHub();
    const tile = screen.getByLabelText('object-tile-legal');
    expect(tile.firstElementChild?.className).toContain('break-words');
    expect(tile.firstElementChild?.className).not.toMatch(/truncate|whitespace-nowrap/);
  });
});
