import type {
  Agenda,
  CalendarSettings,
  CalendarSettingsUpdate,
  PlannedDate,
  Reminder,
  ReminderCreate,
  Schedule,
} from '../types/calendar';
import { apiRequest } from './http';

export function fetchAgenda(options: { start?: string; end?: string; projectId?: string } = {}): Promise<Agenda> {
  const query = new URLSearchParams();
  if (options.start) query.set('start', options.start);
  if (options.end) query.set('end', options.end);
  if (options.projectId) query.set('project_id', options.projectId);
  const suffix = query.toString();
  return apiRequest(`/api/calendar${suffix ? `?${suffix}` : ''}`);
}

export function fetchCalendarSettings(): Promise<CalendarSettings> {
  return apiRequest('/api/calendar/settings');
}

export function saveCalendarSettings(settings: CalendarSettingsUpdate): Promise<CalendarSettings> {
  return apiRequest('/api/calendar/settings', { method: 'PUT', body: JSON.stringify(settings) });
}

export async function listReminders(projectId?: string): Promise<Reminder[]> {
  const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  const response = await apiRequest<{ items: Reminder[] }>(`/api/calendar/reminders${suffix}`);
  return response.items;
}

/** The Remind button: the preset says when; the server computes the instant in the owner's zone. */
export function createReminder(body: ReminderCreate): Promise<Reminder> {
  return apiRequest('/api/calendar/reminders', { method: 'POST', body: JSON.stringify(body) });
}

export function cancelReminder(reminderId: string): Promise<Reminder> {
  return apiRequest(`/api/calendar/reminders/${encodeURIComponent(reminderId)}`, { method: 'DELETE' });
}

const schedulePath = (projectId: string) => `/api/projects/${encodeURIComponent(projectId)}/schedule`;

export function fetchSchedule(projectId: string): Promise<Schedule> {
  return apiRequest(schedulePath(projectId));
}

export function setPlannedDate(projectId: string, occurrenceKey: string, plannedDate: string | null): Promise<Schedule> {
  return apiRequest(`${schedulePath(projectId)}/${encodeURIComponent(occurrenceKey)}`, {
    method: 'PUT',
    body: JSON.stringify({ planned_date: plannedDate }),
  });
}

/** A proposal of dates in the order of the works; nothing is saved until it is applied. */
export function suggestDates(projectId: string, start: string, roomId?: string): Promise<PlannedDate[]> {
  return apiRequest(`${schedulePath(projectId)}/suggest`, {
    method: 'POST',
    body: JSON.stringify({ start, room_id: roomId ?? null }),
  });
}

export function applyPlannedDates(projectId: string, dates: PlannedDate[]): Promise<Schedule> {
  return apiRequest(`${schedulePath(projectId)}/apply`, { method: 'POST', body: JSON.stringify({ dates }) });
}
