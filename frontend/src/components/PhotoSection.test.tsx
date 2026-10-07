import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { resetPhotoStorage } from '../hooks/usePhotoStorage';
import { resetPhotoUploadQueue } from '../hooks/usePhotoUploadQueue';
import { PhotoUploadResponse } from '../types/photo';
import { jpegFile, jpegWithExif } from '../test/jpegFixtures';
import { detailFor, listPage, makeItem, PROJECT_ID, ROOM_ID, storageStatus, SURFACE_ID } from '../test/photoFixtures';
import { PhotoSection } from './PhotoSection';

vi.mock('../api/photos', async () => {
  const actual = await vi.importActual<typeof import('../api/photos')>('../api/photos');
  return {
    ...actual,
    fetchPhotos: vi.fn(),
    fetchPhoto: vi.fn(),
    fetchPhotoStorage: vi.fn(),
    uploadPhoto: vi.fn(),
    patchPhotoAttachment: vi.fn(),
    archivePhotoAttachment: vi.fn(),
    restorePhotoAttachment: vi.fn(),
  };
});
import {
  archivePhotoAttachment,
  fetchPhoto,
  fetchPhotos,
  fetchPhotoStorage,
  restorePhotoAttachment,
  uploadPhoto,
} from '../api/photos';

type SectionProps = React.ComponentProps<typeof PhotoSection>;

function renderSection(over: Partial<SectionProps> = {}) {
  const onCountAdjust = vi.fn();
  const props: SectionProps = {
    projectId: PROJECT_ID,
    // The default section is a SURFACE's: the only kind that offers uploading (the object and a room list everything
    // below them for viewing and editing).
    context: 'SURFACE',
    targetId: SURFACE_ID,
    roomId: ROOM_ID,
    allowUpload: true,
    locationLabel: 'Salon',
    onCountAdjust,
    ...over,
  };
  const view = render(
    <I18nProvider>
      <PhotoSection {...props} />
    </I18nProvider>,
  );
  return { onCountAdjust, ...view };
}

const lastListParams = () => {
  const calls = vi.mocked(fetchPhotos).mock.calls;
  return calls[calls.length - 1][1];
};
// a photo the camera has just taken (fresh EXIF capture time): the camera button declares it CAMERA
const file = (name = 'a.jpg') => jpegFile(name, jpegWithExif({ original: new Date() }));
const pickCamera = (files: File[]) =>
  fireEvent.change(screen.getByTestId('photo-input-camera'), { target: { files } });
const pickGallery = (files: File[]) =>
  fireEvent.change(screen.getByTestId('photo-input-gallery'), { target: { files } });

let uploads: Array<{ resolve: (r: PhotoUploadResponse) => void; reject: (e: unknown) => void; params: Record<string, unknown> }>;

beforeEach(() => {
  localStorage.clear();
  resetPhotoStorage();
  resetPhotoUploadQueue();
  uploads = [];
  vi.mocked(fetchPhotos).mockReset().mockResolvedValue(listPage([]));
  vi.mocked(fetchPhoto).mockReset();
  vi.mocked(fetchPhotoStorage).mockReset().mockResolvedValue(storageStatus());
  vi.mocked(archivePhotoAttachment).mockReset();
  vi.mocked(restorePhotoAttachment).mockReset();
  vi.mocked(uploadPhoto).mockReset().mockImplementation(
    (params) =>
      new Promise<PhotoUploadResponse>((resolve, reject) => {
        uploads.push({ resolve, reject, params: params as unknown as Record<string, unknown> });
      }),
  );
});

afterEach(() => {
  resetPhotoUploadQueue();
  resetPhotoStorage();
});

function uploadResult(item = makeItem()): PhotoUploadResponse {
  return {
    asset: item.asset,
    attachment: item.attachment,
    thumbnail_url: item.thumbnail_url ?? '',
    display_url: 'd',
    urls_expire_at: '2099-01-01T00:00:00Z',
    storage: { state: 'OK' },
  };
}

describe('PhotoSection — listing', () => {
  it.each([
    ['PROJECT', undefined, { archived: false, limit: 30 }],
    ['ROOM', ROOM_ID, { inRoomId: ROOM_ID, archived: false, limit: 30 }],
    ['SURFACE', SURFACE_ID, { context: 'SURFACE', surfaceId: SURFACE_ID, archived: false, limit: 30 }],
    ['OPENING', 'op1', { context: 'OPENING', openingId: 'op1', archived: false, limit: 30 }],
  ] as const)('%s section asks the server for its photos (the object: all; a room: everything in it)', async (context, targetId, expected) => {
    renderSection({ context, targetId });
    await waitFor(() => expect(fetchPhotos).toHaveBeenCalledTimes(1));
    const [projectId, params] = vi.mocked(fetchPhotos).mock.calls[0];
    expect(projectId).toBe(PROJECT_ID);
    const defined = Object.fromEntries(Object.entries(params ?? {}).filter(([, v]) => v !== undefined));
    expect(defined).toEqual(expected);
  });

  it('shows a loading state, then the tiles with the caption line (fixed location)', async () => {
    const item = makeItem();
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([item]));
    renderSection({ locationLabel: 'Salon → Ściana 1' });
    expect(screen.getByText('Ładowanie zdjęć…')).toBeInTheDocument();
    await screen.findByText('Salon → Ściana 1 → 23.06.2026 (10:15) · zrobione w aplikacji');
  });

  it('resolves a per-photo location for the project-wide list', async () => {
    const a = makeItem({ attachment: { room_id: ROOM_ID } });
    const b = makeItem({ attachment: { context: 'SURFACE', room_id: null, surface_id: SURFACE_ID } });
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([a, b]));
    renderSection({
      context: 'PROJECT',
      targetId: undefined,
      locationLabel: (attachment) => (attachment.surface_id ? 'Kuchnia → Ściana 2' : 'Salon'),
    });
    await screen.findByText(/^Salon → 23\.06\.2026/);
    expect(screen.getByText(/^Kuchnia → Ściana 2 → 23\.06\.2026/)).toBeInTheDocument();
  });

  it.each([
    ['the object', { context: 'PROJECT' as const, targetId: undefined }],
    ['a room', { context: 'ROOM' as const, targetId: ROOM_ID }],
  ])('%s list is grouped by day once it is long; a surface list never is', async (_name, props) => {
    const many = Array.from({ length: 14 }, (_, i) => makeItem({ asset: { captured_at: `2026-06-${String(20 + (i % 3)).padStart(2, '0')}T10:00:00` } }));
    vi.mocked(fetchPhotos).mockResolvedValue(listPage(many));
    const view = renderSection({ ...props, allowUpload: false, locationLabel: 'x' });
    await within(view.container).findAllByTestId('photo-day-header');
    view.unmount();

    renderSection();
    await screen.findAllByRole('listitem');
    expect(screen.queryAllByTestId('photo-day-header')).toHaveLength(0);
  });

  it('shows the empty state, and a retryable localized error', async () => {
    renderSection();
    await screen.findByText('Brak zdjęć.');

    vi.mocked(fetchPhotos).mockRejectedValueOnce(new ApiError('boom', 0, 'NETWORK_ERROR'));
    const failing = render(
      <I18nProvider>
        <PhotoSection projectId={PROJECT_ID} context="ROOM" targetId="other" locationLabel="X" />
      </I18nProvider>,
    );
    const alert = await within(failing.container).findByRole('alert');
    expect(alert).toHaveTextContent('Brak połączenia. Spróbuj ponownie.');
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()]));
    fireEvent.click(within(failing.container).getByRole('button', { name: 'Spróbuj ponownie' }));
    await waitFor(() => expect(within(failing.container).queryByRole('alert')).toBeNull());
  });

  it('paginates with a cursor, appends without duplicates, and restarts on a stale cursor', async () => {
    const first = [makeItem(), makeItem()];
    const second = [first[1], makeItem()]; // overlaps by one
    vi.mocked(fetchPhotos).mockResolvedValueOnce(listPage(first, 'cur1'));
    renderSection();
    await screen.findByRole('button', { name: 'Pokaż więcej' });

    vi.mocked(fetchPhotos).mockResolvedValueOnce(listPage(second, null));
    fireEvent.click(screen.getByRole('button', { name: 'Pokaż więcej' }));
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(3));
    expect(lastListParams()?.cursor).toBe('cur1');
    expect(screen.queryByRole('button', { name: 'Pokaż więcej' })).toBeNull();
  });

  it('a stale cursor reloads the first page instead of failing', async () => {
    vi.mocked(fetchPhotos).mockResolvedValueOnce(listPage([makeItem()], 'old'));
    renderSection();
    await screen.findByRole('button', { name: 'Pokaż więcej' });
    vi.mocked(fetchPhotos)
      .mockRejectedValueOnce(new ApiError('x', 422, 'PHOTO_CURSOR_INVALID'))
      .mockResolvedValueOnce(listPage([makeItem(), makeItem()], null));
    fireEvent.click(screen.getByRole('button', { name: 'Pokaż więcej' }));
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2));
    expect(lastListParams()?.cursor).toBeUndefined();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('PhotoSection — availability of uploading', () => {
  it('shows the picker when uploads are enabled', async () => {
    renderSection();
    expect(await screen.findByRole('button', { name: 'Zrób zdjęcie' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Z galerii' })).toBeInTheDocument();
  });

  it('hides the picker until the storage status is known (never a button by mistake)', async () => {
    let release: (value: ReturnType<typeof storageStatus>) => void = () => undefined;
    vi.mocked(fetchPhotoStorage).mockReturnValue(new Promise((resolve) => (release = resolve)));
    renderSection();
    expect(screen.queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
    await act(async () => release(storageStatus()));
    expect(await screen.findByRole('button', { name: 'Zrób zdjęcie' })).toBeInTheDocument();
  });

  it('uploads OFF: no buttons, a neutral note, existing photos stay viewable (D5)', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValue(storageStatus({ uploads_enabled: false }));
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()]));
    renderSection();
    await screen.findByText('Dodawanie zdjęć jest obecnie wyłączone. Możesz przeglądać istniejące zdjęcia.');
    expect(screen.queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Z galerii' })).toBeNull();
    await screen.findByRole('list');
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('storage full: no buttons and the limit message', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValue(storageStatus({ state: 'FULL', uploads_enabled: true }));
    renderSection();
    await screen.findByText(/Limit miejsca na zdjęcia został osiągnięty/);
    expect(screen.queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
  });

  it('storage warning: keeps the buttons and adds a quiet warning', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValue(storageStatus({ state: 'WARNING' }));
    renderSection();
    await screen.findByRole('button', { name: 'Zrób zdjęcie' });
    expect(screen.getByText('Miejsce na zdjęcia zbliża się do limitu.')).toBeInTheDocument();
  });

  it('media unavailable: the note only — no picker, no grid, no options', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValue(storageStatus({ media_available: false }));
    renderSection();
    await screen.findByText('Podgląd zdjęć jest chwilowo niedostępny.');
    expect(screen.queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Opcje zdjęć' })).toBeNull();
  });

  it('an unreachable storage status shows neither buttons nor a misleading "disabled" note', async () => {
    vi.mocked(fetchPhotoStorage).mockRejectedValue(new Error('offline'));
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()]));
    renderSection();
    await screen.findByRole('list');
    expect(screen.queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
    expect(screen.queryByText(/wyłączone/)).toBeNull();
  });
});

describe('PhotoSection — uploading', () => {
  it('camera pick starts an upload for this target with the declared source and shows the row', async () => {
    renderSection();
    await screen.findByRole('button', { name: 'Zrób zdjęcie' });
    await act(async () => pickCamera([file('c.jpg')]));
    await waitFor(() => expect(uploadPhoto).toHaveBeenCalledTimes(1));
    expect(uploads[0].params).toMatchObject({
      projectId: PROJECT_ID,
      context: 'SURFACE',
      surfaceId: SURFACE_ID,
      roomId: ROOM_ID, // not sent to the server for a surface: it lets the host keep the room's total in step
      source: 'CAMERA',
    });
    expect(screen.getByRole('list', { name: 'Wysyłanie zdjęć' })).toBeInTheDocument();
    expect(screen.getByText('c.jpg')).toBeInTheDocument();
  });

  it('gallery pick queues several files, one upload at a time, source GALLERY', async () => {
    renderSection();
    await screen.findByRole('button', { name: 'Z galerii' });
    await act(async () => pickGallery([file('1.jpg'), file('2.jpg'), file('3.jpg')]));
    expect(uploadPhoto).toHaveBeenCalledTimes(1);
    expect(uploads[0].params).toMatchObject({ context: 'SURFACE', surfaceId: SURFACE_ID, source: 'GALLERY' });
    expect(screen.getByText('3.jpg')).toBeInTheDocument();
  });

  it.each([
    ['the object', { context: 'PROJECT' as const, targetId: undefined, roomId: undefined }],
    ['a room', { context: 'ROOM' as const, targetId: ROOM_ID, roomId: undefined }],
  ])('%s list is for viewing and editing only: no picker, no upload notes (photos are added on surfaces)', async (_name, props) => {
    renderSection({ ...props, allowUpload: false, locationLabel: 'x' });
    await screen.findByText('Brak zdjęć. Dodaj je w karcie ściany, podłogi lub sufitu.');
    expect(screen.queryByRole('button', { name: 'Zrób zdjęcie' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Z galerii' })).toBeNull();
    expect(screen.queryByTestId('photo-input-camera')).toBeNull();
  });

  it('an aggregated list stays free of upload notices even when the server has uploads off or storage full', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValue(storageStatus({ uploads_enabled: false, state: 'FULL' }));
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()]));
    renderSection({ context: 'PROJECT', targetId: undefined, allowUpload: false, locationLabel: 'x' });
    await screen.findByRole('list');
    expect(screen.queryByText(/wyłączone/)).toBeNull();
    expect(screen.queryByText(/Limit miejsca/)).toBeNull();
  });

  it('when an upload finishes the grid is refreshed and the transient row disappears', async () => {
    const item = makeItem();
    renderSection();
    await screen.findByRole('button', { name: 'Zrób zdjęcie' });
    await act(async () => pickCamera([file('c.jpg')]));
    await waitFor(() => expect(uploads).toHaveLength(1));
    expect(fetchPhotos).toHaveBeenCalledTimes(1);

    vi.mocked(fetchPhotos).mockResolvedValue(listPage([item]));
    await act(async () => uploads[0].resolve(uploadResult(item)));
    await waitFor(() => expect(fetchPhotos).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText('c.jpg')).toBeNull());
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('more than 10 files in one selection: only 10 are queued and the user is told', async () => {
    renderSection();
    await screen.findByRole('button', { name: 'Z galerii' });
    const files = Array.from({ length: 12 }, (_, i) => file(`${i}.jpg`));
    await act(async () => pickGallery(files));
    expect(screen.getByText('Wybrano zbyt wiele plików — dodano pierwsze 10.')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Wysyłanie zdjęć' })).getAllByRole('listitem')).toHaveLength(10);
  });

  it('a failed upload stays visible with a localized reason and a retry', async () => {
    renderSection();
    await screen.findByRole('button', { name: 'Zrób zdjęcie' });
    await act(async () => pickCamera([file('c.jpg')]));
    await waitFor(() => expect(uploads).toHaveLength(1));
    await act(async () => uploads[0].reject(new ApiError('x', 415, 'PHOTO_UNSUPPORTED_FORMAT')));
    expect(await screen.findByText('Użyj JPEG, PNG lub WebP.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zamknij' })).toBeInTheDocument();
  });

  describe('which sections refresh when an upload finishes', () => {
    async function startUpload(target: Parameters<ReturnType<(typeof import('../hooks/usePhotoUploadQueue'))['getPhotoUploadQueue']>['enqueue']>[1]) {
      const { getPhotoUploadQueue } = await import('../hooks/usePhotoUploadQueue');
      await act(async () => {
        getPhotoUploadQueue().enqueue([file('o.jpg')], target, 'GALLERY');
      });
    }

    it('the surface itself, every aggregated list that contains it — and nothing else', async () => {
      const surfaceView = renderSection();
      const roomView = render(
        <I18nProvider>
          <PhotoSection projectId={PROJECT_ID} context="ROOM" targetId={ROOM_ID} locationLabel="x" />
        </I18nProvider>,
      );
      const otherRoomView = render(
        <I18nProvider>
          <PhotoSection projectId={PROJECT_ID} context="ROOM" targetId="other-room" locationLabel="x" />
        </I18nProvider>,
      );
      const projectView = render(
        <I18nProvider>
          <PhotoSection projectId={PROJECT_ID} context="PROJECT" locationLabel="x" />
        </I18nProvider>,
      );
      await waitFor(() => expect(fetchPhotos).toHaveBeenCalledTimes(4));
      await within(surfaceView.container).findByRole('button', { name: 'Z galerii' });

      await startUpload({ projectId: PROJECT_ID, context: 'SURFACE', surfaceId: SURFACE_ID, roomId: ROOM_ID });
      vi.mocked(fetchPhotos).mockClear();
      await act(async () => uploads[0].resolve(uploadResult(makeItem())));
      await waitFor(() => expect(fetchPhotos).toHaveBeenCalledTimes(3)); // surface + its room + the object
      const reloaded = vi.mocked(fetchPhotos).mock.calls.map((call) => JSON.stringify(call[1]));
      expect(reloaded.some((p) => p.includes(SURFACE_ID))).toBe(true);
      expect(reloaded.some((p) => p.includes(`"inRoomId":"${ROOM_ID}"`))).toBe(true);
      expect(reloaded.some((p) => p.includes('other-room'))).toBe(false);
      for (const view of [surfaceView, roomView, otherRoomView, projectView]) view.unmount();
    });

    it('an upload of another surface does not refresh this surface', async () => {
      renderSection();
      await screen.findByRole('button', { name: 'Z galerii' });
      await startUpload({ projectId: PROJECT_ID, context: 'SURFACE', surfaceId: 'another-surface', roomId: ROOM_ID });
      vi.mocked(fetchPhotos).mockClear();
      await act(async () => uploads[0].resolve(uploadResult(makeItem())));
      await act(async () => undefined);
      expect(fetchPhotos).not.toHaveBeenCalled();
    });

    it('the queue rows are shown by the surface section only, not by the lists that contain it', async () => {
      const surfaceView = renderSection();
      const roomView = render(
        <I18nProvider>
          <PhotoSection projectId={PROJECT_ID} context="ROOM" targetId={ROOM_ID} locationLabel="x" />
        </I18nProvider>,
      );
      const projectView = render(
        <I18nProvider>
          <PhotoSection projectId={PROJECT_ID} context="PROJECT" locationLabel="x" />
        </I18nProvider>,
      );
      await within(surfaceView.container).findByRole('button', { name: 'Z galerii' });
      await startUpload({ projectId: PROJECT_ID, context: 'SURFACE', surfaceId: SURFACE_ID, roomId: ROOM_ID });
      expect(within(surfaceView.container).getByRole('list', { name: 'Wysyłanie zdjęć' })).toBeInTheDocument();
      expect(within(roomView.container).queryByRole('list', { name: 'Wysyłanie zdjęć' })).toBeNull();
      expect(within(projectView.container).queryByRole('list', { name: 'Wysyłanie zdjęć' })).toBeNull();
      for (const view of [surfaceView, roomView, projectView]) view.unmount();
    });

    it('an aggregated list reloads on a finished upload but leaves the queue row to the surface section', async () => {
      const roomView = render(
        <I18nProvider>
          <PhotoSection projectId={PROJECT_ID} context="ROOM" targetId={ROOM_ID} locationLabel="x" />
        </I18nProvider>,
      );
      await waitFor(() => expect(fetchPhotos).toHaveBeenCalledTimes(1));
      const { getPhotoUploadQueue } = await import('../hooks/usePhotoUploadQueue');
      await startUpload({ projectId: PROJECT_ID, context: 'SURFACE', surfaceId: SURFACE_ID, roomId: ROOM_ID });
      await act(async () => uploads[0].resolve(uploadResult(makeItem())));
      await waitFor(() => expect(fetchPhotos).toHaveBeenCalledTimes(2));
      expect(getPhotoUploadQueue().getItems()[0].state).toBe('done'); // not dismissed by the aggregated list
      roomView.unmount();
    });
  });
});

describe('PhotoSection — options (archive view, category filter)', () => {
  it('hides secondary actions behind "Opcje"', async () => {
    renderSection();
    const toggle = await screen.findByRole('button', { name: 'Opcje zdjęć' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveClass('min-h-11');
    expect(screen.queryByRole('button', { name: 'Pokaż archiwum' })).toBeNull();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: 'Pokaż archiwum' })).toBeInTheDocument();
  });

  it('switches to the archive view (archived=true) and back', async () => {
    renderSection();
    fireEvent.click(await screen.findByRole('button', { name: 'Opcje zdjęć' }));
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([]));
    fireEvent.click(screen.getByRole('button', { name: 'Pokaż archiwum' }));
    await waitFor(() => expect(lastListParams()?.archived).toBe(true));
    expect(await screen.findByText('Archiwum jest puste.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Archiwum zdjęć' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ukryj archiwum' }));
    await waitFor(() => expect(lastListParams()?.archived).toBe(false));
  });

  it('category chips exist only in the project-wide list and filter on the server', async () => {
    renderSection({ context: 'PROJECT', targetId: undefined, locationLabel: 'Obiekt' });
    fireEvent.click(await screen.findByRole('button', { name: 'Opcje zdjęć' }));
    const group = screen.getByRole('group', { name: 'Kategoria' });
    expect(within(group).getAllByRole('button')).toHaveLength(9); // all + 8
    fireEvent.click(within(group).getByRole('button', { name: 'Wada' }));
    await waitFor(() => expect(lastListParams()?.category).toBe('DEFECT'));
    expect(within(group).getByRole('button', { name: 'Wada' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(within(group).getByRole('button', { name: 'Wszystkie' }));
    await waitFor(() => expect(lastListParams()?.category).toBeUndefined());
  });

  it('a room list (everything in the room) has the category chips too; a surface section has none', async () => {
    const room = renderSection({ context: 'ROOM', targetId: ROOM_ID, allowUpload: false, locationLabel: 'x' });
    fireEvent.click(await within(room.container).findByRole('button', { name: 'Opcje zdjęć' }));
    expect(within(room.container).getByRole('group', { name: 'Kategoria' })).toBeInTheDocument();
    room.unmount();

    renderSection();
    fireEvent.click(await screen.findByRole('button', { name: 'Opcje zdjęć' }));
    expect(screen.queryByRole('group', { name: 'Kategoria' })).toBeNull();
  });
});

describe('PhotoSection — viewer integration', () => {
  async function openFirst(items = [makeItem(), makeItem()]) {
    vi.mocked(fetchPhotos).mockResolvedValue(listPage(items));
    vi.mocked(fetchPhoto).mockImplementation(async (_p, id) => detailFor(items.find((i) => i.asset.id === id)!));
    const view = renderSection();
    const tiles = await screen.findAllByRole('button', { name: /23\.06\.2026/ });
    fireEvent.click(tiles[0]);
    await screen.findByRole('dialog');
    await screen.findAllByRole('img');
    return { items, ...view };
  }

  it('renders the viewer at the top level of the page, outside the card (no inherited spacing, stacking or clipping)', async () => {
    const { container } = await openFirst();
    const dialog = screen.getByRole('dialog');
    expect(dialog.parentElement).toBe(document.body);
    expect(container.contains(dialog)).toBe(false);
    expect(dialog).toHaveClass('fixed', 'inset-0');
  });

  it('opens the viewer on a tapped tile and closes it back to the grid', async () => {
    await openFirst();
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('archiving in the viewer removes the tile, corrects the count of ITS context and moves on', async () => {
    const { items, onCountAdjust } = await openFirst();
    vi.mocked(archivePhotoAttachment).mockResolvedValue({ ...items[0].attachment, archived_at: '2026-06-23T12:00:00Z' });
    fireEvent.click(screen.getByRole('button', { name: 'Archiwizuj' }));
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Archiwizuj' }));
    await waitFor(() => expect(onCountAdjust).toHaveBeenCalledWith('ROOM', ROOM_ID, -1, ROOM_ID));
    await waitFor(() => expect(screen.getByText('1 / 1')).toBeInTheDocument());
  });

  it('archiving the last photo closes the viewer', async () => {
    const { items, onCountAdjust } = await openFirst([makeItem()]);
    vi.mocked(archivePhotoAttachment).mockResolvedValue({ ...items[0].attachment, archived_at: 'x' });
    fireEvent.click(screen.getByRole('button', { name: 'Archiwizuj' }));
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Archiwizuj' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(onCountAdjust).toHaveBeenCalledWith('ROOM', ROOM_ID, -1, ROOM_ID);
    expect(await screen.findByText('Brak zdjęć.')).toBeInTheDocument();
  });

  it('restoring from the archive view raises the count again', async () => {
    const archivedItem = makeItem({ attachment: { archived_at: '2026-06-23T12:00:00Z' } });
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([]));
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(archivedItem));
    const { onCountAdjust } = renderSection();
    fireEvent.click(await screen.findByRole('button', { name: 'Opcje zdjęć' }));
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([archivedItem]));
    fireEvent.click(screen.getByRole('button', { name: 'Pokaż archiwum' }));
    fireEvent.click((await screen.findAllByRole('button', { name: /23\.06\.2026/ }))[0]);
    await screen.findByRole('dialog');
    vi.mocked(restorePhotoAttachment).mockResolvedValue({ ...archivedItem.attachment, archived_at: null });
    fireEvent.click(await screen.findByRole('button', { name: 'Przywróć' }));
    await waitFor(() => expect(onCountAdjust).toHaveBeenCalledWith('ROOM', ROOM_ID, 1, ROOM_ID));
  });

  it('a category change in the viewer shows on the tile at once', async () => {
    const { items } = await openFirst();
    const { patchPhotoAttachment } = await import('../api/photos');
    vi.mocked(patchPhotoAttachment).mockResolvedValue({ ...items[0].attachment, category: 'DEFECT' });
    fireEvent.change(screen.getByLabelText('Kategoria'), { target: { value: 'DEFECT' } });
    await waitFor(() => expect(screen.getAllByText('Wada').length).toBeGreaterThan(0));
  });
});

describe('PhotoSection — signed links', () => {
  it('refreshes the list when the app returns after the links expired, not before', async () => {
    const past = new Date(Date.now() - 60_000).toISOString();
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()], null, past));
    renderSection();
    await screen.findByRole('list');
    expect(fetchPhotos).toHaveBeenCalledTimes(1);
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(fetchPhotos).toHaveBeenCalledTimes(1);
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(fetchPhotos).toHaveBeenCalledTimes(2));
  });

  it('does not refetch while the links are still valid', async () => {
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()]));
    renderSection();
    await screen.findByRole('list');
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(fetchPhotos).toHaveBeenCalledTimes(1);
  });

  it('a thumbnail that fails to load triggers ONE refetch, never a loop', async () => {
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()]));
    renderSection();
    const image = await screen.findByRole('img');
    fireEvent.error(image);
    await waitFor(() => expect(fetchPhotos).toHaveBeenCalledTimes(2));
    fireEvent.error(await screen.findByRole('img'));
    fireEvent.error(screen.getByRole('img'));
    await act(async () => undefined);
    expect(fetchPhotos).toHaveBeenCalledTimes(2);
  });
});

describe('PhotoSection — mobile and locales', () => {
  it('the section shrinks with its card and uses no fixed pixel widths', async () => {
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()]));
    const { container } = renderSection();
    await screen.findByRole('list');
    expect(container.firstElementChild).toHaveClass('min-w-0', 'space-y-3');
    expect(container.innerHTML).not.toMatch(/\bw-\[\d+px\]|\bwidth:\s*\d+px/);
  });

  it('renders in Russian: buttons, notes and the caption source', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()]));
    renderSection({ locationLabel: 'Гостиная → Стена 1' });
    expect(await screen.findByRole('button', { name: 'Сделать фото' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Из галереи' })).toBeInTheDocument();
    await screen.findByText('Гостиная → Стена 1 → 23.06.2026 (10:15) · снято в приложении');
    expect(screen.getByRole('button', { name: 'Опции фото' })).toBeInTheDocument();
  });

  it('has its own theme surface, so it stays readable inside a fixed-white host card in the dark scheme', async () => {
    document.documentElement.setAttribute('data-color-scheme', 'dark');
    const { container } = renderSection();
    const root = container.firstElementChild as HTMLElement;
    expect(root).toHaveClass('bg-[var(--tg-theme-secondary-bg-color)]', 'text-[var(--tg-theme-text-color)]', 'rounded-xl', 'p-3');
    await screen.findByText('Brak zdjęć.');
    document.documentElement.removeAttribute('data-color-scheme');
  });

  it('uses theme tokens only, so the dark scheme needs no extra rules', async () => {
    document.documentElement.setAttribute('data-color-scheme', 'dark');
    vi.mocked(fetchPhotos).mockResolvedValue(listPage([makeItem()]));
    const { container } = renderSection();
    await screen.findByRole('list');
    fireEvent.click(screen.getByRole('button', { name: 'Opcje zdjęć' }));
    expect(container.innerHTML).toContain('var(--tg-');
    expect(container.innerHTML).not.toMatch(/bg-white|text-slate|border-slate|bg-slate/);
    document.documentElement.removeAttribute('data-color-scheme');
  });
});
