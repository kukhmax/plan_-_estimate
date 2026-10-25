import type { HourFields, Margin, PaymentStage, Schedule, StageFields, WorkHour, WorkHours } from '../types/paymentSchedule';
import type { Payment } from '../types/payment';
import { apiRequest } from './http';

const stages = (projectId: string) => `/api/projects/${projectId}/payment-stages`;
const hours = (projectId: string) => `/api/projects/${projectId}/work-hours`;

/** The stages of the schedule of an object with what each is worth, what was received for it and where it stands (all the server's). */
export function fetchSchedule(projectId: string): Promise<Schedule> {
  return apiRequest(stages(projectId));
}

export function createStage(projectId: string, fields: StageFields): Promise<PaymentStage> {
  return apiRequest(stages(projectId), { method: 'POST', body: JSON.stringify(fields) });
}

/** Giving a share drops a fixed amount and the other way round; `due_on: null` clears the day. */
export function updateStage(projectId: string, stageId: string, fields: Partial<StageFields>): Promise<PaymentStage> {
  return apiRequest(`${stages(projectId)}/${stageId}`, { method: 'PATCH', body: JSON.stringify(fields) });
}

/** The money received for the stage stays, without a stage. */
export function deleteStage(projectId: string, stageId: string): Promise<void> {
  return apiRequest(`${stages(projectId)}/${stageId}`, { method: 'DELETE' });
}

/** The one-tap "received": the rest of the stage as one payment dated today. */
export function receiveStage(projectId: string, stageId: string): Promise<Payment> {
  return apiRequest(`${stages(projectId)}/${stageId}/receive`, { method: 'POST' });
}

export function fetchHours(projectId: string): Promise<WorkHours> {
  return apiRequest(hours(projectId));
}

export function createHours(projectId: string, fields: HourFields): Promise<WorkHour> {
  return apiRequest(hours(projectId), { method: 'POST', body: JSON.stringify(fields) });
}

export function updateHours(projectId: string, entryId: string, fields: Partial<HourFields>): Promise<WorkHour> {
  return apiRequest(`${hours(projectId)}/${entryId}`, { method: 'PATCH', body: JSON.stringify(fields) });
}

export function deleteHours(projectId: string, entryId: string): Promise<void> {
  return apiRequest(`${hours(projectId)}/${entryId}`, { method: 'DELETE' });
}

export function fetchMargin(projectId: string): Promise<Margin> {
  return apiRequest(`/api/projects/${projectId}/margin`);
}
