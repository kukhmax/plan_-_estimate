import { useEffect, useId, useRef, useState } from 'react';
import { cancelReminder, createReminder } from '../api/calendar';
import { useI18n } from '../hooks/useI18n';
import { ApiError } from '../api/http';
import type { Reminder, ReminderPreset } from '../types/calendar';
import { todayIso } from '../utils/calendarFormat';

export interface ReminderContext {
  projectId?: string | null;
  roomId?: string | null;
  surfaceId?: string | null;
  occurrenceKey?: string | null;
  /** The note that is put in when the owner writes none (the name of the work). */
  defaultTitle?: string;
  hasPlannedDate?: boolean;
  /** The work is done and has a break: the end of it is a time the server knows. */
  hasBreakEnd?: boolean;
}

interface ReminderSheetProps {
  context: ReminderContext;
  /** Reminders already set for this place, so they can be seen and removed here. */
  existing?: Reminder[];
  /** Formats the time of an existing reminder (the owner's zone is known by the caller). */
  formatWhen?: (iso: string) => string;
  onClose: () => void;
  onChanged: () => void;
}

const btn = 'w-full min-h-11 px-4 text-sm font-semibold rounded-xl transition disabled:opacity-50';
const input = 'w-full min-h-11 px-3 text-sm rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-control-bg-color)] text-[var(--tg-control-text-color)]';

/**
 * The "Remind" button (Stage 18E): one sheet with a few big presets instead of a form. The preset says when; the server computes
 * the instant in the owner's zone. Two taps for the usual case: a preset, "save".
 */
export function ReminderSheet({ context, existing = [], formatWhen, onClose, onChanged }: ReminderSheetProps) {
  const { t } = useI18n();
  const r = t.calendar.remind;
  const titleId = useId();
  const [preset, setPreset] = useState<ReminderPreset>('IN_1H');
  const [note, setNote] = useState('');
  const [date, setDate] = useState(todayIso());
  const [time, setTime] = useState('09:00');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const presets: ReminderPreset[] = [
    ...(context.hasBreakEnd ? (['BREAK_END'] as const) : []),
    ...(context.hasPlannedDate ? (['WORK_DAY', 'DAY_BEFORE'] as const) : []),
    'IN_1H',
    'IN_3H',
    'TOMORROW',
    'CUSTOM',
  ];

  const errorText = (cause: unknown): string => {
    const code = cause instanceof ApiError ? cause.code : undefined;
    const known = r.errors as Record<string, string>;
    return (code && known[code]) || r.errors.generic;
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await createReminder({
        preset,
        title: note.trim() || context.defaultTitle || null,
        project_id: context.projectId ?? null,
        room_id: context.roomId ?? null,
        surface_id: context.surfaceId ?? null,
        occurrence_key: context.occurrenceKey ?? null,
        ...(preset === 'CUSTOM' ? { local_date: date, local_time: time } : {}),
      });
      if (!alive.current) return;
      onChanged();
      onClose();
    } catch (cause) {
      if (alive.current) setError(errorText(cause));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const remove = async (reminder: Reminder) => {
    setBusy(true);
    setError(null);
    try {
      await cancelReminder(reminder.id);
      if (alive.current) onChanged();
    } catch (cause) {
      if (alive.current) setError(errorText(cause));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50 p-0" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-t-2xl bg-[var(--tg-theme-bg-color)] p-4 space-y-3">
        <h3 id={titleId} className="text-base font-bold text-[var(--tg-theme-text-color)] break-words">{r.title}</h3>

        {existing.length > 0 && (
          <div aria-label="reminder-existing" className="space-y-1">
            <p className="text-xs font-semibold text-[var(--tg-theme-hint-color)]">{r.existing}</p>
            {existing.map((reminder) => (
              <div key={reminder.id} className="flex items-center justify-between gap-2">
                <span className="min-w-0 text-sm text-[var(--tg-theme-text-color)] break-words">
                  🔔 {formatWhen ? formatWhen(reminder.send_at) : reminder.send_at}
                  {reminder.title ? ` — ${reminder.title}` : ''}
                </span>
                <button
                  type="button"
                  aria-label={`reminder-remove-${reminder.id}`}
                  disabled={busy}
                  onClick={() => void remove(reminder)}
                  className="shrink-0 min-h-11 px-3 text-sm font-semibold rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-destructive-text-color)]"
                >
                  {r.remove}
                </button>
              </div>
            ))}
          </div>
        )}

        <div role="radiogroup" aria-label="reminder-presets" className="grid grid-cols-1 gap-2">
          {presets.map((name) => (
            <button
              key={name}
              type="button"
              role="radio"
              aria-checked={preset === name}
              aria-label={`reminder-preset-${name}`}
              onClick={() => setPreset(name)}
              className={`${btn} text-left break-words ${preset === name ? 'bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]' : 'border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)]'}`}
            >
              {r.presets[name]}
            </button>
          ))}
        </div>

        {preset === 'CUSTOM' && (
          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1 min-w-0">
              <span className="text-xs text-[var(--tg-theme-hint-color)]">{r.date}</span>
              <input type="date" aria-label="reminder-date" value={date} min={todayIso()} onChange={(event) => setDate(event.target.value)} className={input} />
            </label>
            <label className="space-y-1 min-w-0">
              <span className="text-xs text-[var(--tg-theme-hint-color)]">{r.time}</span>
              <input type="time" aria-label="reminder-time" value={time} onChange={(event) => setTime(event.target.value)} className={input} />
            </label>
          </div>
        )}

        <label className="block space-y-1">
          <span className="text-xs text-[var(--tg-theme-hint-color)]">{r.note}</span>
          <input
            type="text"
            aria-label="reminder-note"
            value={note}
            maxLength={120}
            placeholder={context.defaultTitle ?? r.note_placeholder}
            onChange={(event) => setNote(event.target.value)}
            className={input}
          />
        </label>

        {error && <p role="alert" className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">{error}</p>}

        <button type="button" aria-label="reminder-save" disabled={busy} onClick={() => void save()} className={`${btn} bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]`}>
          {busy ? r.saving : r.save}
        </button>
        <button type="button" aria-label="reminder-cancel" onClick={onClose} className={`${btn} border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)]`}>
          {r.cancel}
        </button>
      </div>
    </div>
  );
}
