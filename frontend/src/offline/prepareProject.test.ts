import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import * as areaApi from '../api/areaSegments';
import * as checklistsApi from '../api/checklists';
import * as clientsApi from '../api/clients';
import * as inspectionsApi from '../api/inspections';
import * as openingsApi from '../api/openings';
import * as paymentsApi from '../api/payments';
import * as notesApi from '../api/projectNotes';
import * as projectsApi from '../api/projects';
import * as roomsApi from '../api/rooms';
import * as surfacesApi from '../api/surfaces';
import * as workPlansApi from '../api/workPlans';
import { freshIndexedDb } from '../test/fakeIdb';
import { lastPrepared, prepareProjectOffline } from './prepareProject';
import { setOfflineOwner } from './readCache';

vi.mock('../api/areaSegments', () => ({ fetchAreaSegments: vi.fn() }));
vi.mock('../api/checklists', () => ({ fetchChecklistTemplates: vi.fn(), fetchChecklistTemplate: vi.fn() }));
vi.mock('../api/clients', () => ({ fetchClients: vi.fn() }));
vi.mock('../api/inspections', () => ({ fetchInspections: vi.fn(), fetchInspection: vi.fn(), fetchInspectionAnswers: vi.fn() }));
vi.mock('../api/openings', () => ({ fetchOpenings: vi.fn() }));
vi.mock('../api/payments', () => ({ fetchPayments: vi.fn() }));
vi.mock('../api/projectNotes', () => ({ fetchProjectNotes: vi.fn() }));
vi.mock('../api/projects', () => ({ fetchProject: vi.fn() }));
vi.mock('../api/rooms', () => ({ fetchRoom: vi.fn(), fetchRooms: vi.fn(), fetchProjectSummary: vi.fn() }));
vi.mock('../api/surfaces', () => ({ fetchSurfaces: vi.fn() }));
vi.mock('../api/workPlans', () => ({ fetchSurfaceWorkPlan: vi.fn() }));

const P = 'p1';
const ok = (items: unknown[] = []) => Promise.resolve({ items, total: items.length } as never);

describe('"Przygotuj do pracy offline" (Stage 19B)', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    localStorage.clear();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    vi.mocked(projectsApi.fetchProject).mockResolvedValue({} as never);
    vi.mocked(roomsApi.fetchProjectSummary).mockResolvedValue({} as never);
    vi.mocked(notesApi.fetchProjectNotes).mockImplementation(() => ok());
    vi.mocked(paymentsApi.fetchPayments).mockImplementation(() => ok());
    vi.mocked(clientsApi.fetchClients).mockImplementation(() => ok());
    vi.mocked(checklistsApi.fetchChecklistTemplates).mockImplementation(() => ok([{ id: 't1' }, { id: 't2' }]));
    vi.mocked(checklistsApi.fetchChecklistTemplate).mockResolvedValue({} as never);
    vi.mocked(roomsApi.fetchRooms).mockImplementation(() => ok([{ id: 'r1' }]));
    vi.mocked(roomsApi.fetchRoom).mockResolvedValue({} as never);
    vi.mocked(surfacesApi.fetchSurfaces).mockImplementation(() =>
      ok([
        { id: 'w1', surface_type: 'WALL', is_archived: false },
        { id: 'f1', surface_type: 'FLOOR', is_archived: false },
        { id: 'old', surface_type: 'WALL', is_archived: true },
      ]),
    );
    vi.mocked(areaApi.fetchAreaSegments).mockImplementation(() => ok());
    vi.mocked(openingsApi.fetchOpenings).mockImplementation(() => ok());
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue({} as never);
    vi.mocked(inspectionsApi.fetchInspections).mockImplementation(() => ok([{ id: 'i1' }]));
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue({} as never);
    vi.mocked(inspectionsApi.fetchInspectionAnswers).mockImplementation(() => ok());
  });

  it('asks for everything needed on site, one request at a time, and reports the progress', async () => {
    const seen: Array<[number, number]> = [];
    const result = await prepareProjectOffline(P, ({ done, total }) => seen.push([done, total]));

    // project, summary, notes, clients, templates(1+2), rooms(1) + room(5 + walls 2 + plans...) — counted by what was asked:
    expect(projectsApi.fetchProject).toHaveBeenCalledWith(P);
    expect(roomsApi.fetchProjectSummary).toHaveBeenCalledWith(P);
    expect(notesApi.fetchProjectNotes).toHaveBeenCalledWith(P);
    // the settlements of the object (IA-4): the list that hides archived records and the one that shows them
    expect(paymentsApi.fetchPayments).toHaveBeenCalledWith(P);
    expect(paymentsApi.fetchPayments).toHaveBeenCalledWith(P, true);
    expect(clientsApi.fetchClients).toHaveBeenCalledWith({ include_archived: true });
    expect(checklistsApi.fetchChecklistTemplate).toHaveBeenCalledTimes(2);
    // starting an inspection without a signal asks for the templates of ONE substrate (Stage 19C.3): every list is kept
    for (const substrate of ['CONCRETE', 'GYPSUM_PLASTER', 'CEMENT_LIME_PLASTER', 'GYPSUM_BOARD', 'PAINTED', 'OTHER']) {
      expect(checklistsApi.fetchChecklistTemplates).toHaveBeenCalledWith(substrate);
    }
    expect(roomsApi.fetchRoom).toHaveBeenCalledWith(P, 'r1');
    expect(surfacesApi.fetchSurfaces).toHaveBeenCalledWith(P, 'r1');
    expect(areaApi.fetchAreaSegments).toHaveBeenCalledWith(P, 'r1');
    expect(openingsApi.fetchOpenings).toHaveBeenCalledTimes(1); // the live wall only
    expect(openingsApi.fetchOpenings).toHaveBeenCalledWith(P, 'r1', 'w1');
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(2); // wall and floor, not the archived one
    expect(inspectionsApi.fetchInspection).toHaveBeenCalledWith(P, 'r1', 'i1');
    expect(inspectionsApi.fetchInspectionAnswers).toHaveBeenCalledWith(P, 'r1', 'i1');
    expect(result.failed).toBe(0);
    expect(result.saved).toBe(seen[seen.length - 1][1]);
    expect(seen[seen.length - 1][0]).toBe(seen[seen.length - 1][1]);
    // the total only grows, and "done" never passes it
    for (let i = 1; i < seen.length; i++) expect(seen[i][1]).toBeGreaterThanOrEqual(seen[i - 1][1]);
    for (const [done, total] of seen) expect(done).toBeLessThanOrEqual(total);
  });

  it('a work plan that does not exist yet (404) is not a failure; any other error is', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValue(new ApiError('Surface work plan not found', 404));
    expect((await prepareProjectOffline(P)).failed).toBe(0);

    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValue(new TypeError('Failed to fetch'));
    const result = await prepareProjectOffline(P);
    expect(result.failed).toBe(2);
  });

  it('one failed request does not stop the rest', async () => {
    vi.mocked(notesApi.fetchProjectNotes).mockRejectedValue(new ApiError('boom', 500));
    const result = await prepareProjectOffline(P);
    expect(result.failed).toBe(1);
    expect(roomsApi.fetchRooms).toHaveBeenCalled();
    expect(inspectionsApi.fetchInspectionAnswers).toHaveBeenCalled();
  });

  it('notes the time of a finished preparation, and not of one that was stopped', async () => {
    const before = Date.now();
    const result = await prepareProjectOffline(P);
    const note = await lastPrepared(P);
    expect(note?.saved).toBe(result.saved);
    expect(note?.at).toBeGreaterThanOrEqual(before);

    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    await prepareProjectOffline(P, undefined, () => true);
    expect(await lastPrepared(P)).toBeNull();
  });

  it('stops asking when told to (the screen was left)', async () => {
    let calls = 0;
    vi.mocked(roomsApi.fetchRooms).mockImplementation(() => {
      calls += 1;
      return ok([{ id: 'r1' }, { id: 'r2' }]);
    });
    await prepareProjectOffline(P, undefined, () => calls > 0);
    expect(roomsApi.fetchRoom).not.toHaveBeenCalled();
  });
});
