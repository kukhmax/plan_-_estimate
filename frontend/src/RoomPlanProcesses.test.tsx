import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as priceItemsApi from './api/priceItems';
import * as roomPlansApi from './api/roomWorkPlans';
import * as roomsApi from './api/rooms';
import * as templatesApi from './api/workflowTemplates';
import * as workPlansApi from './api/workPlans';
import { RoomPlanSheet } from './components/RoomPlanSheet';
import { I18nProvider } from './hooks/useI18n';
import type { PriceItem } from './types/priceItem';
import type { RoomWorkPlanResponse } from './types/roomWorkPlan';
import type { WorkflowTemplateRead, WorkflowTemplateStepRead } from './types/workflowTemplate';

vi.mock('./api/priceItems', () => ({ fetchPriceItems: vi.fn() }));
vi.mock('./api/rooms', async (importOriginal) => ({ ...(await importOriginal<typeof import('./api/rooms')>()), fetchRooms: vi.fn() }));
vi.mock('./api/workflowTemplates', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api/workflowTemplates')>()),
  fetchCompatibleTemplates: vi.fn(),
}));
vi.mock('./api/roomWorkPlans', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api/roomWorkPlans')>()),
  fetchRoomWorkPlan: vi.fn(),
  saveRoomWorkPlan: vi.fn(),
}));
vi.mock('./api/workPlans', async (importOriginal) => ({ ...(await importOriginal<typeof import('./api/workPlans')>()), fetchSurfaceWorkPlan: vi.fn() }));

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const otherRoomId = '33333333-3333-3333-3333-333333333333';

const item = (code: string): PriceItem => ({
  id: `id-${code}`, code, name_key: null, display_name: `Praca ${code}`, category: 'SKIM_COAT', unit: 'M2', price: null, currency: 'PLN',
  price_scope: 'LABOR', quality_level: null, is_archived: false, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
});
const CATALOG = ['A', 'B', 'C', 'D', 'E'].map(item);

const step = (code: string, position: number, optional = false, archived = false): WorkflowTemplateStepRead => ({
  id: `s-${code}`, position, price_item_id: `id-${code}`, is_optional: optional, note: null, wait_after_hours: null,
  price_item: { id: `id-${code}`, code, name_key: null, display_name: `Praca ${code}`, category: 'SKIM_COAT', unit: 'M2', price_scope: 'LABOR', price: null, currency: 'PLN', is_archived: archived, quality_level: null },
});
const template = (id: string, name: string, steps: WorkflowTemplateStepRead[]): WorkflowTemplateRead => ({
  id, code: id, name_key: null, display_name: name, description: null, applies_to_substrates: [], applies_to_quality: [], applies_to_surface_types: [],
  position: 0, is_archived: false, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z', steps,
});

const response = (over: Partial<RoomWorkPlanResponse> = {}): RoomWorkPlanResponse => ({ plan: null, surfaces: [], results: [], ...over });
const surfacePlan = (ids: string[], substrate = 'CONCRETE', quality: string | null = 'S3') => ({
  id: 'p', surface_id: 'x', substrate, quality_target: quality,
  planned_works: ids.map((id, position) => ({ id: `w${position}`, work_plan_id: 'p', price_item_id: id, position, occurrence_key: `k${position}`, wait_after_hours: null, price_item: null })),
});

const open = () => render(<I18nProvider><RoomPlanSheet projectId={projectId} roomId={roomId} onClose={() => undefined} onSaved={() => undefined} /></I18nProvider>);
const listOf = (target: 'walls' | 'ceiling') =>
  within(screen.getByLabelText(`room-plan-${target}`)).queryAllByText(/^\d+\. /).map((node) => node.textContent);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: CATALOG, total: CATALOG.length });
  vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockResolvedValue(response());
  vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [], total: 0 } as never);
  vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({
    items: [template('t1', 'Gładź S2 na tynku', [step('A', 1), step('B', 2, true), step('C', 3)]), template('t-empty', 'Pusty', [])],
    total: 2,
  });
});

describe('B1: the processes of the price book in the plan of a room', () => {
  it('offers the processes of the substrate, the class and the walls, and puts the required steps into an empty list', async () => {
    open();
    fireEvent.click(await screen.findByLabelText('room-plan-walls-process-open'));
    await waitFor(() => expect(templatesApi.fetchCompatibleTemplates).toHaveBeenCalledWith({ substrate: 'GYPSUM_PLASTER', quality_target: 'S2', surface_type: 'WALL' }));
    const panel = screen.getByLabelText('room-plan-walls-process');
    expect(within(panel).queryByText('Pusty')).toBeNull(); // a process without steps cannot be used
    fireEvent.click(await within(panel).findByLabelText('room-plan-process-t1'));
    expect(within(panel).getByLabelText('room-plan-process-step-0')).toBeChecked();
    expect(within(panel).getByLabelText('room-plan-process-step-0')).toBeDisabled();
    expect(within(panel).getByLabelText('room-plan-process-step-1')).not.toBeChecked(); // the optional step starts off
    fireEvent.click(within(panel).getByLabelText('room-plan-walls-process-insert'));
    expect(listOf('walls')).toEqual(['1. Praca A', '2. Praca C']);
    expect(listOf('ceiling')).toEqual([]);
    expect(screen.getByLabelText('room-plan-notice')).toHaveTextContent('Wstawiono kroki: 2.');
    expect(screen.queryByLabelText('room-plan-walls-process')).toBeNull();
  });

  it('a ticked optional step goes in; with works already listed the steps replace them or go after them; the ceiling asks for its own processes', async () => {
    vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockResolvedValue(response({
      plan: { id: 'rp', room_id: roomId, substrate: 'GYPSUM_PLASTER', quality_target: 'S2', walls: ['id-E'], ceiling: ['id-D'], updated_at: null },
    }));
    vi.mocked(roomPlansApi.saveRoomWorkPlan).mockResolvedValue(response());
    open();
    fireEvent.click(await screen.findByLabelText('room-plan-walls-process-open'));
    fireEvent.click(await screen.findByLabelText('room-plan-process-t1'));
    fireEvent.click(screen.getByLabelText('room-plan-process-step-1'));
    expect(screen.queryByLabelText('room-plan-walls-process-insert')).toBeNull();
    fireEvent.click(screen.getByLabelText('room-plan-walls-process-append'));
    expect(listOf('walls')).toEqual(['1. Praca E', '2. Praca A', '3. Praca B', '4. Praca C']);

    fireEvent.click(screen.getByLabelText('room-plan-ceiling-process-open'));
    await waitFor(() => expect(templatesApi.fetchCompatibleTemplates).toHaveBeenLastCalledWith({ substrate: 'GYPSUM_PLASTER', quality_target: 'S2', surface_type: 'CEILING' }));
    fireEvent.click(await screen.findByLabelText('room-plan-process-t1'));
    fireEvent.click(screen.getByLabelText('room-plan-ceiling-process-replace'));
    expect(listOf('ceiling')).toEqual(['1. Praca A', '2. Praca C']);

    fireEvent.click(screen.getByLabelText('room-plan-save'));
    await screen.findByLabelText('room-plan-report');
    expect(roomPlansApi.saveRoomWorkPlan).toHaveBeenCalledWith(projectId, roomId, {
      substrate: 'GYPSUM_PLASTER', quality_target: 'S2', walls: ['id-E', 'id-A', 'id-B', 'id-C'], ceiling: ['id-A', 'id-C'],
    });
  });

  it('leaves out an archived optional step and refuses a process whose required step is archived', async () => {
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({
      items: [
        template('t1', 'Z opcją', [step('A', 1), step('B', 2, true, true)]),
        template('t2', 'Zepsuty', [step('C', 1, false, true), step('D', 2)]),
      ],
      total: 2,
    });
    open();
    fireEvent.click(await screen.findByLabelText('room-plan-walls-process-open'));
    fireEvent.click(await screen.findByLabelText('room-plan-process-t1'));
    expect(screen.getByLabelText('room-plan-process-step-1')).toBeDisabled();
    expect(screen.getByLabelText('room-plan-walls-process-insert')).toHaveTextContent('(1)');
    fireEvent.click(screen.getByLabelText('room-plan-walls-process-back'));
    fireEvent.click(screen.getByLabelText('room-plan-process-t2'));
    expect(screen.getByRole('alert')).toHaveTextContent('Wymagany krok');
    expect(screen.getByLabelText('room-plan-walls-process-insert')).toBeDisabled();
  });

  it('asks for the class first and fetches nothing without it', async () => {
    vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockResolvedValue(response({
      plan: { id: 'rp', room_id: roomId, substrate: 'CONCRETE', quality_target: null, walls: [], ceiling: [], updated_at: null },
    }));
    open();
    fireEvent.click(await screen.findByLabelText('room-plan-walls-process-open'));
    expect(screen.getByLabelText('room-plan-walls-process')).toHaveTextContent('Najpierw wybierz klasę jakości');
    expect(templatesApi.fetchCompatibleTemplates).not.toHaveBeenCalled();
  });

  it('says so when the processes cannot be read, and closes', async () => {
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockRejectedValue(new Error('x'));
    open();
    fireEvent.click(await screen.findByLabelText('room-plan-walls-process-open'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać procesów technologicznych.');
    fireEvent.click(screen.getByLabelText('room-plan-walls-process-close'));
    expect(screen.queryByLabelText('room-plan-walls-process')).toBeNull();
  });
});

describe('B1: "Skopiuj plan z innego pomieszczenia"', () => {
  beforeEach(() => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({
      items: [{ id: roomId, name: 'Salon' }, { id: otherRoomId, name: 'Sypialnia' }],
      total: 2,
    } as never);
  });

  it('offers the other rooms only and copies the plan of the room without saving it', async () => {
    vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockImplementation(async (_project, room) =>
      room === otherRoomId
        ? response({ plan: { id: 'rp2', room_id: otherRoomId, substrate: 'CONCRETE', quality_target: 'S3', walls: ['id-B', 'id-C'], ceiling: ['id-D'], updated_at: null } })
        : response(),
    );
    open();
    const pick = await screen.findByLabelText('room-plan-copy-room-pick');
    expect(within(pick).getAllByRole('option').map((o) => o.textContent)).toEqual(['Skopiuj plan z innego pomieszczenia', 'Sypialnia']);
    expect(screen.getByLabelText('room-plan-copy-room-button')).toBeDisabled();
    fireEvent.change(pick, { target: { value: otherRoomId } });
    fireEvent.click(screen.getByLabelText('room-plan-copy-room-button'));
    await waitFor(() => expect(listOf('walls')).toEqual(['1. Praca B', '2. Praca C']));
    expect(listOf('ceiling')).toEqual(['1. Praca D']);
    expect(screen.getByLabelText('room-plan-substrate')).toHaveValue('CONCRETE');
    expect(screen.getByLabelText('room-plan-quality')).toHaveValue('S3');
    expect(screen.getByLabelText('room-plan-notice')).toHaveTextContent('Skopiowano plan z: Sypialnia.');
    expect(roomPlansApi.saveRoomWorkPlan).not.toHaveBeenCalled();
  });

  it('a room without a plan of the room gives the plans of its first wall and its ceiling', async () => {
    vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockImplementation(async (_project, room) =>
      room === otherRoomId
        ? response({
            surfaces: [
              { surface_id: 'w0', name: 'Wall 1', surface_type: 'WALL', state: 'NONE', started: false },
              { surface_id: 'w1', name: 'Wall 2', surface_type: 'WALL', state: 'OWN', started: false },
              { surface_id: 'c1', name: 'Ceiling', surface_type: 'CEILING', state: 'OWN', started: false },
            ],
          })
        : response(),
    );
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockImplementation(async (_p, _r, surfaceId) =>
      (surfaceId === 'w1' ? surfacePlan(['id-E', 'id-A'], 'PAINTED', 'S4') : surfacePlan(['id-B'], 'GYPSUM_PLASTER', 'S2')) as never,
    );
    open();
    fireEvent.change(await screen.findByLabelText('room-plan-copy-room-pick'), { target: { value: otherRoomId } });
    fireEvent.click(screen.getByLabelText('room-plan-copy-room-button'));
    await waitFor(() => expect(listOf('walls')).toEqual(['1. Praca E', '2. Praca A']));
    expect(listOf('ceiling')).toEqual(['1. Praca B']);
    expect(screen.getByLabelText('room-plan-substrate')).toHaveValue('PAINTED');
    expect(screen.getByLabelText('room-plan-quality')).toHaveValue('S4');
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledWith(projectId, otherRoomId, 'w1');
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledWith(projectId, otherRoomId, 'c1');
  });

  it('says so when the other room has no plan at all, or cannot be read, and changes nothing', async () => {
    vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockImplementation(async (_project, room) =>
      room === otherRoomId ? response({ surfaces: [{ surface_id: 'w0', name: 'Wall 1', surface_type: 'WALL', state: 'NONE', started: false }] }) : response(),
    );
    open();
    fireEvent.change(await screen.findByLabelText('room-plan-copy-room-pick'), { target: { value: otherRoomId } });
    fireEvent.click(screen.getByLabelText('room-plan-copy-room-button'));
    expect(await screen.findByRole('alert')).toHaveTextContent('W tym pomieszczeniu nie ma jeszcze planu prac.');
    expect(listOf('walls')).toEqual([]);

    vi.mocked(roomPlansApi.fetchRoomWorkPlan).mockRejectedValue(new Error('x'));
    fireEvent.click(screen.getByLabelText('room-plan-copy-room-button'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Nie udało się wczytać planu tego pomieszczenia.'));
  });

  it('is not shown when the object has no other room', async () => {
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [{ id: roomId, name: 'Salon' }], total: 1 } as never);
    open();
    await screen.findByLabelText('room-plan-walls');
    expect(screen.queryByLabelText('room-plan-copy-room-pick')).toBeNull();
  });
});
