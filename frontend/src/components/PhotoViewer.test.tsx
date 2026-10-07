import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { PhotoBackContext } from '../hooks/PhotoBackContext';
import { I18nProvider } from '../hooks/useI18n';
import { PhotoListItem } from '../types/photo';
import { detailFor, makeItem, PROJECT_ID } from '../test/photoFixtures';
import { PhotoViewer } from './PhotoViewer';

vi.mock('../api/photos', () => ({
  fetchPhoto: vi.fn(),
  patchPhotoAttachment: vi.fn(),
  archivePhotoAttachment: vi.fn(),
  restorePhotoAttachment: vi.fn(),
}));
import { archivePhotoAttachment, fetchPhoto, patchPhotoAttachment, restorePhotoAttachment } from '../api/photos';

const err = (status: number, code: string) => new ApiError('server english text', status, code);

interface Setup {
  items: PhotoListItem[];
  index?: number;
  archivedView?: boolean;
  registry?: { register: (close: () => void) => () => void };
}

function setup({ items, index = 0, archivedView = false, registry }: Setup) {
  const handlers = {
    onIndexChange: vi.fn(),
    onClose: vi.fn(),
    onAttachmentUpdated: vi.fn(),
    onAttachmentRemoved: vi.fn(),
    onRefresh: vi.fn(),
  };
  const ui = (at: number) => (
    <I18nProvider>
      <PhotoBackContext.Provider value={registry ?? null}>
        <PhotoViewer
          projectId={PROJECT_ID}
          items={items}
          index={at}
          archivedView={archivedView}
          captionFor={(item) => `line-${item.attachment.position}`}
          {...handlers}
        />
      </PhotoBackContext.Provider>
    </I18nProvider>
  );
  const view = render(ui(index));
  // Same tree shape as the first render, so the viewer instance (and its link cache) survives.
  const rerenderAt = (at: number) => view.rerender(ui(at));
  return { ...handlers, ...view, rerenderAt };
}

async function ready() {
  await waitFor(() => expect(screen.getByRole('img')).toBeInTheDocument());
}

beforeEach(() => {
  localStorage.clear();
  document.body.style.overflow = '';
  vi.mocked(fetchPhoto).mockReset().mockImplementation(async (_p, assetId) => {
    throw new Error(`unexpected fetchPhoto ${assetId}`);
  });
  vi.mocked(patchPhotoAttachment).mockReset();
  vi.mocked(archivePhotoAttachment).mockReset();
  vi.mocked(restorePhotoAttachment).mockReset();
});

describe('PhotoViewer — display and navigation', () => {
  it('loads the detail of the open photo and shows its DISPLAY image (lists carry thumbnails only)', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    expect(screen.getByText('Ładowanie zdjęcia…')).toBeInTheDocument();
    await ready();
    expect(fetchPhoto).toHaveBeenCalledWith(PROJECT_ID, item.asset.id);
    const image = screen.getByRole('img');
    expect(image).toHaveAttribute('src', `https://r2.example/d/${item.asset.id}.jpg`);
    expect(image).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(image).toHaveClass('object-contain');
  });

  it('shows the caption line, both timestamps and the counter', async () => {
    const item = makeItem({ asset: { captured_at: '2026-06-23T10:15:00', uploaded_at: '2026-06-23T08:20:00Z' } });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item, makeItem()] });
    await ready();
    expect(screen.getByTestId('viewer-caption-line')).toHaveTextContent('line-');
    expect(screen.getByText('Zrobiono:')).toBeInTheDocument();
    expect(screen.getByText('23.06.2026 (10:15)')).toBeInTheDocument();
    expect(screen.getByText('Dodano:')).toBeInTheDocument();
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
  });

  it('adds the "older than the add date" hint only when the photo is more than a day older', async () => {
    const old = makeItem({ asset: { captured_at: '2026-06-01T10:00:00', uploaded_at: '2026-06-23T08:20:00Z' } });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(old));
    const first = setup({ items: [old] });
    await ready();
    expect(screen.getByText('Zdjęcie starsze niż data dodania')).toBeInTheDocument();
    first.unmount();

    const fresh = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(fresh));
    setup({ items: [fresh] });
    await ready();
    expect(screen.queryByText('Zdjęcie starsze niż data dodania')).toBeNull();
  });

  it('moves between photos with previous / next, disabled at the ends, 44 px targets', async () => {
    const items = [makeItem(), makeItem(), makeItem()];
    vi.mocked(fetchPhoto).mockImplementation(async (_p, id) => detailFor(items.find((i) => i.asset.id === id)!));
    const { onIndexChange } = setup({ items, index: 1 });
    await ready();
    const previous = screen.getByRole('button', { name: 'Poprzednie zdjęcie' });
    const next = screen.getByRole('button', { name: 'Następne zdjęcie' });
    expect(previous).toHaveClass('min-h-11', 'min-w-11');
    expect(next).toHaveClass('min-h-11', 'min-w-11');
    fireEvent.click(next);
    await waitFor(() => expect(onIndexChange).toHaveBeenCalledWith(2));
    fireEvent.click(previous);
    await waitFor(() => expect(onIndexChange).toHaveBeenCalledWith(0));
  });

  it('disables previous on the first and next on the last photo', async () => {
    const items = [makeItem(), makeItem()];
    vi.mocked(fetchPhoto).mockImplementation(async (_p, id) => detailFor(items.find((i) => i.asset.id === id)!));
    const first = setup({ items, index: 0 });
    await ready();
    expect(screen.getByRole('button', { name: 'Poprzednie zdjęcie' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Następne zdjęcie' })).toBeEnabled();
    first.unmount();
    setup({ items, index: 1 });
    await ready();
    expect(screen.getByRole('button', { name: 'Następne zdjęcie' })).toBeDisabled();
  });

  it('fetches each photo once and reuses fresh links when going back', async () => {
    const items = [makeItem(), makeItem()];
    vi.mocked(fetchPhoto).mockImplementation(async (_p, id) => detailFor(items.find((i) => i.asset.id === id)!));
    const view = setup({ items, index: 0 });
    await ready();
    view.rerenderAt(1);
    await waitFor(() => expect(fetchPhoto).toHaveBeenCalledTimes(2));
    await ready();
    view.rerenderAt(0);
    await ready();
    expect(screen.getByRole('img')).toHaveAttribute('src', `https://r2.example/d/${items[0].asset.id}.jpg`);
    expect(fetchPhoto).toHaveBeenCalledTimes(2);
  });

  it('refetches a photo whose signed links are about to expire', async () => {
    const items = [makeItem(), makeItem()];
    const soon = new Date(Date.now() + 10_000).toISOString(); // inside the 30 s margin
    vi.mocked(fetchPhoto).mockImplementation(async (_p, id) =>
      detailFor(items.find((i) => i.asset.id === id)!, { urls_expire_at: soon }),
    );
    const view = setup({ items, index: 0 });
    await ready();
    view.rerenderAt(1);
    await waitFor(() => expect(fetchPhoto).toHaveBeenCalledTimes(2));
    view.rerenderAt(0);
    await waitFor(() => expect(fetchPhoto).toHaveBeenCalledTimes(3));
  });

  it('offers no download, share, delete or original', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const { container } = setup({ items: [item] });
    await ready();
    expect(container.querySelector('a[download], a[href]')).toBeNull();
    const names = screen.getAllByRole('button').map((b) => (b.getAttribute('aria-label') ?? b.textContent ?? '').toLowerCase());
    expect(names.join('|')).not.toMatch(/pobierz|udostęp|usuń|oryginał|download|share|delete|original/);
  });
});

describe('PhotoViewer — image and detail failures', () => {
  it('refetches the links ONCE when the image fails to load, then shows a message and a retry', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    await ready();
    fireEvent.error(screen.getByRole('img'));
    await waitFor(() => expect(fetchPhoto).toHaveBeenCalledTimes(2));
    await ready();
    fireEvent.error(screen.getByRole('img'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Nie można wyświetlić zdjęcia.'));
    expect(fetchPhoto).toHaveBeenCalledTimes(2); // no loop

    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }));
    await waitFor(() => expect(fetchPhoto).toHaveBeenCalledTimes(3));
  });

  it('says so when the server sent no display URL (media unavailable)', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { display_url: null }));
    setup({ items: [item] });
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Nie można wyświetlić zdjęcia.'));
  });

  it('shows a localized message for a failed detail request, never the server text', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockRejectedValue(err(503, 'PHOTO_STORAGE_UNAVAILABLE'));
    setup({ items: [item] });
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Magazyn zdjęć jest chwilowo niedostępny.'));
    expect(screen.getByRole('alert')).not.toHaveTextContent('server english text');
  });

  it('closes and asks the host to refetch when the photo no longer exists', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockRejectedValue(err(404, 'PHOTO_NOT_FOUND'));
    const { onClose, onRefresh } = setup({ items: [item] });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});

describe('PhotoViewer — editing', () => {
  async function open(over: Parameters<typeof makeItem>[0] = {}) {
    const item = makeItem(over);
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const view = setup({ items: [item] });
    await ready();
    return { item, ...view };
  }

  it('saves a changed caption on blur, trimmed, and reports the updated attachment', async () => {
    const { item, onAttachmentUpdated } = await open();
    const updated = { ...item.attachment, caption: 'Pęknięcie' };
    vi.mocked(patchPhotoAttachment).mockResolvedValue(updated);
    const box = screen.getByLabelText('Opis');
    expect(box).toHaveAttribute('maxlength', '1000');
    fireEvent.change(box, { target: { value: '  Pęknięcie  ' } });
    expect(screen.getByRole('button', { name: 'Zapisz' })).toBeInTheDocument();
    fireEvent.blur(box);
    await waitFor(() => expect(patchPhotoAttachment).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, { caption: 'Pęknięcie' }));
    await waitFor(() => expect(onAttachmentUpdated).toHaveBeenCalledWith(updated));
    expect(await screen.findByText('Zapisano')).toBeInTheDocument();
  });

  it('clears a caption with null, and does not call the API when nothing changed', async () => {
    const { item } = await open({ attachment: { caption: 'stary' } });
    vi.mocked(patchPhotoAttachment).mockResolvedValue({ ...item.attachment, caption: null });
    const box = screen.getByLabelText('Opis');
    fireEvent.blur(box);
    expect(patchPhotoAttachment).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: '   ' } });
    fireEvent.blur(box);
    await waitFor(() => expect(patchPhotoAttachment).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, { caption: null }));
  });

  it('the Cancel button restores the stored caption without a request', async () => {
    await open({ attachment: { caption: 'stary' } });
    const box = screen.getByLabelText('Opis') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'nowy' } });
    fireEvent.click(screen.getByRole('button', { name: 'Anuluj' }));
    expect(box.value).toBe('stary');
    expect(patchPhotoAttachment).not.toHaveBeenCalled();
  });

  it('changes the category at once with a PATCH, from the 8 backend values', async () => {
    const { item, onAttachmentUpdated } = await open();
    const select = screen.getByLabelText('Kategoria') as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual([
      'GENERAL', 'BEFORE', 'DEFECT', 'PREPARATION', 'IN_PROGRESS', 'HIDDEN_WORK', 'AFTER', 'DAMAGE',
    ]);
    expect(select).toHaveClass('min-h-11');
    const updated = { ...item.attachment, category: 'DEFECT' as const };
    vi.mocked(patchPhotoAttachment).mockResolvedValue(updated);
    fireEvent.change(select, { target: { value: 'DEFECT' } });
    await waitFor(() => expect(patchPhotoAttachment).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, { category: 'DEFECT' }));
    await waitFor(() => expect(onAttachmentUpdated).toHaveBeenCalledWith(updated));
  });

  it('toggles "include in report" with a PATCH; default off', async () => {
    const { item } = await open();
    const toggle = screen.getByLabelText('Uwzględnij w raporcie') as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    vi.mocked(patchPhotoAttachment).mockResolvedValue({ ...item.attachment, include_in_report: true });
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(patchPhotoAttachment).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, { include_in_report: true }),
    );
  });

  it('shows a localized error when saving fails and keeps the draft', async () => {
    await open();
    vi.mocked(patchPhotoAttachment).mockRejectedValue(err(0, 'NETWORK_ERROR'));
    const box = screen.getByLabelText('Opis') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'szkic' } });
    fireEvent.blur(box);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Brak połączenia. Spróbuj ponownie.'));
    expect(box.value).toBe('szkic');
  });

  it('uses 16 px text in form controls so iOS does not zoom (text-base) and 44 px controls', async () => {
    await open();
    expect(screen.getByLabelText('Opis')).toHaveClass('text-base');
    expect(screen.getByLabelText('Kategoria')).toHaveClass('text-base', 'min-h-11');
    expect(screen.getByLabelText('Uwzględnij w raporcie').closest('label')).toHaveClass('min-h-11');
  });
});

describe('PhotoViewer — archive and restore (in this context only)', () => {
  it('archives after an explicit confirmation', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const archived = { ...item.attachment, archived_at: '2026-06-23T12:00:00Z' };
    vi.mocked(archivePhotoAttachment).mockResolvedValue(archived);
    const { onAttachmentRemoved } = setup({ items: [item] });
    await ready();

    fireEvent.click(screen.getByRole('button', { name: 'Archiwizuj' }));
    expect(archivePhotoAttachment).not.toHaveBeenCalled(); // one tap only asks
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Zarchiwizować to zdjęcie?');
    fireEvent.click(screen.getByRole('button', { name: 'Archiwizuj' }));
    await waitFor(() => expect(archivePhotoAttachment).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id));
    await waitFor(() => expect(onAttachmentRemoved).toHaveBeenCalledWith(archived, 'archived'));
  });

  it('cancelling the confirmation does nothing', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Archiwizuj' }));
    fireEvent.click(screen.getByRole('button', { name: 'Anuluj' }));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(archivePhotoAttachment).not.toHaveBeenCalled();
  });

  it('in the archive view the only action is Restore', async () => {
    const item = makeItem({ attachment: { archived_at: '2026-06-23T12:00:00Z' } });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const restored = { ...item.attachment, archived_at: null };
    vi.mocked(restorePhotoAttachment).mockResolvedValue(restored);
    const { onAttachmentRemoved } = setup({ items: [item], archivedView: true });
    await ready();
    expect(screen.queryByRole('button', { name: 'Archiwizuj' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Przywróć' }));
    await waitFor(() => expect(restorePhotoAttachment).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id));
    await waitFor(() => expect(onAttachmentRemoved).toHaveBeenCalledWith(restored, 'restored'));
  });

  it('shows "already exists" when restoring would duplicate an active photo (409)', async () => {
    const item = makeItem({ attachment: { archived_at: '2026-06-23T12:00:00Z' } });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    vi.mocked(restorePhotoAttachment).mockRejectedValue(err(409, 'PHOTO_ATTACHMENT_DUPLICATE'));
    const { onAttachmentRemoved } = setup({ items: [item], archivedView: true });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Przywróć' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Aktywne zdjęcie już istnieje.'));
    expect(onAttachmentRemoved).not.toHaveBeenCalled();
  });
});

describe('PhotoViewer — closing, back navigation, unsaved caption', () => {
  it('closes with the visible close button and Escape', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const { onClose } = setup({ items: [item] });
    await ready();
    const close = screen.getByRole('button', { name: 'Zamknij' });
    expect(close).toHaveClass('min-h-11', 'min-w-11');
    fireEvent.click(close);
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(2));
  });

  it('registers with the Telegram BackButton context while open and unregisters on unmount', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const unregister = vi.fn();
    let closer: (() => void) | undefined;
    const registry = {
      register: vi.fn((close: () => void) => {
        closer = close;
        return unregister;
      }),
    };
    const { onClose, unmount } = setup({ items: [item], registry });
    await ready();
    expect(registry.register).toHaveBeenCalledTimes(1);
    await act(async () => closer?.());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    unmount();
    expect(unregister).toHaveBeenCalled();
  });

  it('the registered back handler always runs the latest close logic (saves an unsaved caption)', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    vi.mocked(patchPhotoAttachment).mockResolvedValue({ ...item.attachment, caption: 'x' });
    let closer: (() => void) | undefined;
    const registry = { register: (close: () => void) => ((closer = close), () => undefined) };
    const { onClose } = setup({ items: [item], registry });
    await ready();
    fireEvent.change(screen.getByLabelText('Opis'), { target: { value: 'x' } });
    await act(async () => closer?.());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(patchPhotoAttachment).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, { caption: 'x' });
  });

  it('saves a pending caption before closing', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    vi.mocked(patchPhotoAttachment).mockResolvedValue({ ...item.attachment, caption: 'x' });
    const { onClose } = setup({ items: [item] });
    await ready();
    fireEvent.change(screen.getByLabelText('Opis'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(patchPhotoAttachment).toHaveBeenCalledTimes(1);
  });

  it('stays open and shows the error when the pending caption cannot be saved', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    vi.mocked(patchPhotoAttachment).mockRejectedValue(err(0, 'NETWORK_ERROR'));
    const { onClose } = setup({ items: [item] });
    await ready();
    fireEvent.change(screen.getByLabelText('Opis'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij' }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(onClose).not.toHaveBeenCalled();
  });

  it('saves a pending caption before moving to the next photo', async () => {
    const items = [makeItem(), makeItem()];
    vi.mocked(fetchPhoto).mockImplementation(async (_p, id) => detailFor(items.find((i) => i.asset.id === id)!));
    vi.mocked(patchPhotoAttachment).mockResolvedValue({ ...items[0].attachment, caption: 'x' });
    const { onIndexChange } = setup({ items });
    await ready();
    fireEvent.change(screen.getByLabelText('Opis'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Następne zdjęcie' }));
    await waitFor(() => expect(onIndexChange).toHaveBeenCalledWith(1));
    expect(patchPhotoAttachment).toHaveBeenCalledTimes(1);
  });

  it('is a modal dialog that locks page scroll while open and restores it after', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const { unmount } = setup({ items: [item] });
    await ready();
    expect(screen.getByRole('dialog', { name: 'Podgląd zdjęcia' })).toHaveAttribute('aria-modal', 'true');
    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    expect(document.body.style.overflow).toBe('');
  });
});

describe('PhotoViewer — mobile, locales, theme', () => {
  it('is full screen, scrolls its own content, never scrolls the page sideways', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    await ready();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveClass('fixed', 'inset-0');
    expect(dialog.firstElementChild).toHaveClass('overflow-y-auto', 'overflow-x-hidden');
    expect(dialog.innerHTML).not.toMatch(/\bw-\[\d+px\]|\bwidth:\s*\d+px/);
  });

  it('renders in Russian, with a long caption line wrapping', async () => {
    localStorage.setItem('locale', 'ru');
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    await ready();
    expect(screen.getByRole('dialog', { name: 'Просмотр фото' })).toBeInTheDocument();
    expect(screen.getByLabelText('Подпись')).toBeInTheDocument();
    expect(screen.getByLabelText('Включить в отчёт')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'В архив' })).toHaveClass('min-h-11', 'w-full');
    expect(screen.getByTestId('viewer-caption-line')).toHaveClass('break-words');
  });

  it('works in the dark scheme: theme tokens only, no fixed light colours', async () => {
    document.documentElement.setAttribute('data-color-scheme', 'dark');
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    await ready();
    const html = screen.getByRole('dialog').outerHTML;
    expect(html).toContain('var(--tg-theme-bg-color)');
    expect(html).not.toMatch(/bg-white|text-slate|border-slate|bg-slate/);
    document.documentElement.removeAttribute('data-color-scheme');
  });
});

describe('PhotoViewer — the photo on the whole screen (zoom)', () => {
  const fullscreen = () => screen.queryByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' });

  it('a tap on the photo and the corner button both open it full screen with the same display image; the viewer stays underneath', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const { onClose } = setup({ items: [item, makeItem()] });
    await ready();
    expect(fullscreen()).toBeNull();
    const corner = screen.getByRole('button', { name: 'Otwórz na pełnym ekranie' });
    expect(corner).toHaveClass('min-h-11', 'min-w-11');

    fireEvent.click(screen.getByRole('img'));
    const dialog = fullscreen();
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveClass('fixed', 'inset-0');
    const shown = dialog?.querySelector('img');
    expect(shown).toHaveAttribute('src', `https://r2.example/d/${item.asset.id}.jpg`);
    expect(dialog).toHaveTextContent('1 / 2');
    expect(dialog).toHaveTextContent('Rozsuń dwa palce, aby powiększyć');
    expect(screen.getByRole('dialog', { name: 'Podgląd zdjęcia' })).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Zamknij pełny ekran' }));
    expect(fullscreen()).toBeNull();
    fireEvent.click(corner);
    expect(fullscreen()).toBeInTheDocument();
  });

  it('the close button is at least 44 px, and the hint disappears after the first touch', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Otwórz na pełnym ekranie' }));
    expect(screen.getByRole('button', { name: 'Zamknij pełny ekran' })).toHaveClass('min-h-11', 'min-w-11');
    fireEvent.wheel(screen.getByTestId('zoomable-image'), { deltaY: -100 });
    expect(fullscreen()).not.toHaveTextContent('Rozsuń dwa palce');
  });

  it('Escape closes the full-screen view first and the viewer only on the next press', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const { onClose } = setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Otwórz na pełnym ekranie' }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(fullscreen()).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('the Telegram BackButton closes the full-screen view first, then the viewer', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const stack: Array<() => void> = [];
    const registry = {
      register: (close: () => void) => {
        stack.push(close);
        return () => {
          stack.splice(stack.lastIndexOf(close), 1);
        };
      },
    };
    const back = () => stack[stack.length - 1]?.();
    const { onClose } = setup({ items: [item], registry });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Otwórz na pełnym ekranie' }));
    expect(stack).toHaveLength(2);
    await act(async () => back());
    expect(fullscreen()).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    expect(stack).toHaveLength(1);
    await act(async () => back());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('is not offered while loading or when the image cannot be shown', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { display_url: null }));
    setup({ items: [item] });
    expect(screen.queryByRole('button', { name: 'Otwórz na pełnym ekranie' })).toBeNull();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Otwórz na pełnym ekranie' })).toBeNull();
  });

  it('going to another photo leaves the full-screen view', async () => {
    const items = [makeItem(), makeItem()];
    vi.mocked(fetchPhoto).mockImplementation(async (_p, assetId) => detailFor(items.find((i) => i.asset.id === assetId) as PhotoListItem));
    const view = setup({ items });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Otwórz na pełnym ekranie' }));
    expect(fullscreen()).toBeInTheDocument();
    view.rerenderAt(1);
    await waitFor(() => expect(fetchPhoto).toHaveBeenCalledTimes(2));
    await ready();
    await act(async () => undefined);
    expect(fullscreen()).toBeNull(); // not only while the next photo loads: it stays closed once it is shown
    expect(screen.getByRole('button', { name: 'Otwórz na pełnym ekranie' })).toBeInTheDocument();
  });

  it('a link that expired while zooming is refetched once and the full-screen image follows the new link', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto)
      .mockResolvedValueOnce(detailFor(item))
      .mockResolvedValueOnce(detailFor(item, { display_url: 'https://r2.example/d/fresh.jpg' }));
    setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Otwórz na pełnym ekranie' }));
    fireEvent.error(fullscreen()?.querySelector('img') as HTMLImageElement);
    await waitFor(() => expect(fetchPhoto).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(fullscreen()?.querySelector('img')).toHaveAttribute('src', 'https://r2.example/d/fresh.jpg'));
  });
});
