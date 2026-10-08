import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api/http';
import { I18nProvider } from './hooks/useI18n';
import { PhotoListItem } from './types/photo';
import { detailFor, makeItem, makeMarker, PROJECT_ID } from './test/photoFixtures';
import { PhotoViewer } from './components/PhotoViewer';

vi.mock('./api/photos', () => ({
  fetchPhoto: vi.fn(),
  patchPhotoAttachment: vi.fn(),
  archivePhotoAttachment: vi.fn(),
  restorePhotoAttachment: vi.fn(),
  createPhotoAnnotation: vi.fn(),
  patchPhotoAnnotation: vi.fn(),
  deletePhotoAnnotation: vi.fn(),
}));
import { createPhotoAnnotation, deletePhotoAnnotation, fetchPhoto, patchPhotoAnnotation } from './api/photos';

const err = (status: number, code: string) => new ApiError('server english text', status, code);

function setup({
  items,
  index = 0,
  archivedView = false,
}: {
  items: PhotoListItem[];
  index?: number;
  archivedView?: boolean;
}) {
  const handlers = {
    onIndexChange: vi.fn(),
    onClose: vi.fn(),
    onAttachmentUpdated: vi.fn(),
    onAttachmentRemoved: vi.fn(),
    onRefresh: vi.fn(),
    onAnnotationCount: vi.fn(),
  };
  const view = render(
    <I18nProvider>
      <PhotoViewer
        projectId={PROJECT_ID}
        items={items}
        index={index}
        archivedView={archivedView}
        captionFor={(item) => `line-${item.attachment.position}`}
        {...handlers}
      />
    </I18nProvider>,
  );
  return { ...handlers, ...view };
}

async function ready() {
  await waitFor(() => expect(screen.getByAltText('Zdjęcie')).toBeInTheDocument());
  const image = screen.getByAltText('Zdjęcie') as HTMLImageElement;
  // jsdom has no layout: the picture sits at (100, 50) and is 200 x 100 px.
  image.getBoundingClientRect = () => ({ left: 100, top: 50, width: 200, height: 100, right: 300, bottom: 150, x: 100, y: 50, toJSON: () => ({}) });
  return image;
}

const closePopup = () =>
  fireEvent.click(within(screen.getByRole('dialog', { name: /^Znacznik \d/ })).getByRole('button', { name: 'Zamknij' }));
const addButton = () => screen.getByRole('button', { name: 'Dodaj znacznik' });

beforeEach(() => {
  localStorage.clear();
  document.body.style.overflow = '';
  vi.mocked(fetchPhoto).mockReset();
  vi.mocked(createPhotoAnnotation).mockReset();
  vi.mocked(patchPhotoAnnotation).mockReset();
  vi.mocked(deletePhotoAnnotation).mockReset();
});

describe('PhotoViewer — markers on the picture', () => {
  it('draws only the markers of THIS attachment (the same file attached elsewhere has its own set), in display order', async () => {
    const item = makeItem();
    const mine = [makeMarker(item.attachment.id, { x: 0.1, y: 0.2, label: 'pierwszy' }), makeMarker(item.attachment.id, { x: 0.9, y: 0.8, position: 1 })];
    const theirs = makeMarker('other-attachment', { x: 0.5, y: 0.5 });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [mine[0], theirs, mine[1]] }));
    setup({ items: [item] });
    await ready();
    const markers = screen.getAllByTestId('photo-marker');
    expect(markers.map((marker) => [marker.style.left, marker.style.top])).toEqual([['10%', '20%'], ['90%', '80%']]);
    expect(screen.getByRole('button', { name: 'Znacznik 1: pierwszy' })).toBeInTheDocument();
  });

  it('shows how many markers the photo has of how many it can have (the limit comes from the server)', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [makeMarker(item.attachment.id)], annotation_limit: 7 }));
    setup({ items: [item] });
    await ready();
    expect(screen.getByText('Znaczniki: 1 z 7')).toBeInTheDocument();
  });

  it('a tap on a marker opens its pop-up with the label; it does not open the full-screen view', async () => {
    const item = makeItem();
    const marker = makeMarker(item.attachment.id, { label: 'rysa przy oknie' });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByTestId('photo-marker'));
    expect(screen.getByRole('dialog', { name: 'Znacznik 1' })).toBeInTheDocument();
    expect(screen.getByLabelText('Podpis znacznika')).toHaveValue('rysa przy oknie');
    expect(screen.queryByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' })).toBeNull();
    closePopup();
    expect(screen.queryByRole('dialog', { name: 'Znacznik 1' })).toBeNull();
  });

  it('without the placing mode a tap on the picture opens the full-screen view and places nothing', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    const image = await ready();
    fireEvent.click(image, { clientX: 150, clientY: 100 });
    expect(screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' })).toBeInTheDocument();
    expect(createPhotoAnnotation).not.toHaveBeenCalled();
  });

  it('placing mode: a tap puts a marker at the tapped fraction of the picture, opens its pop-up and reports the new count', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    const created = makeMarker(item.attachment.id, { x: 0.25, y: 0.5 });
    vi.mocked(createPhotoAnnotation).mockResolvedValue(created);
    const { onAnnotationCount } = setup({ items: [item] });
    const image = await ready();
    fireEvent.click(addButton());
    expect(screen.getByRole('button', { name: 'Zakończ dodawanie' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/Stuknij zdjęcie, aby postawić znacznik/)).toBeInTheDocument();
    fireEvent.click(image, { clientX: 150, clientY: 100 }); // (150-100)/200 = 0.25, (100-50)/100 = 0.5
    await waitFor(() => expect(createPhotoAnnotation).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, { x: 0.25, y: 0.5 }));
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Znacznik 1' })).toBeInTheDocument());
    expect(onAnnotationCount).toHaveBeenCalledWith(item.attachment.id, 1);
    expect(screen.getByTestId('photo-marker').style.left).toBe('25%');
    expect(screen.getByText('Znaczniki: 1 z 10')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' })).toBeNull();
  });

  it('a tap outside the picture (or on a picture with no size) places nothing', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    const image = await ready();
    fireEvent.click(addButton());
    for (const point of [{ clientX: 99, clientY: 100 }, { clientX: 301, clientY: 100 }, { clientX: 150, clientY: 49 }, { clientX: 150, clientY: 151 }]) {
      fireEvent.click(image, point);
    }
    expect(createPhotoAnnotation).not.toHaveBeenCalled();
  });

  it('stays in placing mode after a marker, so several can be placed in a row', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    vi.mocked(createPhotoAnnotation).mockImplementation(async (_p, attachmentId, payload) => makeMarker(attachmentId, { ...payload }));
    setup({ items: [item] });
    const image = await ready();
    fireEvent.click(addButton());
    fireEvent.click(image, { clientX: 150, clientY: 100 });
    await screen.findByRole('dialog', { name: 'Znacznik 1' });
    closePopup();
    expect(screen.getByRole('button', { name: 'Zakończ dodawanie' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(image, { clientX: 250, clientY: 120 });
    await screen.findByRole('dialog', { name: 'Znacznik 2' });
    expect(createPhotoAnnotation).toHaveBeenCalledTimes(2);
  });

  it('at the limit placing is refused: the switch is disabled, the limit is explained and nothing is sent', async () => {
    const item = makeItem();
    const full = Array.from({ length: 10 }, (_, i) => makeMarker(item.attachment.id, { position: i, x: i / 10 }));
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: full }));
    setup({ items: [item] });
    await ready();
    expect(addButton()).toBeDisabled();
    expect(screen.getByText(/Osiągnięto maksymalną liczbę znaczników \(10\)/)).toBeInTheDocument();
    expect(createPhotoAnnotation).not.toHaveBeenCalled();
  });

  it('a refusal from the server (limit reached elsewhere) shows its message and keeps the markers as they are', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    vi.mocked(createPhotoAnnotation).mockRejectedValue(err(409, 'PHOTO_ANNOTATION_LIMIT_REACHED'));
    const { onAnnotationCount } = setup({ items: [item] });
    const image = await ready();
    fireEvent.click(addButton());
    fireEvent.click(image, { clientX: 150, clientY: 100 });
    expect(await screen.findByRole('alert')).toHaveTextContent('Zdjęcie ma już maksymalną liczbę znaczników');
    expect(screen.queryByTestId('photo-marker')).toBeNull();
    expect(onAnnotationCount).not.toHaveBeenCalled();
  });

  it('saving the label sends only the label, closes the pop-up and renames the marker', async () => {
    const item = makeItem();
    const marker = makeMarker(item.attachment.id, { label: 'stary' });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    vi.mocked(patchPhotoAnnotation).mockResolvedValue({ ...marker, label: 'nowy' });
    setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.change(screen.getByLabelText('Podpis znacznika'), { target: { value: ' nowy ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz podpis' }));
    await waitFor(() => expect(patchPhotoAnnotation).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, marker.id, { label: 'nowy' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Znacznik 1' })).toBeNull());
    expect(screen.getByRole('button', { name: 'Znacznik 1: nowy' })).toBeInTheDocument();
  });

  it('deleting removes the marker, closes the pop-up and reports the new count', async () => {
    const item = makeItem();
    const markers = [makeMarker(item.attachment.id), makeMarker(item.attachment.id, { position: 1, label: 'drugi' })];
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: markers }));
    vi.mocked(deletePhotoAnnotation).mockResolvedValue(undefined);
    const { onAnnotationCount } = setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getAllByTestId('photo-marker')[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Usuń znacznik' }));
    await waitFor(() => expect(deletePhotoAnnotation).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, markers[0].id));
    await waitFor(() => expect(screen.getAllByTestId('photo-marker')).toHaveLength(1));
    expect(onAnnotationCount).toHaveBeenCalledWith(item.attachment.id, 1);
    expect(screen.getByRole('button', { name: 'Znacznik 1: drugi' })).toBeInTheDocument(); // renumbered
    expect(screen.queryByRole('dialog', { name: /Znacznik/ })).toBeNull();
  });

  it('a delete that fails keeps the marker and says why inside the pop-up', async () => {
    const item = makeItem();
    const marker = makeMarker(item.attachment.id);
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    vi.mocked(deletePhotoAnnotation).mockRejectedValue(err(409, 'PHOTO_ANNOTATION_READ_ONLY'));
    setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.click(screen.getByRole('button', { name: 'Usuń znacznik' }));
    const popup = await screen.findByRole('dialog', { name: 'Znacznik 1' });
    expect(await within(popup).findByRole('alert')).toHaveTextContent('Znaczników zarchiwizowanego zdjęcia nie można zmieniać.');
    expect(screen.getAllByTestId('photo-marker')).toHaveLength(1);
  });

  it('a marker that is already gone makes the viewer read the photo again', async () => {
    const item = makeItem();
    const marker = makeMarker(item.attachment.id);
    vi.mocked(fetchPhoto).mockResolvedValueOnce(detailFor(item, { annotations: [marker] })).mockResolvedValueOnce(detailFor(item, { annotations: [] }));
    vi.mocked(deletePhotoAnnotation).mockRejectedValue(err(404, 'PHOTO_ANNOTATION_NOT_FOUND'));
    setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.click(screen.getByRole('button', { name: 'Usuń znacznik' }));
    await waitFor(() => expect(fetchPhoto).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByTestId('photo-marker')).toBeNull());
  });

  it('an archived photo shows its markers read only: no add switch, no input, no delete', async () => {
    const item = makeItem({ attachment: { archived_at: '2026-10-08T08:00:00Z' } });
    const marker = makeMarker(item.attachment.id, { label: 'zostaje' });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    setup({ items: [item], archivedView: true });
    await ready();
    expect(screen.queryByRole('button', { name: 'Dodaj znacznik' })).toBeNull();
    fireEvent.click(screen.getByTestId('photo-marker'));
    expect(screen.getByTestId('marker-label-text')).toHaveTextContent('zostaje');
    expect(screen.queryByRole('textbox', { name: 'Podpis znacznika' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Usuń znacznik' })).toBeNull();
  });

  it('an archived photo without markers shows no marker controls at all', async () => {
    const item = makeItem({ attachment: { archived_at: '2026-10-08T08:00:00Z' } });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item], archivedView: true });
    await ready();
    expect(screen.queryByTestId('marker-controls')).toBeNull();
  });

  it('a photo archived as a whole (asset) is read only too, even in the normal list', async () => {
    const item = makeItem({ asset: { archived_at: '2026-10-08T08:00:00Z' } });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [makeMarker(item.attachment.id)] }));
    setup({ items: [item] });
    await ready();
    expect(screen.queryByRole('button', { name: 'Dodaj znacznik' })).toBeNull();
    expect(screen.getAllByTestId('photo-marker')).toHaveLength(1);
  });

  it('the archive view makes the photo read only whatever its own dates say', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [makeMarker(item.attachment.id)] }));
    setup({ items: [item], archivedView: true });
    await ready();
    expect(screen.queryByRole('button', { name: 'Dodaj znacznik' })).toBeNull();
    expect(screen.getAllByTestId('photo-marker')).toHaveLength(1);
  });

  it('an archived attachment is read only even when the list is the normal one', async () => {
    const item = makeItem({ attachment: { archived_at: '2026-10-08T08:00:00Z' } });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [makeMarker(item.attachment.id)] }));
    setup({ items: [item], archivedView: false });
    await ready();
    expect(screen.queryByRole('button', { name: 'Dodaj znacznik' })).toBeNull();
  });

  it('the tenth marker fills the photo: the next tap in placing mode is refused on the spot, with the reason, and nothing is sent', async () => {
    const item = makeItem();
    const nine = Array.from({ length: 9 }, (_, i) => makeMarker(item.attachment.id, { position: i, x: i / 10 }));
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: nine }));
    vi.mocked(createPhotoAnnotation).mockImplementation(async (_p, attachmentId, payload) => makeMarker(attachmentId, { ...payload, position: 9 }));
    setup({ items: [item] });
    const image = await ready();
    fireEvent.click(addButton());
    fireEvent.click(image, { clientX: 150, clientY: 100 });
    await screen.findByRole('dialog', { name: 'Znacznik 10' });
    closePopup();
    fireEvent.click(image, { clientX: 160, clientY: 110 });
    expect(await screen.findByRole('alert')).toHaveTextContent('Zdjęcie ma już maksymalną liczbę znaczników');
    expect(createPhotoAnnotation).toHaveBeenCalledTimes(1);
  });

  it('a second tap while the first marker is still being saved places nothing more', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    let resolve!: (marker: ReturnType<typeof makeMarker>) => void;
    vi.mocked(createPhotoAnnotation).mockReturnValue(new Promise((done) => { resolve = done; }));
    setup({ items: [item] });
    const image = await ready();
    fireEvent.click(addButton());
    fireEvent.click(image, { clientX: 150, clientY: 100 });
    fireEvent.click(image, { clientX: 150, clientY: 100 });
    expect(createPhotoAnnotation).toHaveBeenCalledTimes(1);
    await act(async () => resolve(makeMarker(item.attachment.id)));
  });

  it('the next photo starts with placing off and no pop-up, and shows its own markers', async () => {
    const [a, b] = [makeItem(), makeItem()];
    vi.mocked(fetchPhoto).mockImplementation(async (_p, assetId) =>
      assetId === a.asset.id
        ? detailFor(a, { annotations: [makeMarker(a.attachment.id, { x: 0.1 })] })
        : detailFor(b, { annotations: [makeMarker(b.attachment.id, { x: 0.8 }), makeMarker(b.attachment.id, { x: 0.9, position: 1 })] }),
    );
    const { rerender } = setup({ items: [a, b] });
    await ready();
    fireEvent.click(addButton());
    expect(screen.getByRole('button', { name: 'Zakończ dodawanie' })).toBeInTheDocument();
    rerender(
      <I18nProvider>
        <PhotoViewer
          projectId={PROJECT_ID}
          items={[a, b]}
          index={1}
          archivedView={false}
          captionFor={(item) => `line-${item.attachment.position}`}
          onIndexChange={vi.fn()}
          onClose={vi.fn()}
          onAttachmentUpdated={vi.fn()}
          onAttachmentRemoved={vi.fn()}
        />
      </I18nProvider>,
    );
    await waitFor(() => expect(screen.getAllByTestId('photo-marker')).toHaveLength(2));
    expect(screen.getByRole('button', { name: 'Dodaj znacznik' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('remembers the markers of a photo it has already loaded (back to it without asking again), including a change made meanwhile', async () => {
    const [a, b] = [makeItem(), makeItem()];
    const created = makeMarker(a.attachment.id, { x: 0.25, y: 0.5 });
    vi.mocked(fetchPhoto).mockImplementation(async (_p, assetId) => detailFor(assetId === a.asset.id ? a : b));
    vi.mocked(createPhotoAnnotation).mockResolvedValue(created);
    const ui = (index: number) => (
      <I18nProvider>
        <PhotoViewer
          projectId={PROJECT_ID}
          items={[a, b]}
          index={index}
          archivedView={false}
          captionFor={(item) => `line-${item.attachment.position}`}
          onIndexChange={vi.fn()}
          onClose={vi.fn()}
          onAttachmentUpdated={vi.fn()}
          onAttachmentRemoved={vi.fn()}
        />
      </I18nProvider>
    );
    const view = render(ui(0));
    const image = await ready();
    fireEvent.click(addButton());
    fireEvent.click(image, { clientX: 150, clientY: 100 });
    await screen.findByRole('dialog', { name: 'Znacznik 1' });
    closePopup();
    view.rerender(ui(1));
    await waitFor(() => expect(fetchPhoto).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByTestId('photo-marker')).toBeNull());
    view.rerender(ui(0));
    await waitFor(() => expect(screen.getAllByTestId('photo-marker')).toHaveLength(1));
    expect(fetchPhoto).toHaveBeenCalledTimes(2); // photo A came from the cache, with the marker
  });
});

describe('PhotoViewer — markers on the full-screen picture', () => {
  it('shows the markers on the full-screen picture and a pop-up opens above it', async () => {
    const item = makeItem();
    const marker = makeMarker(item.attachment.id, { label: 'szczelina' });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    setup({ items: [item] });
    const image = await ready();
    fireEvent.click(image);
    const fullscreen = screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' });
    const markerInFullscreen = within(fullscreen).getByTestId('photo-marker');
    fireEvent.click(markerInFullscreen);
    expect(screen.getByRole('dialog', { name: 'Znacznik 1' })).toBeInTheDocument();
    expect(screen.getByLabelText('Podpis znacznika')).toHaveValue('szczelina');
  });

  it('the add switch is on the full-screen view too and shares the state with the viewer', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    setup({ items: [item] });
    const image = await ready();
    fireEvent.click(image);
    const fullscreen = screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' });
    fireEvent.click(within(fullscreen).getByRole('button', { name: 'Dodaj znacznik' }));
    expect(within(fullscreen).getByRole('button', { name: 'Zakończ dodawanie' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(fullscreen).getByText(/rozsuń palce, aby dokładniej wskazać miejsce/)).toBeInTheDocument();
    fireEvent.click(within(fullscreen).getByRole('button', { name: 'Zamknij pełny ekran' }));
    expect(screen.getByRole('button', { name: 'Zakończ dodawanie' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('placing works on the zoomable full-screen picture: a tap there places a marker at the tapped fraction', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item));
    vi.mocked(createPhotoAnnotation).mockImplementation(async (_p, attachmentId, payload) => makeMarker(attachmentId, { ...payload }));
    setup({ items: [item] });
    fireEvent.click(await ready());
    const fullscreen = screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' });
    fireEvent.click(within(fullscreen).getByRole('button', { name: 'Dodaj znacznik' }));
    const picture = within(fullscreen).getByAltText('Zdjęcie');
    picture.getBoundingClientRect = () => ({ left: 0, top: 100, width: 400, height: 200, right: 400, bottom: 300, x: 0, y: 100, toJSON: () => ({}) });
    const area = within(fullscreen).getByTestId('zoomable-image');
    for (const type of ['pointerdown', 'pointerup'] as const) {
      const event = new MouseEvent(type, { bubbles: true, clientX: 100, clientY: 150 });
      Object.defineProperty(event, 'pointerId', { value: 1 });
      fireEvent(area, event);
    }
    await waitFor(() => expect(createPhotoAnnotation).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, { x: 0.25, y: 0.25 }));
    expect(await screen.findByRole('dialog', { name: 'Znacznik 1' })).toBeInTheDocument();
  });

  it('no add switch on the full-screen view of an archived photo or when the photo is full', async () => {
    const full = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(
      detailFor(full, { annotations: Array.from({ length: 10 }, (_, i) => makeMarker(full.attachment.id, { position: i })) }),
    );
    setup({ items: [full] });
    fireEvent.click(await ready());
    expect(within(screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' })).queryByRole('button', { name: 'Dodaj znacznik' })).toBeNull();
  });
});

describe('PhotoViewer — marker controls on a phone', () => {
  it('the add switch is a 44 px target that wraps its text; the pop-up and the markers are 44 px too', async () => {
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [makeMarker(item.attachment.id)] }));
    setup({ items: [item] });
    await ready();
    expect(addButton()).toHaveClass('min-h-11', 'min-w-0');
    expect(addButton().querySelector('span')).toHaveClass('break-words');
    expect(screen.getByTestId('photo-marker')).toHaveClass('h-11', 'w-11');
  });

  it('Russian labels and messages', async () => {
    localStorage.setItem('locale', 'ru');
    const item = makeItem();
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [makeMarker(item.attachment.id)] }));
    setup({ items: [item] });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Добавить метку' })).toBeInTheDocument());
    expect(screen.getByText('Метки: 1 из 10')).toBeInTheDocument();
  });

  it('a pending marker call blocks leaving the photo (navigation is disabled while it runs)', async () => {
    const [a, b] = [makeItem(), makeItem()];
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(a));
    let resolve!: (marker: ReturnType<typeof makeMarker>) => void;
    vi.mocked(createPhotoAnnotation).mockReturnValue(new Promise((done) => { resolve = done; }));
    setup({ items: [a, b] });
    const image = await ready();
    fireEvent.click(addButton());
    fireEvent.click(image, { clientX: 150, clientY: 100 });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Następne zdjęcie' })).toBeDisabled());
    await act(async () => resolve(makeMarker(a.attachment.id)));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Następne zdjęcie' })).toBeEnabled());
  });
});

describe('PhotoViewer — contour around a defect', () => {
  const loop = [
    [100, 150], [200, 130], [300, 150], [310, 200], [300, 230], [200, 240], [100, 230], [90, 190], [100, 155],
  ] as const; // a loop around the middle of the 400x200 picture at (0, 100)

  const pointer = (area: Element, type: 'pointerdown' | 'pointermove' | 'pointerup', x: number, y: number) => {
    const event = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y });
    Object.defineProperty(event, 'pointerId', { value: 1 });
    fireEvent(area, event);
  };
  const drawLoop = (area: Element) => {
    pointer(area, 'pointerdown', loop[0][0], loop[0][1]);
    for (const [x, y] of loop.slice(1)) pointer(area, 'pointermove', x, y);
    pointer(area, 'pointerup', loop[loop.length - 1][0], loop[loop.length - 1][1]);
  };

  async function openDrawing(over: Partial<ReturnType<typeof makeMarker>> = {}) {
    const item = makeItem();
    const marker = makeMarker(item.attachment.id, { label: 'rysa', ...over });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    const view = setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.click(screen.getByRole('button', { name: marker.outline ? 'Obrysuj ponownie' : 'Obrysuj wadę' }));
    const fullscreen = screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' });
    const picture = within(fullscreen).getByAltText('Zdjęcie');
    picture.getBoundingClientRect = () => ({ left: 0, top: 100, width: 400, height: 200, right: 400, bottom: 300, x: 0, y: 100, toJSON: () => ({}) });
    return { item, marker, fullscreen, area: within(fullscreen).getByTestId('zoomable-image'), ...view };
  }

  it('"Obrysuj wadę" in the pop-up closes it and opens the big picture in drawing mode, with a hint and a cancel button', async () => {
    const { fullscreen } = await openDrawing();
    expect(screen.queryByRole('dialog', { name: 'Znacznik 1' })).toBeNull();
    expect(within(fullscreen).getByText(/Obrysuj wadę palcem/)).toBeInTheDocument();
    expect(within(fullscreen).getByRole('button', { name: 'Anuluj' })).toBeInTheDocument();
    expect(within(fullscreen).queryByRole('button', { name: 'Dodaj znacznik' })).toBeNull(); // no placing while drawing
    expect(within(fullscreen).getByTestId('photo-marker')).toHaveClass('pointer-events-none');
  });

  it('a finished stroke is thinned, saved on the marker and drawing ends', async () => {
    const { item, marker, area, fullscreen } = await openDrawing();
    vi.mocked(patchPhotoAnnotation).mockImplementation(async (_p, _a, _id, patch) => ({ ...marker, outline: patch.outline ?? null }));
    drawLoop(area);
    await waitFor(() => expect(patchPhotoAnnotation).toHaveBeenCalledTimes(1));
    const [projectId, attachmentId, markerId, patch] = vi.mocked(patchPhotoAnnotation).mock.calls[0];
    expect([projectId, attachmentId, markerId]).toEqual([PROJECT_ID, item.attachment.id, marker.id]);
    expect(Object.keys(patch)).toEqual(['outline']); // only the contour, the label stays as it is
    const points = patch.outline!;
    expect(points.length).toBeGreaterThanOrEqual(3);
    expect(points.length).toBeLessThanOrEqual(100);
    for (const [x, y] of points) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(1);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(1);
    }
    expect(points[0]).toEqual([0.25, 0.25]); // (100-0)/400, (150-100)/200
    await waitFor(() => expect(within(fullscreen).queryByText(/Obrysuj wadę palcem/)).toBeNull());
    expect(within(fullscreen).getAllByTestId('marker-outline')).toHaveLength(1);
    expect(within(fullscreen).getByTestId('photo-marker')).toHaveClass('pointer-events-auto');
  });

  it('the saved contour is on the picture in the viewer too, and the label is untouched', async () => {
    const { marker, area } = await openDrawing();
    vi.mocked(patchPhotoAnnotation).mockImplementation(async (_p, _a, _id, patch) => ({ ...marker, outline: patch.outline ?? null }));
    drawLoop(area);
    await waitFor(() => expect(screen.getAllByTestId('marker-outline').length).toBeGreaterThanOrEqual(1));
    expect(screen.getAllByRole('button', { name: 'Znacznik 1: rysa' }).length).toBeGreaterThan(0);
  });

  it('a stroke that is only a touch is refused with a message, nothing is sent, and drawing goes on', async () => {
    const { area, fullscreen } = await openDrawing();
    pointer(area, 'pointerdown', 100, 150);
    pointer(area, 'pointermove', 102, 151);
    pointer(area, 'pointerup', 102, 151);
    expect(await within(fullscreen).findByRole('alert')).toHaveTextContent('Obrys jest za krótki');
    expect(patchPhotoAnnotation).not.toHaveBeenCalled();
    expect(within(fullscreen).getByText(/Obrysuj wadę palcem/)).toBeInTheDocument(); // still drawing
  });

  it('a save that fails says why under the picture and leaves drawing on, so the stroke can be repeated', async () => {
    const { area, fullscreen } = await openDrawing();
    vi.mocked(patchPhotoAnnotation).mockRejectedValue(err(409, 'PHOTO_ANNOTATION_READ_ONLY'));
    drawLoop(area);
    expect(await within(fullscreen).findByRole('alert')).toHaveTextContent('Znaczników zarchiwizowanego zdjęcia nie można zmieniać.');
    expect(within(fullscreen).getByText(/Obrysuj wadę palcem/)).toBeInTheDocument();
  });

  it('"Anuluj" leaves drawing without saving; the big picture stays open', async () => {
    const { fullscreen } = await openDrawing();
    fireEvent.click(within(fullscreen).getByRole('button', { name: 'Anuluj' }));
    expect(within(fullscreen).queryByText(/Obrysuj wadę palcem/)).toBeNull();
    expect(screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' })).toBeInTheDocument();
    expect(patchPhotoAnnotation).not.toHaveBeenCalled();
  });

  it('closing the big picture while drawing (the Back button, the X) only leaves drawing; a second close closes the picture', async () => {
    const { fullscreen } = await openDrawing();
    fireEvent.click(within(fullscreen).getByRole('button', { name: 'Zamknij pełny ekran' }));
    expect(screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' })).toBeInTheDocument();
    expect(within(fullscreen).queryByText(/Obrysuj wadę palcem/)).toBeNull();
    fireEvent.click(within(fullscreen).getByRole('button', { name: 'Zamknij pełny ekran' }));
    expect(screen.queryByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' })).toBeNull();
  });

  it('a marker that has a contour offers to draw it again, and drawing replaces it', async () => {
    const outline: Array<[number, number]> = [[0.1, 0.1], [0.2, 0.3], [0.3, 0.1]];
    const { marker, area } = await openDrawing({ outline });
    vi.mocked(patchPhotoAnnotation).mockImplementation(async (_p, _a, _id, patch) => ({ ...marker, outline: patch.outline ?? null }));
    drawLoop(area);
    await waitFor(() => expect(patchPhotoAnnotation).toHaveBeenCalledTimes(1));
    expect(vi.mocked(patchPhotoAnnotation).mock.calls[0][3].outline).not.toEqual(outline);
  });

  it('"Usuń obrys" clears the contour (null), keeps the marker and its label and closes the pop-up', async () => {
    const item = makeItem();
    const marker = makeMarker(item.attachment.id, { label: 'rysa', outline: [[0.1, 0.1], [0.2, 0.3], [0.3, 0.1]] });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    vi.mocked(patchPhotoAnnotation).mockResolvedValue({ ...marker, outline: null });
    setup({ items: [item] });
    await ready();
    expect(screen.getAllByTestId('marker-outline')).toHaveLength(1);
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.click(screen.getByRole('button', { name: 'Usuń obrys' }));
    await waitFor(() => expect(patchPhotoAnnotation).toHaveBeenCalledWith(PROJECT_ID, item.attachment.id, marker.id, { outline: null }));
    await waitFor(() => expect(screen.queryByTestId('marker-outline')).toBeNull());
    expect(screen.getByRole('button', { name: 'Znacznik 1: rysa' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Znacznik 1' })).toBeNull();
  });

  it('contours of other attachments of the same photo are not drawn', async () => {
    const item = makeItem();
    const mine = makeMarker(item.attachment.id);
    const theirs = makeMarker('other-attachment', { outline: [[0.1, 0.1], [0.2, 0.3], [0.3, 0.1]] });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [mine, theirs] }));
    setup({ items: [item] });
    await ready();
    expect(screen.queryByTestId('marker-outline')).toBeNull();
  });

  it('an archived photo shows contours but cannot draw, redraw or remove them', async () => {
    const item = makeItem({ attachment: { archived_at: '2026-10-08T08:00:00Z' } });
    const marker = makeMarker(item.attachment.id, { outline: [[0.1, 0.1], [0.2, 0.3], [0.3, 0.1]] });
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    setup({ items: [item], archivedView: true });
    await ready();
    expect(screen.getAllByTestId('marker-outline')).toHaveLength(1);
    fireEvent.click(screen.getByTestId('photo-marker'));
    for (const name of ['Obrysuj wadę', 'Obrysuj ponownie', 'Usuń obrys']) {
      expect(screen.queryByRole('button', { name })).toBeNull();
    }
  });

  it('while drawing, the marker being outlined is highlighted', async () => {
    const { fullscreen } = await openDrawing();
    expect(within(fullscreen).getByTestId('photo-marker').querySelector('span')!.className).toContain('ring-2');
  });

  it('after the contour is saved the add-marker switch is off, even if it was on when drawing began', async () => {
    const item = makeItem();
    const marker = makeMarker(item.attachment.id);
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    vi.mocked(patchPhotoAnnotation).mockImplementation(async (_p, _a, _id, patch) => ({ ...marker, outline: patch.outline ?? null }));
    setup({ items: [item] });
    await ready();
    fireEvent.click(addButton()); // placing mode on
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.click(screen.getByRole('button', { name: 'Obrysuj wadę' }));
    const fullscreen = screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' });
    const picture = within(fullscreen).getByAltText('Zdjęcie');
    picture.getBoundingClientRect = () => ({ left: 0, top: 100, width: 400, height: 200, right: 400, bottom: 300, x: 0, y: 100, toJSON: () => ({}) });
    drawLoop(within(fullscreen).getByTestId('zoomable-image'));
    await waitFor(() => expect(patchPhotoAnnotation).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(within(fullscreen).queryByText(/Obrysuj wadę palcem/)).toBeNull());
    expect(within(fullscreen).getByRole('button', { name: 'Dodaj znacznik' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('a second stroke while the first is still being saved is ignored', async () => {
    const { marker, area } = await openDrawing();
    let finish!: (value: typeof marker) => void;
    vi.mocked(patchPhotoAnnotation).mockReturnValue(new Promise((done) => { finish = done; }));
    drawLoop(area);
    await waitFor(() => expect(patchPhotoAnnotation).toHaveBeenCalledTimes(1));
    drawLoop(area);
    expect(patchPhotoAnnotation).toHaveBeenCalledTimes(1);
    await act(async () => finish({ ...marker, outline: [[0.1, 0.1], [0.2, 0.2], [0.3, 0.1]] }));
  });

  it('the contour keeps within the point limit the server names (a smaller limit than the phone\'s own)', async () => {
    const item = makeItem();
    const marker = makeMarker(item.attachment.id);
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker], outline_max_points: 6 }));
    vi.mocked(patchPhotoAnnotation).mockImplementation(async (_p, _a, _id, patch) => ({ ...marker, outline: patch.outline ?? null }));
    setup({ items: [item] });
    await ready();
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.click(screen.getByRole('button', { name: 'Obrysuj wadę' }));
    const fullscreen = screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' });
    const picture = within(fullscreen).getByAltText('Zdjęcie');
    picture.getBoundingClientRect = () => ({ left: 0, top: 100, width: 400, height: 200, right: 400, bottom: 300, x: 0, y: 100, toJSON: () => ({}) });
    const area = within(fullscreen).getByTestId('zoomable-image');
    pointer(area, 'pointerdown', 50, 150);
    for (let i = 1; i <= 60; i += 1) pointer(area, 'pointermove', 50 + i * 5, 200 + 40 * Math.sin(i / 3)); // a wavy line
    pointer(area, 'pointerup', 350, 200);
    await waitFor(() => expect(patchPhotoAnnotation).toHaveBeenCalledTimes(1));
    expect(vi.mocked(patchPhotoAnnotation).mock.calls[0][3].outline!.length).toBeLessThanOrEqual(6);
  });

  it('coming back to a photo does not reopen its drawing mode', async () => {
    const [a, b] = [makeItem(), makeItem()];
    const marker = makeMarker(a.attachment.id);
    vi.mocked(fetchPhoto).mockImplementation(async (_p, assetId) => (assetId === a.asset.id ? detailFor(a, { annotations: [marker] }) : detailFor(b)));
    const ui = (index: number) => (
      <I18nProvider>
        <PhotoViewer
          projectId={PROJECT_ID}
          items={[a, b]}
          index={index}
          archivedView={false}
          captionFor={(item) => `line-${item.attachment.position}`}
          onIndexChange={vi.fn()}
          onClose={vi.fn()}
          onAttachmentUpdated={vi.fn()}
          onAttachmentRemoved={vi.fn()}
        />
      </I18nProvider>
    );
    const view = render(ui(0));
    await ready();
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.click(screen.getByRole('button', { name: 'Obrysuj wadę' }));
    view.rerender(ui(1));
    await waitFor(() => expect(screen.queryByText(/Obrysuj wadę palcem/)).toBeNull());
    view.rerender(ui(0));
    await waitFor(() => expect(screen.getByTestId('photo-marker')).toBeInTheDocument());
    fireEvent.click(screen.getByAltText('Zdjęcie')); // the big picture opens again
    expect(screen.getByRole('dialog', { name: 'Zdjęcie na pełnym ekranie' })).toBeInTheDocument();
    expect(screen.queryByText(/Obrysuj wadę palcem/)).toBeNull();
  });

  it('the next photo starts without drawing', async () => {
    const [a, b] = [makeItem(), makeItem()];
    const marker = makeMarker(a.attachment.id);
    vi.mocked(fetchPhoto).mockImplementation(async (_p, assetId) => (assetId === a.asset.id ? detailFor(a, { annotations: [marker] }) : detailFor(b)));
    const ui = (index: number) => (
      <I18nProvider>
        <PhotoViewer
          projectId={PROJECT_ID}
          items={[a, b]}
          index={index}
          archivedView={false}
          captionFor={(item) => `line-${item.attachment.position}`}
          onIndexChange={vi.fn()}
          onClose={vi.fn()}
          onAttachmentUpdated={vi.fn()}
          onAttachmentRemoved={vi.fn()}
        />
      </I18nProvider>
    );
    const view = render(ui(0));
    await ready();
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.click(screen.getByRole('button', { name: 'Obrysuj wadę' }));
    expect(screen.getByText(/Obrysuj wadę palcem/)).toBeInTheDocument();
    view.rerender(ui(1));
    await waitFor(() => expect(screen.queryByText(/Obrysuj wadę palcem/)).toBeNull());
  });

  it('Russian drawing texts', async () => {
    localStorage.setItem('locale', 'ru');
    const item = makeItem();
    const marker = makeMarker(item.attachment.id);
    vi.mocked(fetchPhoto).mockResolvedValue(detailFor(item, { annotations: [marker] }));
    setup({ items: [item] });
    await waitFor(() => expect(screen.getByTestId('photo-marker')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('photo-marker'));
    fireEvent.click(screen.getByRole('button', { name: 'Обвести дефект' }));
    expect(screen.getByText(/Обведите дефект пальцем/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Отмена' })).toBeInTheDocument();
  });
});

