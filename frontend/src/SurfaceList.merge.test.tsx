import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api/http';
import * as openingsApi from './api/openings';
import * as surfacesApi from './api/surfaces';
import * as workPlansApi from './api/workPlans';
import { SurfaceList } from './components/SurfaceList';
import { I18nProvider } from './hooks/useI18n';
import type { SurfaceType } from './types/surface';

vi.mock('./api/surfaces', () => ({
  fetchSurfaces: vi.fn(),
  createSurface: vi.fn(),
  updateSurface: vi.fn(),
  archiveSurface: vi.fn(),
  restoreSurface: vi.fn(),
  generateWalls: vi.fn(),
  mergeSurfaces: vi.fn(),
  unmergeSurface: vi.fn(),
  duplicateMergedSurface: vi.fn(),
  reorderSurfaces: vi.fn(),
  updateSurfacePart: vi.fn(),
}));
vi.mock('./api/openings', () => ({
  fetchOpenings: vi.fn(),
  createOpening: vi.fn(),
  updateOpening: vi.fn(),
  archiveOpening: vi.fn(),
  restoreOpening: vi.fn(),
}));
vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return { ...actual, fetchSurfaceWorkPlan: vi.fn(), putSurfaceWorkPlan: vi.fn(), applyWorkPlanToRoomWalls: vi.fn() };
});

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const wall = (n: number, width: string, height: string, extra: Partial<SurfaceType> = {}): SurfaceType => ({
  id: `00000000-0000-0000-0000-00000000000${n}`,
  room_id: roomId,
  name: `Ściana ${n}`,
  surface_type: 'WALL',
  description: null,
  position: n,
  width,
  height,
  gross_area: (Number(width) * Number(height)).toFixed(3),
  deduction_area: '0.000',
  net_area: (Number(width) * Number(height)).toFixed(3),
  is_archived: false,
  created_at: '2026-10-23T10:00:00Z',
  updated_at: '2026-10-23T10:00:00Z',
  ...extra,
});
const W1 = wall(1, '3.420', '2.520');
const W2 = wall(2, '2.700', '2.500');
const W3 = wall(3, '4.000', '2.500');

function renderList(wallMode: 'RECTANGLE' | 'CUSTOM' = 'CUSTOM') {
  return render(
    <I18nProvider>
      <SurfaceList projectId={projectId} roomId={roomId} roomName="Salon" wallMode={wallMode} initiallyOpen={false} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [W1, W2, W3], total: 3 });
  vi.mocked(openingsApi.fetchOpenings).mockResolvedValue([] as never);
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue({ id: 'p', surface_id: W1.id, substrate: 'CONCRETE', quality_target: 'S2', planned_works: [] } as never);
});
afterEach(() => {
  vi.useRealTimers();
});

describe('merging walls: the selection', () => {
  it('offers "Połącz ściany" only in an irregular room with two or more walls that can be merged', async () => {
    renderList('RECTANGLE');
    await screen.findByLabelText(`surface-row-${W1.id}`);
    expect(screen.queryByLabelText('merge-walls-start')).toBeNull();
  });

  it('does not offer it with one wall', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [W1], total: 1 });
    renderList();
    await screen.findByLabelText(`surface-row-${W1.id}`);
    expect(screen.queryByLabelText('merge-walls-start')).toBeNull();
  });

  it('marks walls in the order they are tapped, the first one stays, and merges them after one confirmation', async () => {
    vi.mocked(surfacesApi.mergeSurfaces).mockResolvedValue({ ...W2, parts: [] });
    renderList();
    fireEvent.click(await screen.findByLabelText('merge-walls-start'));
    expect(screen.getByLabelText('merge-go')).toBeDisabled();
    fireEvent.click(screen.getByLabelText(`surface-row-${W3.id}`));
    fireEvent.click(screen.getByLabelText(`surface-row-${W1.id}`));
    expect(screen.getByLabelText(`surface-row-mark-${W3.id}`)).toHaveTextContent('1');
    expect(screen.getByLabelText(`surface-row-mark-${W1.id}`)).toHaveTextContent('2');
    expect(screen.getByLabelText('merge-selected')).toHaveTextContent('Zaznaczone: 2');
    expect(within(screen.getByLabelText(`surface-item-${W3.id}`)).getByText('zostaje')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('merge-go'));
    expect(surfacesApi.mergeSurfaces).not.toHaveBeenCalled(); // one confirmation first
    expect(screen.getByLabelText('merge-confirm')).toHaveTextContent('Ściana 3');
    fireEvent.click(screen.getByLabelText('merge-confirm-yes'));
    await waitFor(() => expect(surfacesApi.mergeSurfaces).toHaveBeenCalledWith(projectId, roomId, [W3.id, W1.id]));
    expect(await screen.findByText('Ściany połączone')).toBeInTheDocument();
    expect(screen.queryByLabelText('merge-bar')).toBeNull();
  });

  it('a tap on a marked wall unmarks it; "Anuluj" leaves the selection', async () => {
    renderList();
    fireEvent.click(await screen.findByLabelText('merge-walls-start'));
    fireEvent.click(screen.getByLabelText(`surface-row-${W1.id}`));
    fireEvent.click(screen.getByLabelText(`surface-row-${W1.id}`));
    expect(screen.getByLabelText('merge-selected')).toHaveTextContent('Zaznaczone: 0');
    fireEvent.click(screen.getByLabelText('merge-cancel'));
    expect(screen.queryByLabelText('merge-bar')).toBeNull();
    expect(screen.getByLabelText('merge-walls-start')).toBeInTheDocument();
  });

  it('a long press on a wall starts the selection with that wall; a short tap only opens it', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderList();
    const row = await screen.findByLabelText(`surface-row-${W2.id}`);
    fireEvent.pointerDown(row, { clientX: 10, clientY: 10 });
    act(() => {
      vi.advanceTimersByTime(520);
    });
    fireEvent.pointerUp(row);
    fireEvent.click(row); // the click that ends the press is not a tap
    expect(screen.getByLabelText('merge-selected')).toHaveTextContent('Zaznaczone: 1');
    expect(screen.getByLabelText(`surface-row-mark-${W2.id}`)).toHaveTextContent('1');
  });

  it('a short press does not start the selection', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderList();
    const row = await screen.findByLabelText(`surface-row-${W2.id}`);
    fireEvent.pointerDown(row);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    fireEvent.pointerUp(row);
    fireEvent.click(row);
    expect(screen.queryByLabelText('merge-bar')).toBeNull();
    expect(await screen.findByLabelText(`card-collapse-${W2.id}`)).toBeInTheDocument(); // it opened the card
  });

  it('a press that turns into a scroll does not start the selection', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderList();
    const row = await screen.findByLabelText(`surface-row-${W2.id}`);
    // jsdom has no PointerEvent: a mouse event of the pointer type carries the coordinates
    row.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX: 10, clientY: 10 }));
    row.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 10, clientY: 60 }));
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(screen.queryByLabelText('merge-bar')).toBeNull();
  });

  it('shows the reason in the language of the interface when the server refuses', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(surfacesApi.mergeSurfaces).mockRejectedValue(new ApiError('x', 409, 'WALL_MERGE_WORK_STARTED'));
    renderList();
    fireEvent.click(await screen.findByLabelText('merge-walls-start'));
    fireEvent.click(screen.getByLabelText(`surface-row-${W1.id}`));
    fireEvent.click(screen.getByLabelText(`surface-row-${W2.id}`));
    fireEvent.click(screen.getByLabelText('merge-go'));
    fireEvent.click(screen.getByLabelText('merge-confirm-yes'));
    expect(await screen.findByRole('alert')).toHaveTextContent('На одной из стен уже начаты работы');
  });
});

describe('merging walls: a merged wall', () => {
  const parts = [
    { id: 'part-1', source_surface_id: W1.id, position: 0, width: '3.420', height: '2.520' },
    { id: 'part-2', source_surface_id: W2.id, position: 1, width: '2.700', height: '2.500' },
  ];
  const merged = wall(1, '3.420', '2.520', { parts, gross_area: '15.368', net_area: '15.368' });
  const absorbed = wall(2, '2.700', '2.500', { is_archived: true, merged_into_id: W1.id });

  beforeEach(() => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [merged, absorbed], total: 2 });
  });

  it('lists the parts instead of one size, with the sum as the area, and no duplicate button', async () => {
    renderList();
    fireEvent.click(await screen.findByLabelText(`surface-row-${W1.id}`));
    const block = await screen.findByLabelText(`merged-parts-${W1.id}`);
    expect(block).toHaveTextContent('Części ściany (2)');
    expect(within(block).getAllByText(/Część [12]/)).toHaveLength(2);
    expect(block).toHaveTextContent('3,42 × 2,52');
    expect(block).toHaveTextContent('2,70 × 2,50');
    expect(screen.queryByLabelText(`edit-dimensions-${W1.id}`)).toBeNull(); // the size is the parts
    expect(screen.queryByLabelText(`duplicate-surface-${W1.id}`)).toBeNull();
  });

  it('shows the number of parts on the collapsed row', async () => {
    renderList();
    expect(await screen.findByLabelText(`surface-row-parts-${W1.id}`)).toHaveTextContent('2');
  });

  it('saves the size of one part', async () => {
    vi.mocked(surfacesApi.updateSurfacePart).mockResolvedValue(merged);
    renderList();
    fireEvent.click(await screen.findByLabelText(`surface-row-${W1.id}`));
    fireEvent.click(await screen.findByLabelText('edit-dimensions-part-2'));
    fireEvent.change(screen.getByLabelText('dimensions-width-part-2'), { target: { value: '300' } });
    fireEvent.change(screen.getByLabelText('dimensions-height-part-2'), { target: { value: '250' } });
    fireEvent.click(screen.getByLabelText('dimensions-save-part-2'));
    await waitFor(() => expect(surfacesApi.updateSurfacePart).toHaveBeenCalledWith(projectId, roomId, W1.id, 'part-2', { width: 3, height: 2.5 }));
  });

  it('renames a merged wall: a sheet over the list that sends the name and the description only', async () => {
    vi.mocked(surfacesApi.updateSurface).mockResolvedValue(merged);
    renderList();
    const pencil = await screen.findByLabelText(`edit-surface-${W1.id}`); // the pencil of the collapsed row: the card is not opened
    expect(pencil).toHaveTextContent(/^✏️$/); // an icon only, no word
    expect(pencil.closest('li')).toContainElement(screen.getByLabelText(`surface-row-${W1.id}`));
    fireEvent.click(pencil);
    const sheet = await screen.findByRole('dialog', { name: 'Edytuj powierzchnię' });
    expect(sheet).toContainElement(screen.getByLabelText('surface-form'));
    expect(screen.queryByLabelText('surface-width')).toBeNull(); // the size is the parts
    expect(screen.queryByLabelText('surface-type')).toBeNull();
    expect(screen.getByLabelText('merged-size-hint')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('surface-name'), { target: { value: 'Ściana północna' } });
    fireEvent.submit(screen.getByLabelText('surface-form'));
    await waitFor(() => expect(surfacesApi.updateSurface).toHaveBeenCalledWith(projectId, roomId, W1.id, { name: 'Ściana północna', description: null }));
    await waitFor(() => expect(screen.queryByLabelText('surface-form')).toBeNull());
  });

  it('closes the sheet with Escape', async () => {
    renderList();
    fireEvent.click(await screen.findByLabelText(`edit-surface-${W1.id}`)); // the pencil next to the name, no Opcje needed
    await screen.findByLabelText('surface-form');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByLabelText('surface-form')).toBeNull();
  });

  it('separates the wall after one confirmation', async () => {
    vi.mocked(surfacesApi.unmergeSurface).mockResolvedValue(W1);
    renderList();
    fireEvent.click(await screen.findByLabelText(`surface-row-${W1.id}`));
    fireEvent.click(await screen.findByLabelText(`unmerge-surface-${W1.id}`));
    expect(surfacesApi.unmergeSurface).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText(`unmerge-confirm-yes-${W1.id}`));
    await waitFor(() => expect(surfacesApi.unmergeSurface).toHaveBeenCalledWith(projectId, roomId, W1.id, []));
    expect(await screen.findByText('Ściana rozłączona')).toBeInTheDocument();
  });

  it('duplicates a merged wall: the next number and position, in sight next to "Rozłącz"', async () => {
    vi.mocked(surfacesApi.duplicateMergedSurface).mockResolvedValue({ ...merged, id: 'copy-1', name: 'Ściana 3' });
    renderList();
    fireEvent.click(await screen.findByLabelText(`surface-row-${W1.id}`));
    const duplicate = await screen.findByLabelText(`duplicate-merged-${W1.id}`);
    expect(duplicate).toHaveTextContent('Duplikuj');
    expect(duplicate.className).toContain('min-h-11');
    expect(duplicate.parentElement).toBe(screen.getByLabelText(`unmerge-surface-${W1.id}`).parentElement);
    fireEvent.click(duplicate);
    await waitFor(() => expect(surfacesApi.duplicateMergedSurface).toHaveBeenCalledWith(projectId, roomId, W1.id, { name: 'Ściana 3', position: expect.any(Number) }));
    expect(await screen.findByText('Ścianę zduplikowano')).toBeInTheDocument();
  });

  it('offers no duplicate of a merged wall in a rectangular room', async () => {
    renderList('RECTANGLE');
    fireEvent.click(await screen.findByLabelText(`surface-row-${W1.id}`));
    await screen.findByLabelText(`merged-parts-${W1.id}`);
    expect(screen.queryByLabelText(`duplicate-merged-${W1.id}`)).toBeNull();
  });

  it('separating a COPY asks for names that clash with no wall, the archived ones included', async () => {
    const copy = wall(5, '4.000', '2.500', {
      name: 'Ściana 5',
      parts: [
        { id: 'c-1', source_surface_id: W3.id, position: 0, width: '4.000', height: '2.500' },
        { id: 'c-2', source_surface_id: null, position: 1, width: '0.080', height: '2.700' },
        { id: 'c-3', source_surface_id: null, position: 2, width: '1.000', height: '2.000' },
      ],
    });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [merged, absorbed, copy], total: 3 });
    vi.mocked(surfacesApi.unmergeSurface).mockResolvedValue(copy);
    renderList();
    fireEvent.click(await screen.findByLabelText(`surface-row-${copy.id}`));
    fireEvent.click(await screen.findByLabelText(`unmerge-surface-${copy.id}`));
    fireEvent.click(screen.getByLabelText(`unmerge-confirm-yes-${copy.id}`));
    // the highest number is 5 ("Ściana 5"); the two new walls are 6 and 7
    await waitFor(() => expect(surfacesApi.unmergeSurface).toHaveBeenCalledWith(projectId, roomId, copy.id, ['Ściana 6', 'Ściana 7']));
  });

  it('a wall that was joined is shown with its merged wall and cannot be restored alone', async () => {
    renderList();
    const row = await screen.findByLabelText(`surface-row-${W2.id}`);
    expect(await screen.findByLabelText(`surface-row-merged-${W2.id}`)).toHaveTextContent('Połączona z: Ściana 1');
    fireEvent.click(row);
    fireEvent.click(await screen.findByLabelText(`options-toggle-${W2.id}`));
    expect(screen.queryByLabelText(`restore-surface-${W2.id}`)).toBeNull();
  });

  it('merged walls are not selectable for another merge', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [merged, W3, wall(4, '1.000', '2.000')], total: 3 });
    renderList();
    fireEvent.click(await screen.findByLabelText('merge-walls-start'));
    fireEvent.click(screen.getByLabelText(`surface-row-${W1.id}`));
    expect(screen.getByLabelText('merge-selected')).toHaveTextContent('Zaznaczone: 0');
    expect(screen.getByLabelText(`surface-row-${W1.id}`)).toHaveAttribute('aria-disabled', 'true');
  });
});

describe('the order of the walls', () => {
  const order = () => screen.getAllByLabelText(/^surface-item-/).map((li) => within(li).getByText(/Ściana \d/).textContent);

  it('is offered in an irregular room with two or more walls, and not in a rectangular one', async () => {
    renderList('RECTANGLE');
    await screen.findByLabelText(`surface-row-${W1.id}`);
    expect(screen.queryByLabelText('reorder-walls-start')).toBeNull();
  });

  it('shows ↑ ↓ on every wall, the first cannot go up and the last cannot go down', async () => {
    renderList();
    fireEvent.click(await screen.findByLabelText('reorder-walls-start'));
    expect(order()).toEqual(['Ściana 1', 'Ściana 2', 'Ściana 3']);
    expect(screen.getByLabelText(`wall-up-${W1.id}`)).toBeDisabled();
    expect(screen.getByLabelText(`wall-down-${W3.id}`)).toBeDisabled();
    expect(screen.getByLabelText(`wall-down-${W1.id}`)).toBeEnabled();
    expect(screen.getByLabelText(`wall-down-${W1.id}`).className).toContain('min-h-11');
    expect(screen.getByLabelText(`wall-down-${W1.id}`).className).toContain('min-w-11');
  });

  it('moves a wall at once and saves the whole order', async () => {
    vi.mocked(surfacesApi.reorderSurfaces).mockResolvedValue({ items: [W2, W1, W3], total: 3 });
    renderList();
    fireEvent.click(await screen.findByLabelText('reorder-walls-start'));
    fireEvent.click(screen.getByLabelText(`wall-down-${W1.id}`));
    expect(order()).toEqual(['Ściana 2', 'Ściana 1', 'Ściana 3']);
    await waitFor(() => expect(surfacesApi.reorderSurfaces).toHaveBeenCalledWith(projectId, roomId, [W2.id, W1.id, W3.id]));
    fireEvent.click(screen.getByLabelText(`wall-up-${W3.id}`));
    await waitFor(() => expect(surfacesApi.reorderSurfaces).toHaveBeenLastCalledWith(projectId, roomId, [W2.id, W3.id, W1.id]));
    expect(order()).toEqual(['Ściana 2', 'Ściana 3', 'Ściana 1']);
  });

  it('brings the real order back and says why when the server refuses', async () => {
    vi.mocked(surfacesApi.reorderSurfaces).mockRejectedValue(new ApiError('x', 409, 'WALL_REORDER_CANONICAL'));
    renderList();
    fireEvent.click(await screen.findByLabelText('reorder-walls-start'));
    const loads = vi.mocked(surfacesApi.fetchSurfaces).mock.calls.length;
    fireEvent.click(screen.getByLabelText(`wall-down-${W1.id}`));
    expect(await screen.findByRole('alert')).toHaveTextContent('Cztery ściany pokoju prostokątnego');
    await waitFor(() => expect(vi.mocked(surfacesApi.fetchSurfaces).mock.calls.length).toBeGreaterThan(loads));
    await waitFor(() => expect(order()).toEqual(['Ściana 1', 'Ściana 2', 'Ściana 3']));
  });

  it('lists only the active walls and ends with "Gotowe"', async () => {
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [W1, W2, wall(4, '1.000', '2.000', { is_archived: true })], total: 3 });
    renderList();
    fireEvent.click(await screen.findByLabelText('reorder-walls-start'));
    expect(order()).toEqual(['Ściana 1', 'Ściana 2']);
    fireEvent.click(screen.getByLabelText('reorder-done'));
    expect(screen.queryByLabelText('reorder-bar')).toBeNull();
    expect(screen.getByLabelText('reorder-walls-start')).toBeInTheDocument();
  });

  describe('dragging (press and hold)', () => {
    // jsdom has no layout: every row is 50 px tall, stacked from y = 100 in the order it has in the DOM
    let rects: { mockRestore: () => void };
    beforeEach(() => {
      rects = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
        const rows = Array.from(document.querySelectorAll('[aria-label^="surface-item-"]'));
        const i = rows.indexOf(this);
        const top = i < 0 ? 0 : 100 + i * 50;
        return { top, bottom: top + 50, height: 50, left: 0, right: 300, width: 300, x: 0, y: top, toJSON: () => ({}) } as DOMRect;
      });
      vi.spyOn(window, 'scrollBy').mockImplementation(() => undefined);
    });
    afterEach(() => rects.mockRestore());
    const touch = (y: number) => ({ touches: [{ clientX: 50, clientY: y }] });

    it('takes a wall by its ⠿ handle and puts it at the end with ONE save', async () => {
      vi.mocked(surfacesApi.reorderSurfaces).mockResolvedValue({ items: [W2, W3, W1], total: 3 });
      renderList();
      fireEvent.click(await screen.findByLabelText('reorder-walls-start'));
      fireEvent.pointerDown(screen.getByLabelText(`wall-drag-${W1.id}`), { clientY: 125, pointerType: 'touch' });
      expect(screen.getByLabelText(`surface-item-${W1.id}`)).toHaveAttribute('data-held', 'true');
      fireEvent.touchMove(document, touch(180));
      expect(order()).toEqual(['Ściana 2', 'Ściana 1', 'Ściana 3']);
      fireEvent.touchMove(document, touch(240));
      expect(order()).toEqual(['Ściana 2', 'Ściana 3', 'Ściana 1']);
      expect(surfacesApi.reorderSurfaces).not.toHaveBeenCalled(); // nothing is saved while the finger moves
      fireEvent.touchEnd(document);
      await waitFor(() => expect(surfacesApi.reorderSurfaces).toHaveBeenCalledTimes(1));
      expect(surfacesApi.reorderSurfaces).toHaveBeenCalledWith(projectId, roomId, [W2.id, W3.id, W1.id]);
      expect(order()).toEqual(['Ściana 2', 'Ściana 3', 'Ściana 1']);
      expect(screen.getByLabelText(`surface-item-${W1.id}`)).not.toHaveAttribute('data-held');
    });

    it('picks a wall up after holding the row, and moves it to the top', async () => {
      vi.mocked(surfacesApi.reorderSurfaces).mockResolvedValue({ items: [W3, W1, W2], total: 3 });
      renderList();
      fireEvent.click(await screen.findByLabelText('reorder-walls-start'));
      vi.useFakeTimers();
      fireEvent.touchStart(screen.getByLabelText(`surface-item-${W3.id}`), touch(225));
      act(() => { vi.advanceTimersByTime(400); });
      expect(screen.getByLabelText(`surface-item-${W3.id}`)).toHaveAttribute('data-held', 'true');
      fireEvent.touchMove(document, touch(105));
      fireEvent.touchEnd(document);
      vi.useRealTimers();
      expect(order()).toEqual(['Ściana 3', 'Ściana 1', 'Ściana 2']);
      await waitFor(() => expect(surfacesApi.reorderSurfaces).toHaveBeenCalledWith(projectId, roomId, [W3.id, W1.id, W2.id]));
    });

    it('a quick swipe scrolls the page and picks nothing up', async () => {
      renderList();
      fireEvent.click(await screen.findByLabelText('reorder-walls-start'));
      vi.useFakeTimers();
      fireEvent.touchStart(screen.getByLabelText(`surface-item-${W1.id}`), touch(125));
      fireEvent.touchMove(document, touch(160)); // moved 35 px before the hold time
      act(() => { vi.advanceTimersByTime(400); });
      fireEvent.touchEnd(document);
      vi.useRealTimers();
      expect(screen.getByLabelText(`surface-item-${W1.id}`)).not.toHaveAttribute('data-held');
      expect(order()).toEqual(['Ściana 1', 'Ściana 2', 'Ściana 3']);
      expect(surfacesApi.reorderSurfaces).not.toHaveBeenCalled();
    });

    it('a wall let go at its own place saves nothing', async () => {
      renderList();
      fireEvent.click(await screen.findByLabelText('reorder-walls-start'));
      fireEvent.pointerDown(screen.getByLabelText(`wall-drag-${W2.id}`), { clientY: 175, pointerType: 'touch' });
      fireEvent.touchMove(document, touch(170));
      fireEvent.touchEnd(document);
      await act(async () => { await Promise.resolve(); });
      expect(surfacesApi.reorderSurfaces).not.toHaveBeenCalled();
    });
  });

  it('speaks Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderList();
    expect(await screen.findByLabelText('reorder-walls-start')).toHaveTextContent('Изменить порядок');
    fireEvent.click(screen.getByLabelText('reorder-walls-start'));
    expect(screen.getByLabelText('reorder-done')).toHaveTextContent('Готово');
    expect(screen.getByLabelText(`wall-up-${W1.id}`)).toHaveAttribute('title', 'Передвинуть стену выше');
  });
});
