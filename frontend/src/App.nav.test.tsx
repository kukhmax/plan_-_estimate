import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within, act } from '@testing-library/react';
import App from './App';
import * as api from './api/auth';
import * as projectsApi from './api/projects';
import * as clientsApi from './api/clients';
import * as priceItemsApi from './api/priceItems';
import { openMenu } from './test/menu';
import { clearLastProject, readLastProject, writeLastProject } from './utils/lastProject';

vi.mock('./api/auth', async () => {
  const actual = await vi.importActual<typeof import('./api/auth')>('./api/auth');
  return { ...actual, loginWithTelegram: vi.fn(), fetchCurrentUser: vi.fn() };
});
vi.mock('./api/clients', () => ({
  fetchClients: vi.fn(), createClient: vi.fn(), archiveClient: vi.fn(), restoreClient: vi.fn(), updateClient: vi.fn(), fetchClient: vi.fn(),
}));
vi.mock('./api/projects', () => ({
  fetchProjects: vi.fn(), fetchProject: vi.fn(), createProject: vi.fn(), updateProject: vi.fn(), archiveProject: vi.fn(), restoreProject: vi.fn(),
}));
vi.mock('./api/rooms', () => ({
  fetchRooms: vi.fn().mockResolvedValue({ items: [], total: 0 }), fetchRoom: vi.fn(), createRoom: vi.fn(), updateRoom: vi.fn(), archiveRoom: vi.fn(), restoreRoom: vi.fn(),
}));
vi.mock('./api/surfaces', () => ({
  fetchSurfaces: vi.fn().mockResolvedValue({ items: [], total: 0 }), createSurface: vi.fn(), updateSurface: vi.fn(), archiveSurface: vi.fn(), restoreSurface: vi.fn(), generateWalls: vi.fn(),
}));
vi.mock('./api/openings', () => ({
  fetchOpenings: vi.fn().mockResolvedValue({ items: [], total: 0 }), createOpening: vi.fn(), updateOpening: vi.fn(), archiveOpening: vi.fn(), restoreOpening: vi.fn(),
}));
vi.mock('./api/priceItems', () => ({
  fetchPriceItems: vi.fn().mockResolvedValue({ items: [], total: 0 }), createPriceItem: vi.fn(), updatePriceItem: vi.fn(), archivePriceItem: vi.fn(), restorePriceItem: vi.fn(),
}));

const OWNER = '11111111-1111-1111-1111-111111111111';
const OTHER_OWNER = '99999999-9999-9999-9999-999999999999';
const PROJECT_ID = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa';

const project = (over: Record<string, unknown> = {}) => ({
  id: PROJECT_ID, owner_id: OWNER, client_id: null, name: 'Mieszkanie Mokotów', address: 'ul. Dobra 10', city: 'Warszawa', postal_code: '00-001',
  description: null, status: 'PLANNING', is_archived: false, created_at: '2026-09-09T10:00:00Z', updated_at: '2026-09-09T10:00:00Z', ...over,
});

function mockAuth(userId = OWNER) {
  vi.mocked(api.loginWithTelegram).mockResolvedValue({
    access_token: 't', token_type: 'bearer', is_dev_auth: true,
    user: { id: userId, telegram_user_id: 1, username: 'u', first_name: 'Jan', last_name: 'K', language_code: 'pl', created_at: '2026-09-08T12:00:00Z', updated_at: '2026-09-08T12:00:00Z' },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllEnvs();
  vi.stubEnv('DEV', true);
  vi.stubEnv('VITE_DEV_MOCK_AUTH', 'true');
  delete (window as unknown as { Telegram?: unknown }).Telegram;
  window.history.replaceState({}, '', '/');
  localStorage.clear();
  vi.mocked(clientsApi.fetchClients).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(projectsApi.fetchProjects).mockResolvedValue({ items: [project()], total: 1 } as never);
  vi.mocked(projectsApi.fetchProject).mockResolvedValue(project() as never);
  vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
});

describe('the last object (usability U-11)', () => {
  it('remembers the object that is open, per account', async () => {
    mockAuth();
    render(<App />);
    fireEvent.click(await screen.findByLabelText('bottom-nav-projects'));
    fireEvent.click(await screen.findByLabelText(`open-project-${PROJECT_ID}`));
    await screen.findByLabelText('project-detail');
    await waitFor(() => expect(readLastProject(OWNER)).toBe(PROJECT_ID));
    expect(readLastProject(OTHER_OWNER)).toBeNull();
  });

  it('opens the remembered object at the start instead of the list of clients', async () => {
    writeLastProject(OWNER, PROJECT_ID);
    mockAuth();
    render(<App />);
    expect(await screen.findByLabelText('project-detail')).toBeInTheDocument();
    expect(projectsApi.fetchProject).toHaveBeenCalledWith(PROJECT_ID);
    expect(screen.getByRole('banner', { name: 'app-header' })).toHaveTextContent('Obiekty');
    expect(screen.queryByLabelText('clients-section')).toBeNull();
  });

  it('does not use the memory of another account', async () => {
    writeLastProject(OTHER_OWNER, PROJECT_ID);
    mockAuth();
    render(<App />);
    expect(await screen.findByLabelText('clients-section')).toBeInTheDocument();
    expect(projectsApi.fetchProject).not.toHaveBeenCalled();
  });

  it('an archived object is not reopened: the list of objects shows and the memory is cleared', async () => {
    writeLastProject(OWNER, PROJECT_ID);
    vi.mocked(projectsApi.fetchProject).mockResolvedValue(project({ is_archived: true }) as never);
    mockAuth();
    render(<App />);
    await screen.findByLabelText('projects-list');
    expect(screen.queryByLabelText('project-detail')).toBeNull();
    await waitFor(() => expect(readLastProject(OWNER)).toBeNull());
  });

  it('an object that is gone shows the list without an error screen', async () => {
    writeLastProject(OWNER, PROJECT_ID);
    vi.mocked(projectsApi.fetchProject).mockRejectedValue(new Error('Not found'));
    mockAuth();
    render(<App />);
    await screen.findByLabelText('projects-list');
    expect(screen.queryByText('Not found')).toBeNull();
    await waitFor(() => expect(readLastProject(OWNER)).toBeNull());
  });

  it('a link with ?open= wins over the memory', async () => {
    writeLastProject(OWNER, PROJECT_ID);
    window.history.replaceState({}, '', '/?open=calendar');
    mockAuth();
    render(<App />);
    await waitFor(() => expect(screen.getByRole('banner', { name: 'app-header' })).toHaveTextContent('Kalendarz'));
    expect(projectsApi.fetchProject).not.toHaveBeenCalled();
  });

  it('a blocked storage only means that nothing is remembered', async () => {
    // only the memory of the last object is blocked (the rest of the application reads its own keys as usual)
    const original = Storage.prototype.getItem;
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (this: Storage, name: string) {
      if (name.startsWith('pe.lastProject')) throw new Error('blocked');
      return original.call(this, name);
    });
    mockAuth();
    render(<App />);
    expect(await screen.findByLabelText('clients-section')).toBeInTheDocument();
    getItem.mockRestore();
  });

  it('keeps the helpers safe: a damaged value is ignored and clear works', () => {
    localStorage.setItem(`pe.lastProject.${OWNER}`, 'not-an-id');
    expect(readLastProject(OWNER)).toBeNull();
    writeLastProject(OWNER, PROJECT_ID);
    expect(readLastProject(OWNER)).toBe(PROJECT_ID);
    clearLastProject(OWNER);
    expect(readLastProject(OWNER)).toBeNull();
  });
});

describe('the bottom bar (usability U-11)', () => {
  it('has four places, each 56 px tall, and marks the open one', async () => {
    mockAuth();
    render(<App />);
    const bar = await screen.findByLabelText('bottom-nav');
    for (const id of ['projects', 'clients', 'pricebook', 'more']) {
      const button = within(bar).getByLabelText(`bottom-nav-${id}`);
      expect(button.className).toContain('min-h-14');
    }
    expect(within(bar).getByLabelText('bottom-nav-clients')).toHaveAttribute('aria-current', 'page');
    expect(within(bar).getByLabelText('bottom-nav-projects')).not.toHaveAttribute('aria-current');
    expect(bar.className).toContain('safe-area-inset-bottom'); // the safe area of the phone under the bar
    expect(within(bar).getByLabelText('bottom-nav-more')).toHaveTextContent('Więcej');
  });

  it('switches the sections and "Więcej" opens the whole menu', async () => {
    mockAuth();
    render(<App />);
    fireEvent.click(await screen.findByLabelText('bottom-nav-pricebook'));
    await waitFor(() => expect(screen.getByRole('banner', { name: 'app-header' })).toHaveTextContent('Cennik'));
    expect(screen.getByLabelText('bottom-nav-pricebook')).toHaveAttribute('aria-current', 'page');
    fireEvent.click(screen.getByLabelText('bottom-nav-projects'));
    await waitFor(() => expect(screen.getByRole('banner', { name: 'app-header' })).toHaveTextContent('Obiekty'));
    fireEvent.click(screen.getByLabelText('bottom-nav-more'));
    expect(await screen.findByRole('dialog', { name: 'main-menu' })).toBeInTheDocument();
    // under an overlay the bar steps aside
    expect(screen.queryByLabelText('bottom-nav')).toBeNull();
  });

  it('is in Russian too', async () => {
    localStorage.setItem('locale', 'ru');
    mockAuth();
    render(<App />);
    const bar = await screen.findByLabelText('bottom-nav');
    expect(bar).toHaveTextContent('Объекты');
    expect(bar).toHaveTextContent('Клиенты');
    expect(bar).toHaveTextContent('Прайс');
    expect(bar).toHaveTextContent('Ещё');
  });

  it('hides while a text field has the focus (the keyboard) and comes back', async () => {
    mockAuth();
    render(<App />);
    await screen.findByLabelText('bottom-nav');
    const field = await screen.findByLabelText('search-clients');
    act(() => field.focus());
    await waitFor(() => expect(screen.queryByLabelText('bottom-nav')).toBeNull());
    act(() => field.blur());
    await waitFor(() => expect(screen.getByLabelText('bottom-nav')).toBeInTheDocument());
  });

  it('hides when the visual viewport is much shorter than the window (the keyboard of the phone)', async () => {
    const listeners: Array<() => void> = [];
    const viewport = { height: 800, addEventListener: (_: string, fn: () => void) => listeners.push(fn), removeEventListener: () => {} };
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });
    mockAuth();
    render(<App />);
    await screen.findByLabelText('bottom-nav');
    viewport.height = 380;
    act(() => listeners.forEach((fn) => fn()));
    await waitFor(() => expect(screen.queryByLabelText('bottom-nav')).toBeNull());
    viewport.height = 800;
    act(() => listeners.forEach((fn) => fn()));
    await waitFor(() => expect(screen.getByLabelText('bottom-nav')).toBeInTheDocument());
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: undefined });
  });

  it('is not shown before the sign-in', () => {
    vi.mocked(api.loginWithTelegram).mockReturnValue(new Promise(() => {}));
    render(<App />);
    expect(screen.queryByLabelText('bottom-nav')).toBeNull();
    void openMenu;
  });
});
