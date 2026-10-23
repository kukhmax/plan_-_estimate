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
    expect(block).toHaveTextContent('3.42 × 2.52');
    expect(block).toHaveTextContent('2.70 × 2.50');
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

  it('separates the wall after one confirmation', async () => {
    vi.mocked(surfacesApi.unmergeSurface).mockResolvedValue(W1);
    renderList();
    fireEvent.click(await screen.findByLabelText(`surface-row-${W1.id}`));
    fireEvent.click(await screen.findByLabelText(`unmerge-surface-${W1.id}`));
    expect(surfacesApi.unmergeSurface).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText(`unmerge-confirm-yes-${W1.id}`));
    await waitFor(() => expect(surfacesApi.unmergeSurface).toHaveBeenCalledWith(projectId, roomId, W1.id));
    expect(await screen.findByText('Ściana rozłączona')).toBeInTheDocument();
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
