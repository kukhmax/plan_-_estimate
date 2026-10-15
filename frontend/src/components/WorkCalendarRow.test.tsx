import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import type { Reminder, ScheduleWarning } from '../types/calendar';
import { WorkCalendarRow } from './WorkCalendarRow';

const WARNING: ScheduleWarning = { occurrence_key: 'k', code: 'BEFORE_BREAK_END', date: '2026-10-13' };
const REMINDER = (id: string, sendAt: string): Reminder => ({
  id, project_id: 'p', room_id: null, surface_id: null, occurrence_key: 'k', origin: 'USER', kind: 'USER', title: 'x', send_at: sendAt, status: 'PENDING', close_on_status: null,
});

function row(props: Partial<React.ComponentProps<typeof WorkCalendarRow>> = {}) {
  const onSetDate = vi.fn().mockResolvedValue(undefined);
  const onRemind = vi.fn();
  render(
    <I18nProvider>
      <WorkCalendarRow workKey="k" plannedDate={null} warnings={[]} reminders={[]} completed={false} onSetDate={onSetDate} onRemind={onRemind} {...props} />
    </I18nProvider>,
  );
  return { onSetDate, onRemind };
}

beforeEach(() => localStorage.clear());

describe('the planned date', () => {
  it('sets a date as soon as it is chosen and clears it with one press', async () => {
    const { onSetDate } = row({ plannedDate: '2026-10-12' });
    expect(screen.getByLabelText('planned-date-k')).toHaveValue('2026-10-12');
    fireEvent.change(screen.getByLabelText('planned-date-k'), { target: { value: '2026-10-15' } });
    await waitFor(() => expect(onSetDate).toHaveBeenCalledWith('2026-10-15'));
    fireEvent.click(screen.getByLabelText('planned-date-clear-k'));
    await waitFor(() => expect(onSetDate).toHaveBeenLastCalledWith(null));
  });

  it('has no clear button while there is no date, and touch targets of 44 px', () => {
    row();
    expect(screen.queryByLabelText('planned-date-clear-k')).toBeNull();
    expect(screen.getByLabelText('planned-date-k').className).toContain('min-h-11');
    expect(screen.getByLabelText('remind-k').className).toContain('min-h-11');
  });

  it('is not asked for a work that is done, but the Remind button stays', () => {
    row({ completed: true, plannedDate: '2026-10-12' });
    expect(screen.queryByLabelText('planned-date-k')).toBeNull();
    expect(screen.getByLabelText('remind-k')).toBeInTheDocument();
  });

  it('says it when the date could not be saved', async () => {
    row({ onSetDate: vi.fn().mockRejectedValue(new Error('x')) });
    fireEvent.change(screen.getByLabelText('planned-date-k'), { target: { value: '2026-10-15' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zapisać daty.');
  });
});

describe('the warnings are a hint', () => {
  it('names the date of the end of the break, in Polish and in Russian', () => {
    row({ plannedDate: '2026-10-12', warnings: [WARNING] });
    expect(screen.getByLabelText('schedule-warning-k')).toHaveTextContent(/Wcześniej niż koniec przerwy poprzedniej pracy \(od .*2026.*\)\./);
  });

  it('is in Russian when the application is', () => {
    localStorage.setItem('locale', 'ru');
    row({ plannedDate: '2026-10-12', warnings: [{ ...WARNING, code: 'AFTER_CONTRACT_END', date: '2026-11-20' }] });
    expect(screen.getByLabelText('schedule-warning-k')).toHaveTextContent(/После окончания работ по договору \(.*2026.*\)\./);
  });

  it('shows nothing when there is no warning', () => {
    row({ plannedDate: '2026-10-12' });
    expect(screen.queryByLabelText('schedule-warning-k')).toBeNull();
  });
});

describe('the reminders', () => {
  it('shows the first one as a chip with the count of the others, and opens the sheet', () => {
    const { onRemind } = row({ reminders: [REMINDER('a', '2026-10-20T08:00:00Z'), REMINDER('b', '2026-10-21T08:00:00Z')] });
    expect(screen.getByLabelText('reminder-chips-k')).toHaveTextContent(/^🔔 .*\(\+1\)$/);
    fireEvent.click(screen.getByLabelText('remind-k'));
    expect(onRemind).toHaveBeenCalled();
  });

  it('shows no chip while nothing is set', () => {
    row();
    expect(screen.queryByLabelText('reminder-chips-k')).toBeNull();
  });
});
