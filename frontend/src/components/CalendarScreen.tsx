import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { cancelReminder, fetchAgenda, fetchCalendarSettings } from '../api/calendar';
import { fetchProjects } from '../api/projects';
import { transitionWorkExecution } from '../api/workPlans';
import { useI18n } from '../hooks/useI18n';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import type { Agenda, AgendaItem, AgendaWork } from '../types/calendar';
import type { ProjectType } from '../types/project';
import type { WorkExecutionStatus } from '../types/workPlan';
import { eventTitle, formatDay, formatShortDate, formatTime } from '../utils/calendarFormat';
import { priceItemLabel } from '../utils/executionFormat';
import { CalendarSettingsForm } from './CalendarSettingsForm';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';
import { ReminderSheet } from './ReminderSheet';
import { Ico } from './Ico';

const btn = 'w-full min-h-11 px-4 text-sm font-semibold rounded-xl transition disabled:opacity-60 break-words';
const primary = `${btn} bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]`;
const secondary = `${btn} border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)]`;
const card = 'min-w-0 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] p-3 space-y-2';

interface CalendarScreenProps {
  backSuspended?: boolean;
  /** Opens the screen of the object a line is about. */
  onOpenProject?: (projectId: string) => void;
}

/**
 * The calendar (Stage 18E): a list by day, not a month grid -- on a phone a list is read at once. First what is to be done today and what
 * is overdue (with a one-tap "in progress / done" that is the very status change of the card of the work), then the days ahead: the
 * events derived from the data of the objects and the owner's own reminders.
 */
export function CalendarScreen({ backSuspended = false, onOpenProject }: CalendarScreenProps) {
  const { t, locale } = useI18n();
  const c = t.calendar;
  const [view, setView] = useState<'agenda' | 'settings'>('agenda');
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [projects, setProjects] = useState<ProjectType[]>([]);
  const [projectId, setProjectId] = useState('');
  const [timeZone, setTimeZone] = useState('Europe/Warsaw');
  const [failed, setFailed] = useState(false);
  const [remindOpen, setRemindOpen] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const alive = useRef(true);

  useTelegramBackButton(view === 'settings' && !backSuspended, () => setView('agenda'));

  const load = useCallback(async () => {
    try {
      const next = await fetchAgenda({ projectId: projectId || undefined });
      if (!alive.current) return;
      setAgenda(next);
      setFailed(false);
    } catch {
      if (alive.current) setFailed(true);
    }
  }, [projectId]);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    fetchProjects()
      .then((response) => alive.current && setProjects(response.items))
      .catch(() => undefined); // the filter is a convenience: without it the whole agenda is still there
    fetchCalendarSettings()
      .then((settings) => alive.current && setTimeZone(settings.timezone))
      .catch(() => undefined);
  }, []);

  const mark = async (work: AgendaWork, status: WorkExecutionStatus) => {
    setBusyKey(work.occurrence_key);
    setNotice(null);
    try {
      await transitionWorkExecution(work.project_id, work.room_id, work.surface_id, work.occurrence_key, { status, expected_status: work.status });
      await load();
    } catch {
      if (alive.current) setNotice(c.mark_error);
    } finally {
      if (alive.current) setBusyKey(null);
    }
  };

  const removeReminder = async (item: AgendaItem) => {
    if (!item.reminder_id) return;
    setBusyKey(item.key);
    try {
      await cancelReminder(item.reminder_id);
      await load();
    } finally {
      if (alive.current) setBusyKey(null);
    }
  };

  const days = useMemo(() => {
    if (!agenda) return [];
    const byDay = new Map<string, { items: AgendaItem[]; works: AgendaWork[] }>();
    const slot = (day: string) => {
      if (!byDay.has(day)) byDay.set(day, { items: [], works: [] });
      return byDay.get(day)!;
    };
    for (const item of agenda.items) slot(item.day).items.push(item);
    for (const work of agenda.works) slot(work.planned_date).works.push(work);
    return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [agenda]);

  const workName = (work: AgendaWork) =>
    priceItemLabel(t, { name_key: work.work_name_key, display_name: work.work_display_name } as Parameters<typeof priceItemLabel>[1], t.work_plan.unavailable_item);

  const context = (parts: Array<string | null>) => parts.filter(Boolean).join(' · ');

  const renderWork = (work: AgendaWork, actions: boolean) => (
    <li key={work.occurrence_key} aria-label={`calendar-work-${work.occurrence_key}`} className={card}>
      <p className="min-w-0 text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">{workName(work)}</p>
      <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{context([work.project_name, work.room_name, work.surface_name])}</p>
      <div className="flex flex-wrap items-center gap-2">
        <ExecutionStatusBadge status={work.status} />
        <span className="text-xs text-[var(--tg-theme-hint-color)]">{c.planned_for.replace('{date}', formatShortDate(work.planned_date, locale))}</span>
      </div>
      {actions && (
        <div className="grid grid-cols-1 gap-2">
          {work.status === 'NOT_STARTED' && (
            <button type="button" aria-label={`calendar-start-${work.occurrence_key}`} disabled={busyKey === work.occurrence_key} onClick={() => void mark(work, 'IN_PROGRESS')} className={secondary}>
              <Ico>▶️</Ico>{c.mark_started}
            </button>
          )}
          <button type="button" aria-label={`calendar-done-${work.occurrence_key}`} disabled={busyKey === work.occurrence_key} onClick={() => void mark(work, 'COMPLETED')} className={primary}>
            <span aria-hidden="true">✓ </span><Ico>✅</Ico>{c.mark_done}
          </button>
        </div>
      )}
    </li>
  );

  const renderItem = (item: AgendaItem) => (
    <li key={item.key} aria-label={`calendar-item-${item.key}`} className={card}>
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">
          {item.source === 'REMINDER' && <span aria-hidden="true">🔔 </span>}
          {item.at && <span className="text-[var(--tg-theme-hint-color)]">{formatTime(item.at, locale, timeZone)} </span>}
          {eventTitle(c.event as unknown as Record<string, unknown>, item)}
        </p>
      </div>
      {context([item.project_name, item.room_name, item.surface_name]) && (
        <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{context([item.project_name, item.room_name, item.surface_name])}</p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-[var(--tg-theme-hint-color)]">{item.sends ? c.sends : c.calendar_only}</span>
        <div className="flex gap-2">
          {item.project_id && onOpenProject && (
            <button type="button" aria-label={`calendar-open-${item.key}`} onClick={() => onOpenProject(item.project_id!)} className="min-h-11 px-3 text-sm font-semibold rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)]">
              ›
            </button>
          )}
          {item.source === 'REMINDER' && (
            <button type="button" aria-label={`calendar-remove-${item.key}`} disabled={busyKey === item.key} onClick={() => void removeReminder(item)} className="min-h-11 px-3 text-sm font-semibold rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-destructive-text-color)]">
              <Ico>🗑️</Ico>{t.calendar.remind.remove}
            </button>
          )}
        </div>
      </div>
    </li>
  );

  if (view === 'settings') {
    return (
      <section aria-label="calendar-settings-section" className="w-full mt-4 space-y-3">
        <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{c.settings_page.title}</h2>
        <CalendarSettingsForm onSaved={(saved) => setTimeZone(saved.timezone)} />
        <button type="button" aria-label="calendar-settings-back" onClick={() => { setView('agenda'); void load(); }} className={secondary}>
          <Ico>⬅️</Ico>{c.settings_page.back}
        </button>
      </section>
    );
  }

  const today = agenda?.today ?? '';
  const todayEntry = days.find(([day]) => day === today)?.[1];
  const todayWorks = todayEntry?.works ?? [];
  const todayItems = todayEntry?.items ?? [];
  const later = days.filter(([day]) => day !== today);

  return (
    <section aria-label="calendar-section" className="w-full mt-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="min-w-0 text-lg font-bold text-[var(--tg-theme-text-color)] break-words">{c.title}</h2>
        <button type="button" aria-label="calendar-open-settings" onClick={() => setView('settings')} className="shrink-0 min-h-11 px-3 text-sm font-semibold rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)]">
          <Ico>⚙️</Ico>{c.settings}
        </button>
      </div>

      <select aria-label="calendar-project-filter" value={projectId} onChange={(event) => setProjectId(event.target.value)} className="w-full min-h-11 px-3 text-sm rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-control-bg-color)] text-[var(--tg-control-text-color)]">
        <option value="">{c.all_projects}</option>
        {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select>

      <button type="button" aria-label="calendar-add-reminder" onClick={() => setRemindOpen(true)} className={primary}><Ico>➕</Ico>{c.add_reminder}</button>

      {notice && <p role="alert" className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">{notice}</p>}
      {failed && (
        <div role="alert" className="space-y-2">
          <p className="text-sm text-[var(--tg-theme-destructive-text-color)] break-words">{c.load_error}</p>
          <button type="button" aria-label="calendar-retry" onClick={() => void load()} className={secondary}><Ico>🔄</Ico>{c.retry}</button>
        </div>
      )}
      {!agenda && !failed && <p className="text-sm text-[var(--tg-theme-hint-color)]">{c.loading}</p>}

      {agenda && (
        <>
          {agenda.overdue.length > 0 && (
            <div aria-label="calendar-overdue" className="space-y-2">
              <h3 className="text-sm font-bold text-[var(--tg-theme-destructive-text-color)]">{c.overdue} ({agenda.overdue.length})</h3>
              <ul className="space-y-2">{agenda.overdue.map((work) => renderWork(work, true))}</ul>
            </div>
          )}

          <div aria-label="calendar-today" className="space-y-2">
            <h3 className="text-sm font-bold text-[var(--tg-theme-text-color)]">{c.today} · {formatDay(today, locale)}</h3>
            {todayWorks.length === 0 && todayItems.length === 0 && <p className="text-sm text-[var(--tg-theme-hint-color)]">{c.today_empty}</p>}
            <ul className="space-y-2">
              {todayWorks.map((work) => renderWork(work, true))}
              {todayItems.map((item) => renderItem(item))}
            </ul>
          </div>

          <div aria-label="calendar-upcoming" className="space-y-3">
            <h3 className="text-sm font-bold text-[var(--tg-theme-text-color)]">{c.upcoming}</h3>
            {later.length === 0 && <p className="text-sm text-[var(--tg-theme-hint-color)]">{c.empty}</p>}
            {later.map(([day, entry]) => (
              <div key={day} aria-label={`calendar-day-${day}`} className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wide text-[var(--tg-theme-hint-color)]">{formatDay(day, locale)}</h4>
                <ul className="space-y-2">
                  {entry.works.map((work) => renderWork(work, false))}
                  {entry.items.map((item) => renderItem(item))}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}

      {remindOpen && (
        <ReminderSheet
          context={{ projectId: projectId || null }}
          onClose={() => setRemindOpen(false)}
          onChanged={() => void load()}
        />
      )}
    </section>
  );
}
