import { fetchAreaSegments } from '../api/areaSegments';
import { fetchChecklistTemplate, fetchChecklistTemplates } from '../api/checklists';
import { fetchClients } from '../api/clients';
import { ApiError } from '../api/http';
import { fetchInspection, fetchInspectionAnswers, fetchInspections } from '../api/inspections';
import { fetchOpenings } from '../api/openings';
import { fetchPayments } from '../api/payments';
import { fetchProjectNotes } from '../api/projectNotes';
import { fetchProject } from '../api/projects';
import { fetchProjectSummary, fetchRoom, fetchRooms } from '../api/rooms';
import { fetchSurfaces } from '../api/surfaces';
import { fetchSurfaceWorkPlan } from '../api/workPlans';
import { SUBSTRATE_ORDER } from '../components/InspectionList';
import { refreshPhotoStorage } from '../hooks/usePhotoStorage';
import { getMeta, setMeta } from './readCache';

export interface PrepareProgress {
  done: number;
  /** Grows while the rooms are discovered; the strip shows "done / total". */
  total: number;
}

export interface PrepareResult {
  /** Requests answered by the server (their answers are now kept on the phone). */
  saved: number;
  failed: number;
}

export interface PreparedNote {
  at: number;
  saved: number;
  failed: number;
}

export const preparedKey = (projectId: string) => `prepared:${projectId}`;

export const lastPrepared = (projectId: string) => getMeta<PreparedNote>(preparedKey(projectId));

/**
 * "Przygotuj do pracy offline": asks for everything the owner needs on site, one request at a time (gentle for a weak network).
 * Every answer is kept on the phone by `apiRequest` itself. A work plan that does not exist yet (404) is not a failure.
 */
export async function prepareProjectOffline(
  projectId: string,
  onProgress?: (progress: PrepareProgress) => void,
  shouldStop: () => boolean = () => false,
): Promise<PrepareResult> {
  let done = 0;
  let total = 0;
  let saved = 0;
  let failed = 0;
  const report = () => onProgress?.({ done, total });

  async function step<T>(request: () => Promise<T>): Promise<T | null> {
    total += 1;
    report();
    try {
      const value = await request();
      saved += 1;
      return value;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) saved += 1; // nothing there yet (a surface without a work plan)
      else failed += 1;
      return null;
    } finally {
      done += 1;
      report();
    }
  }

  await refreshPhotoStorage(); // so photos can be taken, and wait on the phone, without a signal (never fails: the last answer is kept)
  await step(() => fetchProject(projectId));
  await step(() => fetchProjectSummary(projectId));
  await step(() => fetchProjectNotes(projectId));
  // the settlements of the object (IA-4): the list that hides archived records and the one that shows them (a waiting restore needs the second)
  await step(() => fetchPayments(projectId));
  await step(() => fetchPayments(projectId, true));
  await step(() => fetchClients({ include_archived: true }));
  const templates = await step(() => fetchChecklistTemplates());
  // starting an inspection asks for the templates of one substrate, then for the template itself (Stage 19C.3)
  for (const substrate of SUBSTRATE_ORDER) {
    if (shouldStop()) break;
    await step(() => fetchChecklistTemplates(substrate));
  }
  // the floor is inspected with its own templates (the floor variants of concrete / other)
  const floorTemplates = await step(() => fetchChecklistTemplates(undefined, { forFloor: true }));
  for (const substrate of SUBSTRATE_ORDER) {
    if (shouldStop()) break;
    await step(() => fetchChecklistTemplates(substrate, { forFloor: true }));
  }
  // the substrates of the floor only are in both lists: each template is asked for once
  const templateIds = new Set([...(templates?.items ?? []), ...(floorTemplates?.items ?? [])].map((template) => template.id));
  for (const id of templateIds) {
    if (shouldStop()) break;
    await step(() => fetchChecklistTemplate(id));
  }

  const rooms = await step(() => fetchRooms(projectId));
  for (const room of rooms?.items ?? []) {
    if (shouldStop()) break;
    await step(() => fetchRoom(projectId, room.id));
    const surfaces = await step(() => fetchSurfaces(projectId, room.id));
    await step(() => fetchAreaSegments(projectId, room.id));
    for (const surface of surfaces?.items ?? []) {
      if (shouldStop()) break;
      if (surface.is_archived) continue;
      if (surface.surface_type === 'WALL') await step(() => fetchOpenings(projectId, room.id, surface.id));
      await step(() => fetchSurfaceWorkPlan(projectId, room.id, surface.id));
    }
    const inspections = await step(() => fetchInspections(projectId, room.id));
    for (const inspection of inspections?.items ?? []) {
      if (shouldStop()) break;
      await step(() => fetchInspection(projectId, room.id, inspection.id));
      await step(() => fetchInspectionAnswers(projectId, room.id, inspection.id));
    }
  }

  if (!shouldStop()) await setMeta(preparedKey(projectId), { at: Date.now(), saved, failed } satisfies PreparedNote);
  return { saved, failed };
}
