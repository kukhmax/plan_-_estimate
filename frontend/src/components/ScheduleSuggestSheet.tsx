import { useEffect, useId, useRef, useState } from 'react';
import { applyPlannedDates, suggestDates } from '../api/calendar';
import { useI18n } from '../hooks/useI18n';
import type { PlannedDate, Schedule } from '../types/calendar';
import { formatDay, todayIso } from '../utils/calendarFormat';

interface ScheduleSuggestSheetProps {
  projectId: string;
  roomId: string;
  /** Names of the works of the open surface by occurrence key; the other surfaces of the room are counted. */
  workNames: Record<string, string>;
  onClose: () => void;
  onApplied: (schedule: Schedule) => void;
}

const btn = 'w-full min-h-11 px-4 text-sm font-semibold rounded-xl transition disabled:opacity-50';
const input = 'w-full min-h-11 px-3 text-sm rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-control-bg-color)] text-[var(--tg-control-text-color)]';

/**
 * "Suggest dates in order" (Stage 18E, decision Q12): from a day the owner names, the earliest working days for the works of the
 * room that are not done, after each technological break. Nothing is saved until the owner accepts the proposal.
 */
export function ScheduleSuggestSheet({ projectId, roomId, workNames, onClose, onApplied }: ScheduleSuggestSheetProps) {
  const { t, locale } = useI18n();
  const s = t.calendar.schedule;
  const titleId = useId();
  const [start, setStart] = useState(todayIso());
  const [proposal, setProposal] = useState<PlannedDate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const show = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await suggestDates(projectId, start, roomId);
      if (alive.current) setProposal(result);
    } catch {
      if (alive.current) setError(s.suggest_error);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const apply = async () => {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      const schedule = await applyPlannedDates(projectId, proposal);
      if (!alive.current) return;
      onApplied(schedule);
      onClose();
    } catch {
      if (alive.current) setError(s.suggest_error);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50 p-0" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-t-2xl bg-[var(--tg-theme-bg-color)] p-4 space-y-3">
        <h3 id={titleId} className="text-base font-bold text-[var(--tg-theme-text-color)] break-words">{s.suggest}</h3>
        <label className="block space-y-1">
          <span className="text-xs text-[var(--tg-theme-hint-color)]">{s.suggest_from}</span>
          <input type="date" aria-label="suggest-start" value={start} onChange={(event) => { setStart(event.target.value); setProposal(null); }} className={input} />
        </label>
        {!proposal && (
          <button type="button" aria-label="suggest-show" disabled={busy || !start} onClick={() => void show()} className={`${btn} bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]`}>
            {s.suggest_show}
          </button>
        )}
        {proposal && proposal.length === 0 && <p className="text-sm text-[var(--tg-theme-hint-color)]">{s.suggest_none}</p>}
        {proposal && proposal.length > 0 && (
          <div aria-label="suggest-proposal" className="space-y-1">
            <p className="text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">{s.suggest_summary.replace('{count}', String(proposal.length))}</p>
            <ul className="space-y-1">
              {proposal.filter((item) => workNames[item.occurrence_key]).map((item) => (
                <li key={item.occurrence_key} className="flex items-start justify-between gap-2 text-sm text-[var(--tg-theme-text-color)]">
                  <span className="min-w-0 break-words">{workNames[item.occurrence_key]}</span>
                  <span className="shrink-0 font-semibold">{formatDay(item.planned_date, locale)}</span>
                </li>
              ))}
            </ul>
            <button type="button" aria-label="suggest-apply" disabled={busy} onClick={() => void apply()} className={`${btn} bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]`}>
              {s.suggest_apply}
            </button>
          </div>
        )}
        {error && <p role="alert" className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">{error}</p>}
        <button type="button" aria-label="suggest-close" onClick={onClose} className={`${btn} border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)]`}>
          {s.suggest_close}
        </button>
      </div>
    </div>
  );
}
