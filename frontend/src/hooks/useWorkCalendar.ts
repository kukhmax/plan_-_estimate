import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchSchedule, listReminders, setPlannedDate } from '../api/calendar';
import type { Reminder, Schedule } from '../types/calendar';

const EMPTY: Schedule = { planned: [], warnings: [], window_start: null, window_end: null };

/**
 * The planned dates, their warnings and the waiting own reminders of one object, for the cards of its works (Stage 18E).
 * A failed read is not an error of the card: the work is shown without a date, the status and the photos still work.
 */
export function useWorkCalendar(projectId: string) {
  const [schedule, setSchedule] = useState<Schedule>(EMPTY);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [failed, setFailed] = useState(false);
  const alive = useRef(true);

  const reload = useCallback(async () => {
    try {
      const [nextSchedule, nextReminders] = await Promise.all([fetchSchedule(projectId), listReminders(projectId)]);
      if (!alive.current) return;
      setSchedule(nextSchedule);
      setReminders(nextReminders);
      setFailed(false);
    } catch {
      if (alive.current) setFailed(true);
    }
  }, [projectId]);

  useEffect(() => {
    alive.current = true;
    void reload();
    return () => {
      alive.current = false;
    };
  }, [reload]);

  const setDate = useCallback(
    async (occurrenceKey: string, day: string | null) => {
      const next = await setPlannedDate(projectId, occurrenceKey, day);
      if (alive.current) setSchedule(next);
      return next;
    },
    [projectId],
  );

  return { schedule, reminders, failed, reload, setDate, setSchedule };
}
