import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { ArchivedPhotoItem, PhotoArchiveResponse, PhotoPlace } from '../types/photo';
import { detailFor, makeItem } from '../test/photoFixtures';
import { ArchivePhotos } from './ArchivePhotos';

vi.mock('../api/photos', async () => {
  const actual = await vi.importActual<typeof import('../api/photos')>('../api/photos');
  return {
    ...actual,
    fetchPhotoArchive: vi.fn(),
    fetchPhoto: vi.fn(),
    trashPhotoAttachment: vi.fn(),
    untrashPhotoAttachment: vi.fn(),
    restorePhotoAttachment: vi.fn(),
    fetchPhotoPurgePreview: vi.fn(),
    purgePhotoAttachment: vi.fn(),
  };
});
import {
  fetchPhoto,
  fetchPhotoArchive,
  fetchPhotoPurgePreview,
  restorePhotoAttachment,
  trashPhotoAttachment,
  untrashPhotoAttachment,
} from '../api/photos';

const OTHER_PROJECT = 'ffffffff-ffff-4fff-8fff-ffffffffffff';
const NO_PLACE: PhotoPlace = { room_name: null, surface_name: null, surface_type: null, opening_type: null, opening_name: null, payment_title: null, payment_kind: null };

function archived(
  over: { project_id?: string; project_name?: string; place?: Partial<PhotoPlace>; trashed?: boolean; annotation_count?: number } = {},
): ArchivedPhotoItem {
  const base = makeItem({
    attachment: {
      archived_at: '2026-06-23T12:00:00Z',
      trashed_at: over.trashed ? '2026-06-23T13:00:00Z' : null,
      ...(over.project_id ? { project_id: over.project_id } : {}),
    },
    annotation_count: over.annotation_count,
  });
  return {
    ...base,
    project_id: over.project_id ?? base.attachment.project_id,
    project_name: over.project_name ?? 'Mieszkanie Mokotów',
    place: { ...NO_PLACE, room_name: 'Salon', surface_name: 'Ściana 1', surface_type: 'WALL', ...over.place },
  };
}

const page = (items: ArchivedPhotoItem[], totals: { archived: number; trashed: number } = { archived: items.length, trashed: 0 }): PhotoArchiveResponse => ({
  items,
  archived_total: totals.archived,
  trashed_total: totals.trashed,
  urls_expire_at: '2099-01-01T00:00:00Z',
});

function renderPhotos(props: Partial<React.ComponentProps<typeof ArchivePhotos>> = {}) {
  const onTotals = vi.fn();
  render(
    <I18nProvider>
      <ArchivePhotos active onTotals={onTotals} {...props} />
    </I18nProvider>,
  );
  return { onTotals };
}

beforeEach(() => {
  localStorage.clear();
  vi.mocked(fetchPhotoArchive).mockReset();
  vi.mocked(fetchPhoto).mockReset();
  vi.mocked(trashPhotoAttachment).mockReset();
  vi.mocked(untrashPhotoAttachment).mockReset();
  vi.mocked(restorePhotoAttachment).mockReset();
  vi.mocked(fetchPhotoPurgePreview).mockReset();
});

describe('ArchivePhotos (archive cleanup AC-3a)', () => {
  it('asks for the archive of all objects and names the object and the place of every photo', async () => {
    const item = archived();
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([item], { archived: 1, trashed: 2 }));
    const { onTotals } = renderPhotos();
    const open = await screen.findByRole('button', { name: /Mieszkanie Mokotów → Salon → Ściana 1 → 23\.06\.2026/ });
    expect(open).toBeInTheDocument();
    expect(fetchPhotoArchive).toHaveBeenCalledWith('archived', 100);
    expect(screen.getByRole('button', { name: 'Archiwum (1)', pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Kosz (2)' })).toBeInTheDocument();
    expect(onTotals).toHaveBeenCalledWith({ archived: 1, trashed: 2 });
  });

  it('a photo of the object itself has the object name only, an opening photo names the opening', async () => {
    vi.mocked(fetchPhotoArchive).mockResolvedValue(
      page([
        archived({ project_name: 'Dom', place: { room_name: null, surface_name: null, surface_type: null } }),
        archived({ place: { opening_type: 'DOOR', opening_name: 'wejściowe' } }),
      ]),
    );
    renderPhotos();
    expect(await screen.findByRole('button', { name: /^Dom → 23\.06\.2026/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Mieszkanie Mokotów → Salon → Ściana 1 → Drzwi \(wejściowe\) → 23\.06\.2026/ })).toBeInTheDocument();
  });

  it('tells how a photo gets to the trash and how it leaves it', async () => {
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([archived()]));
    renderPhotos();
    await screen.findByRole('list');
    expect(screen.getByText(/Otwórz zdjęcie, aby je przywrócić, przenieść do kosza lub usunąć na zawsze/)).toBeInTheDocument();
  });

  it('the trash view asks for the trash and has its own empty state and hint', async () => {
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([archived()], { archived: 1, trashed: 0 }));
    renderPhotos();
    await screen.findByRole('list');
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([], { archived: 1, trashed: 0 }));
    fireEvent.click(screen.getByRole('button', { name: /^Kosz/ }));
    expect(await screen.findByLabelText('archive-empty-photos')).toHaveTextContent('Kosz jest pusty.');
    expect(fetchPhotoArchive).toHaveBeenLastCalledWith('trashed', 100);
    expect(screen.getByText(/nie zostały usunięte/)).toBeInTheDocument();
  });

  it('the viewer works on the project of the photo: "Do kosza" calls that project, the list is read again, the viewer closes', async () => {
    const item = archived({ project_id: OTHER_PROJECT });
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([item], { archived: 1, trashed: 0 }));
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    renderPhotos();
    fireEvent.click(await screen.findByRole('button', { name: /23\.06\.2026/ }));
    await screen.findByRole('dialog');
    expect(fetchPhoto).toHaveBeenCalledWith(OTHER_PROJECT, item.asset.id);

    vi.mocked(trashPhotoAttachment).mockResolvedValue({ ...item.attachment, trashed_at: '2026-06-23T13:00:00Z' });
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([], { archived: 0, trashed: 1 }));
    fireEvent.click(screen.getByRole('button', { name: 'photo-trash' }));
    await waitFor(() => expect(trashPhotoAttachment).toHaveBeenCalledWith(OTHER_PROJECT, item.attachment.id));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // the totals of both views follow the change
    expect(await screen.findByRole('button', { name: 'Kosz (1)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Archiwum (0)' })).toBeInTheDocument();
    expect(screen.getByLabelText('archive-empty-photos')).toBeInTheDocument();
  });

  it('in the trash: "Wyjmij z kosza" and the deletion for good go to the project of the photo', async () => {
    const item = archived({ project_id: OTHER_PROJECT, trashed: true });
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([], { archived: 0, trashed: 1 }));
    renderPhotos();
    await screen.findByLabelText('archive-empty-photos');
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([item], { archived: 0, trashed: 1 }));
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    fireEvent.click(screen.getByRole('button', { name: /^Kosz/ }));
    fireEvent.click(await screen.findByRole('button', { name: /23\.06\.2026/ }));
    await screen.findByRole('dialog');
    expect(screen.queryByRole('button', { name: 'photo-trash' })).toBeNull();

    vi.mocked(fetchPhotoPurgePreview).mockResolvedValue({
      attachment_id: item.attachment.id, trashed: true, can_purge: true, annotations: 0, other_attachments: 0,
      deletes_files: true, files: 3, bytes: 2048, may_be_in_backups: true, blockers: [],
    });
    fireEvent.click(screen.getByRole('button', { name: 'photo-purge' }));
    await waitFor(() => expect(fetchPhotoPurgePreview).toHaveBeenCalledWith(OTHER_PROJECT, item.attachment.id));

    vi.mocked(untrashPhotoAttachment).mockResolvedValue({ ...item.attachment, trashed_at: null });
    fireEvent.click(await screen.findByRole('button', { name: 'photo-purge-cancel' }));
    fireEvent.click(screen.getByRole('button', { name: 'photo-untrash' }));
    await waitFor(() => expect(untrashPhotoAttachment).toHaveBeenCalledWith(OTHER_PROJECT, item.attachment.id));
  });

  it('says when the list shows only the newest part of a large archive', async () => {
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([archived(), archived()], { archived: 130, trashed: 0 }));
    renderPhotos();
    expect(await screen.findByText('Pokazano najnowsze 2 z 130.')).toBeInTheDocument();
  });

  it('a failed load is told with a retry that loads again', async () => {
    vi.mocked(fetchPhotoArchive).mockRejectedValueOnce(new ApiError('boom', 0, 'NETWORK_ERROR'));
    renderPhotos();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([archived()]));
    fireEvent.click(screen.getByRole('button', { name: 'archive-photos-retry' }));
    expect(await screen.findByRole('button', { name: /23\.06\.2026/ })).toBeInTheDocument();
  });

  it('inactive: shows nothing but still reports the totals, so the tab can show its number', async () => {
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([archived()], { archived: 1, trashed: 1 }));
    const { onTotals } = renderPhotos({ active: false });
    await waitFor(() => expect(onTotals).toHaveBeenCalledWith({ archived: 1, trashed: 1 }));
    expect(screen.queryByLabelText('archive-photos')).toBeNull();
  });

  it('the Russian texts are used in the Russian interface', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(fetchPhotoArchive).mockResolvedValue(page([archived()], { archived: 1, trashed: 0 }));
    renderPhotos();
    await screen.findByRole('list');
    expect(screen.getByRole('button', { name: 'Архив (1)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Корзина (0)' })).toBeInTheDocument();
    expect(within(screen.getByLabelText('archive-photos')).getByText(/Откройте фото, чтобы восстановить его/)).toBeInTheDocument();
  });

  it('names a receipt by its object, the settlements and its record: no room, no surface (IA-3)', async () => {
    vi.mocked(fetchPhotoArchive).mockResolvedValue(
      page([
        archived({
          place: { room_name: null, surface_name: null, surface_type: null, payment_title: 'Farba i grunt', payment_kind: 'EXPENSE' },
        }),
      ]),
    );
    renderPhotos();
    expect(await screen.findByRole('button', { name: /Mieszkanie Mokotów → Faktury i zaliczki → Farba i grunt → 23\.06\.2026/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Salon/ })).toBeNull();
  });

  it('says the same in Russian (IA-3)', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(fetchPhotoArchive).mockResolvedValue(
      page([archived({ place: { room_name: null, surface_name: null, surface_type: null, payment_title: 'Краска', payment_kind: 'EXPENSE' } })]),
    );
    renderPhotos();
    expect(await screen.findByRole('button', { name: /Mieszkanie Mokotów → Фактуры и авансы → Краска/ })).toBeInTheDocument();
  });
});
