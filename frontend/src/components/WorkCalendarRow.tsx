import { useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import type { Reminder, ScheduleWarning } from '../types/calendar';
import { formatDayTime, formatShortDate } from '../utils/calendarFormat';

interface WorkCalendarRowProps {
  workKey: string;
  plannedDate: string | null;
  warnings: ScheduleWarning[];
  reminders: Reminder[];
  /** A done work needs no date; the reminders stay possible (a note, a call). */
  completed: boolean;
  onSetDate: (day: string | null) => Promise<unknown>;
  onRemind: () => void;
}

const input = 'w-full min-h-11 px-3 text-sm rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-control-bg-color)] text-[var(--tg-control-text-color)]';
const btn = 'w-full min-h-11 px-4 text-sm font-semibold rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)]';

/**
 * The calendar side of the card of a work (Stage 18E): the planned date with its warnings (a hint, never a block) and the
 * Remind button with the reminders that are already set.
 */
export function WorkCalendarRow({ workKey, plannedDate, warnings, reminders, completed, onSetDate, onRemind }: WorkCalendarRowProps) {
  const { t, locale } = useI18n();
  const s = t.calendar.schedule;
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  const change = async (day: string | null) => {
    setBusy(true);
    setError(false);
    try {
      await onSetDate(day);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  const warningText = (warning: ScheduleWarning) =>
    s.warnings[warning.code].replace('{date}', formatShortDate(warning.date, locale));

  return (
    <div aria-label={`work-calendar-${workKey}`} className="space-y-2">
      {!completed && (
        <div className="flex items-end gap-2">
          <label className="min-w-0 flex-1 space-y-1">
            <span className="text-xs text-[var(--tg-theme-hint-color)]">{s.planned_date}</span>
            <input
              type="date"
              aria-label={`planned-date-${workKey}`}
              value={plannedDate ?? ''}
              disabled={busy}
              onChange={(event) => void change(event.target.value || null)}
              className={input}
            />
          </label>
          {plannedDate && (
            <button
              type="button"
              aria-label={`planned-date-clear-${workKey}`}
              disabled={busy}
              onClick={() => void change(null)}
              className="shrink-0 min-h-11 px-3 text-sm font-semibold rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)]"
            >
              {s.clear}
            </button>
          )}
        </div>
      )}
      {warnings.map((warning) => (
        <p key={warning.code} role="status" aria-label={`schedule-warning-${workKey}`} className="text-xs font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">
          <span aria-hidden="true">⚠ </span>
          {warningText(warning)}
        </p>
      ))}
      {error && <p role="alert" className="text-xs font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">{s.save_error}</p>}
      {reminders.length > 0 && (
        <p aria-label={`reminder-chips-${workKey}`} className="text-xs text-[var(--tg-theme-text-color)] break-words">
          {t.calendar.remind.set_chip.replace('{when}', formatDayTime(reminders[0].send_at, locale))}
          {reminders.length > 1 ? ` (+${reminders.length - 1})` : ''}
        </p>
      )}
      <button type="button" aria-label={`remind-${workKey}`} onClick={onRemind} className={btn}>
        <span aria-hidden="true">🔔 </span>
        {t.calendar.remind.button}
      </button>
    </div>
  );
}
