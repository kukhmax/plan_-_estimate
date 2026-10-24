import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as openingsApi from './api/openings';
import * as priceItemsApi from './api/priceItems';
import * as roomPlansApi from './api/roomWorkPlans';
import * as surfacesApi from './api/surfaces';
import * as workPlansApi from './api/workPlans';
import { RoomPlanSheet } from './components/RoomPlanSheet';
import { SurfaceList } from './components/SurfaceList';
import { I18nProvider } from './hooks/useI18n';
import type { PriceItem } from './types/priceItem';
import type { RoomWorkPlanResponse } from './types/roomWorkPlan';
import type { SurfaceType } from './types/surface';

vi.mock('./api/priceItems', () => ({ fetchPriceItems: vi.fn() }));
vi.mock('./api/roomWorkPlans', async () => {
  const actual = await vi.importActual<typeof import('./api/roomWorkPlans')>('./api/roomWorkPlans');
  return { ...actual, fetchRoomWorkPlan: vi.fn(), saveRoomWorkPlan: vi.fn(), followRoomWorkPlan: vi.fn() };
});
vi.mock('./api/surfaces', () => ({
  fetchSurfaces: vi.fn(), createSurface: vi.fn(), updateSurface: vi.fn(), archiveSurface: vi.fn(), restoreSurface: vi.fn(), generateWalls: vi.fn(),
  mergeSurfaces: vi.fn(), unmergeSurface: vi.fn(), duplicateMergedSurface: vi.fn(), reorderSurfaces: vi.fn(), updateSurfacePart: vi.fn(),
}));
vi.mock('./api/openings', () => ({ fetchOpenings: vi.fn(), createOpening: vi.fn(), updateOpening: vi.fn(), archiveOpening: vi.fn(), restoreOpening: vi.fn() }));
vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return { ...actual, fetchSurfaceWorkPlan: vi.fn(), putSurfaceWorkPlan: vi.fn(), applyWorkPlanToRoomWalls: vi.fn() };
});

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';

const item = (code: string, category: PriceItem['category'] = 'SKIM_COAT'): PriceItem => ({
  id: `id-${code}`, code, name_key: null, display_name: `Praca ${code}`, category, unit: 'M2', price: null, currency: 'PLN',
  price_scope: 'LABOR', quality_level: null, is_archived: false, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
});
const CATALOG = ['A', 'B', 'C', 'D'].map((code) => item(code));

const wall = (n: number): SurfaceType => ({
  id: `00000000-0000-0000-0000-00000000000${n}`, room_id: roomId, name: `Ściana ${n}`, surface_type: 'WALL', description: null, position: n,
  width: '3.000', height: '2.500', gross_area: '7.500', deduction_area: '0.000', net_area: '7.500', is_archived: false,
  created_at: '2026-10-24T10:00:00Z', updated_at: '2026-10-24T10:00:00Z',
});
const W1 = wall(1);
const W2 = wall(2);

const planResponse = (over: Partial<RoomWorkPlanResponse> = {}): RoomWorkPlanResponse => ({
  plan: { id: 'rp', room_id: roomId, substrate: 'GYPSUM_PLASTER', quality_target: 'S2', walls: ['id-A', 'id-B'], ceiling: ['id-C'], updated_at: null },
  surfaces: [
    { surface_id: W1.id, name: W1.name, surface_type: 'WALL', state: 'FOLLOWS', started: false },
    { surface_id: W2.id, name: W2.name, surface_type: 'WALL', state: 'OWN', started: false },
  ],
  results: [],
  ...over,
});

const wrap = (node: React.ReactNode) => render(<I18nProvider>{node}</I18nProvider>);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: CATALOG, total: 4 });
  vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockResolvedValue(planResponse());
  vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue({ items: [W1, W2], total: 2 });
  vi.mocked(openingsApi.fetchOpenings).mockResolvedValue([] as never);
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue({ id: 'p', surface_id: W1.id, substrate: 'CONCRETE', quality_target: 'S2', planned_works: [] } as never);
});

describe('the sheet "Plan pomieszczenia" (V2-5)', () => {
  const open = (props: Partial<React.ComponentProps<typeof RoomPlanSheet>> = {}) =>
    wrap(<RoomPlanSheet projectId={projectId} roomId={roomId} onClose={props.onClose ?? (() => undefined)} onSaved={props.onSaved ?? (() => undefined)} />);

  it('shows the saved plan: the class and the two lists in their order', async () => {
    open();
    const walls = await screen.findByLabelText('room-plan-walls');
    expect(within(walls).getByText('1. Praca A')).toBeInTheDocument();
    expect(within(walls).getByText('2. Praca B')).toBeInTheDocument();
    expect(within(screen.getByLabelText('room-plan-ceiling')).getByText('1. Praca C')).toBeInTheDocument();
    expect(screen.getByLabelText('room-plan-quality')).toHaveValue('S2');
  });

  it('starts empty when the room has no plan', async () => {
    vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockResolvedValue(planResponse({ plan: null, surfaces: [] }));
    open();
    await screen.findByLabelText('room-plan-walls');
    expect(within(screen.getByLabelText('room-plan-walls')).getByText('Brak prac')).toBeInTheDocument();
    expect(within(screen.getByLabelText('room-plan-ceiling')).getByText('Brak prac')).toBeInTheDocument();
  });

  it('adds, moves and removes works, and saves exactly what is on the screen', async () => {
    vi.mocked(roomPlansApi.saveRoomWorkPlan).mockResolvedValue(planResponse({ results: [{ surface_id: W1.id, name: 'Ściana 1', surface_type: 'WALL', outcome: 'UPDATED' }] }));
    open();
    await screen.findByLabelText('room-plan-walls');
    fireEvent.change(screen.getByLabelText('room-plan-walls-pick'), { target: { value: 'id-D' } });
    fireEvent.click(screen.getByLabelText('room-plan-walls-add'));
    fireEvent.click(screen.getByLabelText('room-plan-walls-up-2')); // D before B
    fireEvent.click(screen.getByLabelText('room-plan-walls-remove-0')); // A leaves
    fireEvent.click(screen.getByLabelText('room-plan-ceiling-remove-0'));
    fireEvent.click(screen.getByLabelText('room-plan-save'));
    await screen.findByLabelText('room-plan-report');
    expect(roomPlansApi.saveRoomWorkPlan).toHaveBeenCalledWith(projectId, roomId, { substrate: 'GYPSUM_PLASTER', quality_target: 'S2', walls: ['id-D', 'id-B'], ceiling: [] });
  });

  it('a drywall substrate takes a Q class', async () => {
    open();
    await screen.findByLabelText('room-plan-walls');
    fireEvent.change(screen.getByLabelText('room-plan-substrate'), { target: { value: 'GYPSUM_BOARD' } });
    expect(screen.getByLabelText('room-plan-quality')).toHaveValue('Q2');
  });

  it('reports what was made and what was left alone, and closing it reads the surfaces again', async () => {
    const onSaved = vi.fn();
    const onClose = vi.fn();
    vi.mocked(roomPlansApi.saveRoomWorkPlan).mockResolvedValue(planResponse({
      results: [
        { surface_id: 'a', name: 'Ściana 1', surface_type: 'WALL', outcome: 'CREATED' },
        { surface_id: 'b', name: 'Ściana 2', surface_type: 'WALL', outcome: 'UPDATED' },
        { surface_id: 'c', name: 'Wall 3', surface_type: 'WALL', outcome: 'SKIPPED_OWN' },
        { surface_id: 'e', name: 'Ceiling', surface_type: 'CEILING', outcome: 'SKIPPED_OWN' },
        { surface_id: 'd', name: 'Wall 4', surface_type: 'WALL', outcome: 'SKIPPED_STARTED' },
      ],
    }));
    open({ onSaved, onClose });
    await screen.findByLabelText('room-plan-walls');
    fireEvent.click(screen.getByLabelText('room-plan-save'));
    const report = await screen.findByLabelText('room-plan-report');
    expect(report).toHaveTextContent('Utworzono plany: 1');
    expect(report).toHaveTextContent('Zaktualizowano plany: 1');
    expect(report).toHaveTextContent('Pominięto (własny plan): Ściana 3, Sufit'); // the stored "Wall 3" / "Ceiling" are shown in the language of the application
    expect(report).not.toHaveTextContent('Wall');
    expect(report).toHaveTextContent('Pominięto (prace rozpoczęte): Ściana 4');
    expect(onSaved).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('room-plan-close'));
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('names a refusal it knows, keeps the sheet for another try on any other failure, and says when it cannot load', async () => {
    open();
    await screen.findByLabelText('room-plan-walls');
    vi.mocked(roomPlansApi.saveRoomWorkPlan).mockRejectedValueOnce(new roomPlansApi.RoomPlanRequestError('QUALITY_SCALE_MISMATCH', 422));
    fireEvent.click(screen.getByLabelText('room-plan-save'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Klasa jakości nie pasuje do podłoża');
    vi.mocked(roomPlansApi.saveRoomWorkPlan).mockRejectedValueOnce(new Error('x'));
    fireEvent.click(screen.getByLabelText('room-plan-save'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Nie udało się zapisać planu. Nic nie zostało zmienione.'));
    expect(screen.getByLabelText('room-plan-save')).not.toBeDisabled();
  });

  it('says so when the plan cannot be loaded, and Escape closes the sheet', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockRejectedValue(new Error('x'));
    const onClose = vi.fn();
    open({ onClose });
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać planu pomieszczenia.');
    expect(screen.getByLabelText('room-plan-save')).toBeDisabled();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});

describe('the list of walls with the plan of the room (V2-5)', () => {
  const list = () => wrap(<SurfaceList projectId={projectId} roomId={roomId} roomName="Salon" wallMode="CUSTOM" initiallyOpen={false} />);

  it('offers the plan of the room and opens the sheet', async () => {
    list();
    fireEvent.click(await screen.findByLabelText('room-plan-open'));
    expect(await screen.findByLabelText('room-plan-sheet')).toBeInTheDocument();
  });

  it('marks only the wall whose plan differs from the plan of the room', async () => {
    list();
    expect(await screen.findByLabelText(`surface-row-plan-${W2.id}`)).toHaveTextContent('Własny plan');
    expect(screen.queryByLabelText(`surface-row-plan-${W1.id}`)).toBeNull();
  });

  it('shows no marks while the room has no plan', async () => {
    vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockResolvedValue(planResponse({ plan: null }));
    list();
    await screen.findByLabelText('room-plan-open');
    await waitFor(() => expect(roomPlansApi.fetchRoomWorkPlan).toHaveBeenCalled());
    expect(screen.queryByLabelText(`surface-row-plan-${W2.id}`)).toBeNull();
  });

  it('brings a wall of its own plan back to the plan of the room', async () => {
    vi.mocked(roomPlansApi.followRoomWorkPlan).mockResolvedValue({ surface_id: W2.id, name: W2.name, surface_type: 'WALL', outcome: 'UPDATED' });
    list();
    fireEvent.click(await screen.findByLabelText(`surface-row-${W2.id}`));
    expect(await screen.findByLabelText(`plan-state-${W2.id}`)).toHaveTextContent('Własny plan');
    vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockResolvedValue(planResponse({
      surfaces: [
        { surface_id: W1.id, name: W1.name, surface_type: 'WALL', state: 'FOLLOWS', started: false },
        { surface_id: W2.id, name: W2.name, surface_type: 'WALL', state: 'FOLLOWS', started: false },
      ],
    }));
    fireEvent.click(screen.getByLabelText(`back-to-room-plan-${W2.id}`));
    await waitFor(() => expect(roomPlansApi.followRoomWorkPlan).toHaveBeenCalledWith(projectId, roomId, W2.id));
    expect(await screen.findByText('Plan wrócił do planu pokoju.')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText(`plan-state-${W2.id}`)).toHaveTextContent('Plan pokoju'));
    expect(screen.queryByLabelText(`back-to-room-plan-${W2.id}`)).toBeNull();
  });

  it('says so when the work on the wall has started', async () => {
    vi.mocked(roomPlansApi.followRoomWorkPlan).mockRejectedValue(new roomPlansApi.RoomPlanRequestError('ROOM_PLAN_STARTED', 409));
    list();
    fireEvent.click(await screen.findByLabelText(`surface-row-${W2.id}`));
    fireEvent.click(await screen.findByLabelText(`back-to-room-plan-${W2.id}`));
    expect(await screen.findByRole('alert')).toHaveTextContent('Prace na tej ścianie już się rozpoczęły');
  });
});
