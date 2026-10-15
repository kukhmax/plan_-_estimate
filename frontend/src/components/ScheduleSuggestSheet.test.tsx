import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/calendar';
import { I18nProvider } from '../hooks/useI18n';
import type { Schedule } from '../types/calendar';
import { ScheduleSuggestSheet } from './ScheduleSuggestSheet';

vi.mock('../api/calendar', () => ({ suggestDates: vi.fn(), applyPlannedDates: vi.fn() }));

const SCHEDULE: Schedule = { planned: [], warnings: [], window_start: null, window_end: null };
const PROPOSAL = [
  { occurrence_key: 'k1', planned_date: '2026-10-12' },
  { occurrence_key: 'k2', planned_date: '2026-10-13' },
  { occurrence_key: 'other-surface', planned_date: '2026-10-12' },
];

function open() {
  const onClose = vi.fn();
  const onApplied = vi.fn();
  render(
    <I18nProvider>
      <ScheduleSuggestSheet projectId="p" roomId="r" workNames={{ k1: 'Gruntowanie', k2: 'Gładź' }} onClose={onClose} onApplied={onApplied} />
    </I18nProvider>,
  );
  return { onClose, onApplied };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.suggestDates).mockResolvedValue(PROPOSAL);
  vi.mocked(api.applyPlannedDates).mockResolvedValue(SCHEDULE);
});

describe('the proposal', () => {
  it('asks for the room and the day, shows the works of this surface and counts the whole room', async () => {
    open();
    fireEvent.change(screen.getByLabelText('suggest-start'), { target: { value: '2026-10-12' } });
    fireEvent.click(screen.getByLabelText('suggest-show'));
    const proposal = await screen.findByLabelText('suggest-proposal');
    expect(api.suggestDates).toHaveBeenCalledWith('p', '2026-10-12', 'r');
    expect(proposal).toHaveTextContent('Propozycja dla 3 prac w pomieszczeniu');
    expect(proposal).toHaveTextContent('Gruntowanie');
    expect(proposal).toHaveTextContent('Gładź');
    expect(proposal).not.toHaveTextContent('other-surface');
  });

  it('saves nothing until it is accepted, and then saves all of it at once', async () => {
    const { onApplied, onClose } = open();
    fireEvent.click(screen.getByLabelText('suggest-show'));
    await screen.findByLabelText('suggest-proposal');
    expect(api.applyPlannedDates).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('suggest-apply'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.applyPlannedDates).toHaveBeenCalledWith('p', PROPOSAL);
    expect(onApplied).toHaveBeenCalledWith(SCHEDULE);
  });

  it('forgets the proposal when the day is changed', async () => {
    open();
    fireEvent.click(screen.getByLabelText('suggest-show'));
    await screen.findByLabelText('suggest-proposal');
    fireEvent.change(screen.getByLabelText('suggest-start'), { target: { value: '2026-10-20' } });
    expect(screen.queryByLabelText('suggest-proposal')).toBeNull();
    expect(screen.getByLabelText('suggest-show')).toBeInTheDocument();
  });

  it('says there is nothing to plan, and what went wrong', async () => {
    vi.mocked(api.suggestDates).mockResolvedValueOnce([]);
    open();
    fireEvent.click(screen.getByLabelText('suggest-show'));
    expect(await screen.findByText('Brak prac do zaplanowania.')).toBeInTheDocument();
  });

  it('shows an error and keeps the sheet when the proposal fails', async () => {
    vi.mocked(api.suggestDates).mockRejectedValueOnce(new Error('x'));
    const { onClose } = open();
    fireEvent.click(screen.getByLabelText('suggest-show'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się przygotować propozycji.');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes without saving', () => {
    const { onClose } = open();
    fireEvent.click(screen.getByLabelText('suggest-close'));
    expect(onClose).toHaveBeenCalled();
    expect(api.applyPlannedDates).not.toHaveBeenCalled();
  });
});
