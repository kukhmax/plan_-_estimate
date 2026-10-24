import type { Locale } from '../utils/locale';
import type { WorkExecutionStatus } from './workPlan';

/** The API of Stage 18E mirrored: the agenda, the settings, the Remind button, the planned dates. */

export type ReminderPreset = 'BREAK_END' | 'WORK_DAY' | 'DAY_BEFORE' | 'IN_1H' | 'IN_3H' | 'TOMORROW' | 'CUSTOM';

export interface AgendaItem {
  source: 'EVENT' | 'REMINDER';
  kind: string;
  key: string;
  day: string; // YYYY-MM-DD in the owner's zone
  on: string | null;
  at: string | null;
  ref: string;
  title_key: string | null;
  title: string | null;
  params: Record<string, string | number>;
  sends: boolean;
  reminder_id: string | null;
  project_id: string | null;
  project_name: string | null;
  room_id: string | null;
  room_name: string | null;
  surface_id: string | null;
  surface_name: string | null;
  occurrence_key: string | null;
}

export interface AgendaWork {
  occurrence_key: string;
  planned_date: string;
  status: WorkExecutionStatus;
  wait_after_hours: number | null;
  project_id: string;
  project_name: string;
  room_id: string;
  room_name: string;
  surface_id: string;
  surface_name: string;
  work_name_key: string | null;
  work_display_name: string | null;
}

export interface Agenda {
  today: string;
  start: string;
  end: string;
  items: AgendaItem[];
  works: AgendaWork[];
  overdue: AgendaWork[];
}

export interface KindSetting {
  kind: string;
  default_push: boolean;
  sends: boolean;
}

export interface CalendarSettings {
  timezone: string;
  enabled: boolean;
  kind_overrides: Record<string, boolean>;
  quiet_from: string; // HH:MM:SS
  quiet_to: string;
  digest_at: string;
  language: Locale | null;
  kinds: KindSetting[];
  timezones: string[];
}

export interface CalendarSettingsUpdate {
  timezone: string;
  enabled: boolean;
  kind_overrides: Record<string, boolean>;
  quiet_from: string;
  quiet_to: string;
  digest_at: string;
  language: Locale | null;
}

export interface ReminderCreate {
  preset: ReminderPreset;
  title?: string | null;
  send_at?: string | null; // CUSTOM: an aware instant (the API)
  local_date?: string | null; // CUSTOM: or a day and a time of the day in the owner's zone, from the screen
  local_time?: string | null;
  project_id?: string | null;
  room_id?: string | null;
  surface_id?: string | null;
  occurrence_key?: string | null;
}

export interface Reminder {
  id: string;
  project_id: string | null;
  room_id: string | null;
  surface_id: string | null;
  occurrence_key: string | null;
  origin: string;
  kind: string;
  title: string | null;
  send_at: string;
  status: string;
  close_on_status: string | null;
}

export type ScheduleWarningCode = 'BEFORE_BREAK_END' | 'BEFORE_CONTRACT_START' | 'AFTER_CONTRACT_END';

export interface PlannedDate {
  occurrence_key: string;
  planned_date: string;
}

export interface ScheduleWarning {
  occurrence_key: string;
  code: ScheduleWarningCode;
  date: string;
}

export interface Schedule {
  planned: PlannedDate[];
  warnings: ScheduleWarning[];
  window_start: string | null;
  window_end: string | null;
}
